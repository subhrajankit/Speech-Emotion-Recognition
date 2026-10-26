import sys
import os
import time
import subprocess
import torch
import numpy as np
import soundfile as sf

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from parler_tts import ParlerTTSForConditionalGeneration, ParlerTTSStreamer
from transformers import AutoTokenizer

def get_nvidia_smi_vram():
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,noheader"],
            capture_output=True, text=True, check=True
        )
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def calculate_speech_active_seconds(audio: np.ndarray, sr: int, frame_ms=30, hop_ms=10, energy_thresh=0.005):
    """Energy-based speech active seconds removing trailing silence."""
    frame_len = int(sr * frame_ms / 1000)
    hop_len = int(sr * hop_ms / 1000)
    if len(audio) < frame_len:
        return len(audio) / sr
    
    num_frames = (len(audio) - frame_len) // hop_len + 1
    rms = []
    for i in range(num_frames):
        chunk = audio[i * hop_len : i * hop_len + frame_len]
        rms.append(np.sqrt(np.mean(chunk**2)))
    rms = np.array(rms)
    
    active_frames = np.where(rms > energy_thresh)[0]
    if len(active_frames) == 0:
        return 0.0
    last_active_idx = active_frames[-1]
    last_sample = min(len(audio), (last_active_idx + 1) * hop_len + frame_len)
    return round(last_sample / sr, 2)

