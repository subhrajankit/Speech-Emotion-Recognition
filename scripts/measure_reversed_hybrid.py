import sys
import os
import time
import subprocess
import threading
import json
import urllib.request
import torch
import soundfile as sf
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def log(msg):
    print(msg, flush=True)

def get_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            encoding="utf-8"
        )
        return float(out.strip().split("\n")[0])
    except Exception:
        return 0.0

def get_process_ram_mb(name="llama-server"):
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue).WorkingSet64 / 1MB"],
            encoding="utf-8"
        )
        return float(out.strip().split("\n")[0])
    except Exception:
        return 0.0

def stream_llm(prompt, completion_holder):
    url = "http://127.0.0.1:8080/v1/chat/completions"
    payload = {
        "model": "qwen3-1.7b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 150,
        "temperature": 0.7,
        "stream": True,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    tokens = 0
    t_first = None
    try:
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            for line in resp:
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str or not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:].strip()
                if data_str == "[DONE]":
                    break
                tokens += 1
                if t_first is None:
                    t_first = time.perf_counter() - t0
        total_time = time.perf_counter() - t0
        tok_s = tokens / total_time if total_time > 0 else 0
        completion_holder["tokens"] = tokens
        completion_holder["total_time"] = total_time
        completion_holder["tok_s"] = tok_s
        completion_holder["first_token_time"] = t_first
    except Exception as e:
        completion_holder["error"] = str(e)

def main():
    log("=== STEP 2: REVERSED HYBRID (LLM on CPU, TTS on GPU FP16) ===")
    initial_vram = get_vram()
    llama_ram = get_process_ram_mb("llama-server")
    log(f"Baseline: GPU VRAM = {initial_vram:.1f} MiB, llama-server RAM = {llama_ram:.1f} MiB")

    # 1. Baseline LLM alone on CPU
    log("\n--- Benchmarking LLM Alone on CPU ---")
    holder_alone = {}
    stream_llm("Explain how voice assistants work in 4 paragraphs.", holder_alone)
    log(f"LLM Alone on CPU: {holder_alone.get('tokens')} tokens in {holder_alone.get('total_time', 0):.2f}s -> {holder_alone.get('tok_s', 0):.2f} tok/s (First token: {holder_alone.get('first_token_time', 0):.3f}s)")

    # 2. Load TTS model on GPU
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer

    log("\n--- Loading Indic Parler-TTS on GPU (FP16) ---")
    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc_tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    tts_model = ParlerTTSForConditionalGeneration.from_pretrained(
        "ai4bharat/indic-parler-tts",
        torch_dtype=torch.float16,
    ).to("cuda")
    tts_model.eval()
    log(f"TTS loaded in {time.perf_counter() - t0:.2f}s. GPU VRAM with TTS loaded: {get_vram():.1f} MiB")

    sr = getattr(tts_model.config, "sampling_rate", 44100)
    desc = "Aditi speaks with natural, balanced delivery and moderate pace."
    desc_ids = desc_tokenizer(desc, return_tensors="pt").input_ids.to("cuda")
    prompt_ids = tokenizer("Hello! How are you doing?", return_tensors="pt").input_ids.to("cuda")

    # 3. Concurrent Run: LLM busy generating on CPU WHILE TTS runs on GPU
    log("\n--- Running Concurrent: LLM streaming on CPU + TTS generating on GPU ---")
    holder_concurrent = {}
    llm_thread = threading.Thread(
        target=stream_llm,
        args=("Write a detailed story about an AI exploring a new planet.", holder_concurrent)
    )
    
    # Start LLM first so it's busy
    llm_thread.start()
    time.sleep(0.5)  # Ensure LLM is actively streaming

    # Start TTS on GPU
    t_tts_0 = time.perf_counter()
    peak_vram_concurrent = get_vram()
    with torch.no_grad():
        tts_gen = tts_model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids)
    tts_time = time.perf_counter() - t_tts_0
    peak_vram_concurrent = max(peak_vram_concurrent, get_vram())

    llm_thread.join()

    # Process audio
    audio_arr = tts_gen.to(torch.float32).cpu().numpy().squeeze()
    dur = len(audio_arr) / sr
    rtf = tts_time / dur if dur > 0 else 0
    amp = float(np.max(np.abs(audio_arr)))
    out_path = "tests/samples/reversed_hybrid_en_5_gpu_fp16.wav"
    sf.write(out_path, audio_arr, sr, format="WAV", subtype="PCM_16")

    llama_ram_post = get_process_ram_mb("llama-server")

    log("\n--- REVERSED HYBRID CONCURRENT RESULTS ---")
    log(f"LLM on CPU (Concurrent): {holder_concurrent.get('tokens')} tokens in {holder_concurrent.get('total_time', 0):.2f}s -> {holder_concurrent.get('tok_s', 0):.2f} tok/s")
    log(f"llama-server RAM: {llama_ram_post:.1f} MiB")
    log(f"TTS on GPU (Concurrent): synth_time={tts_time:.2f}s, dur={dur:.2f}s, RTF={rtf:.2f}")
    log(f"Peak GPU VRAM during concurrent run: {peak_vram_concurrent:.1f} MiB")
    log(f"Output audio: {out_path} (peak_amp={amp:.3f})")

if __name__ == "__main__":
    main()