def run_single_benchmark(model, tokenizer, text, desc, device, dtype_str, max_new_tokens=None, do_stream=False, play_steps=12):
    if device == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    
    input_ids = tokenizer(desc, return_tensors="pt").input_ids.to(device)
    prompt_input_ids = tokenizer(text, return_tensors="pt").input_ids.to(device)
    
    gen_kwargs = {
        "input_ids": input_ids,
        "prompt_input_ids": prompt_input_ids,
        "do_sample": True,
        "temperature": 1.0,
    }
    limit = max_new_tokens if max_new_tokens is not None else 2610
    gen_kwargs["max_new_tokens"] = limit
    
    t_start = time.perf_counter()
    
    if do_stream:
        import threading
        streamer = ParlerTTSStreamer(model, device=device, play_steps=play_steps)
        gen_kwargs["streamer"] = streamer
        
        first_chunk_time = None
        chunks = []
        gen_thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
        gen_thread.start()
        
        for audio_chunk in streamer:
            if first_chunk_time is None:
                first_chunk_time = time.perf_counter() - t_start
            chunks.append(audio_chunk)
            
        gen_thread.join()
        total_time = time.perf_counter() - t_start
        audio = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
    else:
        with torch.no_grad():
            gen = model.generate(**gen_kwargs)
        total_time = time.perf_counter() - t_start
        first_chunk_time = total_time
        audio = gen.to(torch.float32).cpu().numpy().squeeze()
        
    vram_peak_smi = get_nvidia_smi_vram()
    cuda_alloc_peak = (torch.cuda.max_memory_allocated() / (1024 * 1024)) if device == "cuda" else 0.0
    
    sr = 44100
    actual_steps = int(len(audio) // 512)
    reached_eos = bool(actual_steps < limit)
    total_audio_sec = round(len(audio) / sr, 2)
    speech_active_sec = calculate_speech_active_seconds(audio, sr)
    rtf = round(total_time / total_audio_sec, 2) if total_audio_sec > 0 else 0.0
    
    return {
        "text": text,
        "device": device,
        "dtype": dtype_str,
        "max_new_tokens": limit,
        "actual_steps": actual_steps,
        "total_time_s": round(total_time, 2),
        "first_chunk_s": round(first_chunk_time, 2) if first_chunk_time else round(total_time, 2),
        "total_audio_s": total_audio_sec,
        "speech_active_s": speech_active_sec,
        "rtf": rtf,
        "reached_eos": reached_eos,
        "cuda_alloc_peak_mib": round(cuda_alloc_peak, 1),
        "vram_peak_smi_mib": round(vram_peak_smi, 1),
        "audio": audio,
        "sr": sr,
    }

def main():
    model_id = "ai4bharat/indic-parler-tts"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    sentences = [
        ("en_5w", "Hello, how can I help?"),
        ("hi_5w", "नमस्ते, मैं आपकी क्या मदद करूँ?"),
        ("en_14w", "The quick brown fox jumps over the lazy dog near the river bank."),
        ("hi_14w", "नमस्ते, आज का मौसम बहुत अच्छा है और मैं आपकी किस प्रकार मदद कर सकता हूँ?"),
    ]
    
    desc_en = "A female speaker delivers her speech with a calm tone, low pitch at a normal pace."
    desc_hi = "A female speaker delivers her speech in Hindi with a calm tone, low pitch at a normal pace."
    
    print("=" * 80)
    print("PHASE 8 TTS GENERATION LENGTH & STREAMING BENCHMARKS")
    print("=" * 80)
    
    results = []
    
    for test_dtype, dtype_name in [(torch.float16, "float16"), (torch.bfloat16, "bfloat16")]:
        print(f"\n==========================================")
        print(f"LOADING GPU MODEL: dtype={dtype_name}")
        print(f"==========================================")
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            model_id, torch_dtype=test_dtype
        ).to("cuda")
        
        for name, text in sentences:
            desc = desc_hi if name.startswith("hi") else desc_en
            word_count = len(text.split())
            
            # DAC Frame rate ratio:
            # DAC sampling rate = 44100 Hz, hop_length = 512 samples.
            # Frames per second = 44100 / 512 = 86.1328 frames/sec.
            # Speech rate = ~2.5 words/second.
            # Estimated speech duration = (words / 2.5) + 0.6s padding.
            est_sec = max(2.0, (word_count / 2.5) + 0.6)
            clamped_tokens = int(est_sec * 86.1328)
            
            # 1. Unconstrained run (max_length = 2610 tokens) - only do 5w to verify root cause without stalling
            if name.endswith("_5w"):
                print(f"\n[Benchmarking {name} ({dtype_name}) - UNCONSTRAINED (max_new_tokens=2610)]")
                r_uncon = run_single_benchmark(model, tokenizer, text, desc, "cuda", dtype_name, max_new_tokens=2610)
                print(f"  Steps: {r_uncon['actual_steps']} | Limit: {r_uncon['max_new_tokens']} | Audio: {r_uncon['total_audio_s']}s (Active: {r_uncon['speech_active_s']}s) | Time: {r_uncon['total_time_s']}s | RTF: {r_uncon['rtf']} | EOS: {r_uncon['reached_eos']} | Torch Alloc: {r_uncon['cuda_alloc_peak_mib']} MiB | SMI: {r_uncon['vram_peak_smi_mib']} MiB")
                results.append(r_uncon)
            
            # 2. Clamped run
            print(f"\n[Benchmarking {name} ({dtype_name}) - CLAMPED (max_new_tokens={clamped_tokens} for ~{est_sec:.1f}s)]")
            r_clamp = run_single_benchmark(model, tokenizer, text, desc, "cuda", dtype_name, max_new_tokens=clamped_tokens)
            print(f"  Steps: {r_clamp['actual_steps']} | Limit: {r_clamp['max_new_tokens']} | Audio: {r_clamp['total_audio_s']}s (Active: {r_clamp['speech_active_s']}s) | Time: {r_clamp['total_time_s']}s | RTF: {r_clamp['rtf']} | EOS: {r_clamp['reached_eos']} | Torch Alloc: {r_clamp['cuda_alloc_peak_mib']} MiB | SMI: {r_clamp['vram_peak_smi_mib']} MiB")
            results.append(r_clamp)
            
            out_wav = f"scripts/bench_{name}_{dtype_name}_clamped.wav"
            sf.write(out_wav, r_clamp['audio'], r_clamp['sr'], subtype="PCM_16")

        # Streaming on float16
        if dtype_name == "float16":
            print("\n------------------------------------------")
            print("STREAMING BENCHMARKS (ParlerTTSStreamer)")
            print("------------------------------------------")
            for p_steps in [12, 16, 20]:
                for name, text in [("en_5w", "Hello, how can I help?"), ("hi_5w", "नमस्ते, मैं आपकी क्या मदद करूँ?")]:
                    desc = desc_hi if name.startswith("hi") else desc_en
                    clamped_tokens = 258
                    r_stream = run_single_benchmark(model, tokenizer, text, desc, "cuda", dtype_name, max_new_tokens=clamped_tokens, do_stream=True, play_steps=p_steps)
                    print(f"play_steps={p_steps} | {name} | TTFC: {r_stream['first_chunk_s']}s | Total: {r_stream['total_time_s']}s | Audio: {r_stream['total_audio_s']}s | RTF: {r_stream['rtf']}")

        del model
        torch.cuda.empty_cache()

    # CPU Benchmark
    print("\n==========================================")
    print("CPU BENCHMARK (float32)")
    print("==========================================")
    threads = torch.get_num_threads()
    print(f"PyTorch CPU threads: {threads}")
    model_cpu = ParlerTTSForConditionalGeneration.from_pretrained(
        model_id, torch_dtype=torch.float32
    ).to("cpu")
    
    text_5w = "Hello, how can I help?"
    clamped_tokens = 258
    r_cpu = run_single_benchmark(model_cpu, tokenizer, text_5w, desc_en, "cpu", "float32", max_new_tokens=clamped_tokens)
    print(f"CPU float32 ({threads} threads) | Steps: {r_cpu['actual_steps']} | Time: {r_cpu['total_time_s']}s | Audio: {r_cpu['total_audio_s']}s | RTF: {r_cpu['rtf']}")
    
    # Profile DAC decode vs Decoder autoregression
    print("\n--- PROFILING DAC DECODE VS DECODER AUTOREGRESSION (GPU fp16) ---")
    model_gpu = ParlerTTSForConditionalGeneration.from_pretrained(
        model_id, torch_dtype=torch.float16
    ).to("cuda")
    input_ids = tokenizer(desc_en, return_tensors="pt").input_ids.to("cuda")
    prompt_input_ids = tokenizer(text_5w, return_tensors="pt").input_ids.to("cuda")
    
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model_gpu.generate(input_ids=input_ids, prompt_input_ids=prompt_input_ids, max_new_tokens=258, return_dict_in_generate=True)
    t1 = time.perf_counter()
    gen_time = t1 - t0
    
    # Check sequences shape
    seqs = out.sequences
    print(f"Generated tokens shape: {seqs.shape} in {gen_time:.3f}s")
    t2 = time.perf_counter()
    with torch.no_grad():
        # Codebook decode
        dac_audio = model_gpu.audio_encoder.decode(seqs).audio_values
    t3 = time.perf_counter()
    dac_time = t3 - t2
    print(f"Autoregressive generation time: {gen_time:.3f}s ({gen_time/(gen_time+dac_time)*100:.1f}%)")
    print(f"DAC audio decode time: {dac_time:.3f}s ({dac_time/(gen_time+dac_time)*100:.1f}%)")
    
    del model_gpu
    torch.cuda.empty_cache()

if __name__ == "__main__":
    main()
