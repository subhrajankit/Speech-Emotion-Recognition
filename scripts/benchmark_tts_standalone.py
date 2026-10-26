"""
Comprehensive Standalone TTS Benchmark on GPU (Alone)
Measures:
- Peak VRAM via nvidia-smi
- Time to First Chunk (TTFC)
- Total Synthesis Time & RTF
- Audio Duration & Peak Amplitude
- Compares:
  - Standard generate
  - ParlerTTSStreamer (streaming generation)
  - Static cache
For:
  (a) 5-word chunk (EN & HI)
  (b) 14-word sentence (EN & HI)
"""
import os
import sys
import time
import subprocess
import torch
import soundfile as sf
import numpy as np
from parler_tts import ParlerTTSForConditionalGeneration
from transformers import AutoTokenizer

def get_gpu_vram_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            encoding="utf-8"
        )
        return float(out.strip().split("\n")[0])
    except Exception:
        return 0.0

# Sentences
EN_5 = "Hello! How are you doing?"
HI_5 = "नमस्ते! आप कैसे हैं आज?"
EN_14 = "VoiceSense AI provides multilingual and emotion aware voice assistance across twenty three Indian languages."
HI_14 = "वॉइससेंस एआई भारतीय भाषाओं में भावना और ध्वनि को अच्छी तरह समझता है आज।"

DESC = "Aditi speaks with natural, balanced delivery and moderate pace."

def benchmark():
    os.makedirs("tests/samples", exist_ok=True)
    device = "cuda"
    dtype = torch.float16
    
    print(f"Initial GPU VRAM: {get_gpu_vram_mb():.1f} MiB")
    t_load_0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    description_tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        "ai4bharat/indic-parler-tts",
        torch_dtype=dtype,
    ).to(device)
    model.eval()
    t_load = (time.perf_counter() - t_load_0)
    sr = getattr(model.config, "sampling_rate", 44100)
    print(f"Model loaded in {t_load:.2f}s. Loaded GPU VRAM: {get_gpu_vram_mb():.1f} MiB")

    tests = [
        ("EN_5_words", EN_5, "output_en_5_gpu_fp16.wav"),
        ("HI_5_words", HI_5, "output_hi_5_gpu_fp16.wav"),
        ("EN_14_words", EN_14, "output_en_14_gpu_fp16.wav"),
        ("HI_14_words", HI_14, "output_hi_14_gpu_fp16.wav"),
    ]

    results = []

    # Warmup
    print("\nWarming up model...")
    warm_desc = description_tokenizer("Aditi speaks.", return_tensors="pt").input_ids.to(device)
    warm_prompt = tokenizer("Hello.", return_tensors="pt").input_ids.to(device)
    with torch.no_grad():
        _ = model.generate(input_ids=warm_desc, prompt_input_ids=warm_prompt)
    print(f"Post-warmup GPU VRAM: {get_gpu_vram_mb():.1f} MiB")

    for label, text, out_name in tests:
        desc_ids = description_tokenizer(DESC, return_tensors="pt").input_ids.to(device)
        prompt_ids = tokenizer(text, return_tensors="pt").input_ids.to(device)
        
        peak_vram = get_gpu_vram_mb()
        t0 = time.perf_counter()
        with torch.no_grad():
            gen = model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids)
        t_gen = time.perf_counter() - t0
        peak_vram = max(peak_vram, get_gpu_vram_mb())

        audio_arr = gen.to(torch.float32).cpu().numpy().squeeze()
        audio_dur = len(audio_arr) / sr
        rtf = t_gen / audio_dur if audio_dur > 0 else 0
        peak_amp = float(np.max(np.abs(audio_arr)))

        out_path = os.path.join("tests/samples", out_name)
        sf.write(out_path, audio_arr, sr, format="WAV", subtype="PCM_16")

        res = {
            "label": label,
            "text": text,
            "words": len(text.split()),
            "synthesis_sec": t_gen,
            "audio_dur_sec": audio_dur,
            "rtf": rtf,
            "peak_vram_mb": peak_vram,
            "peak_amp": peak_amp,
            "out_path": out_path
        }
        results.append(res)
        print(f"[{label}] ({len(text.split())} words) synth={t_gen:.2f}s, dur={audio_dur:.2f}s, RTF={rtf:.2f}, peak_VRAM={peak_vram:.1f}MiB, peak_amp={peak_amp:.3f}")

    # Now test ParlerTTSStreamer for streaming TTFC
    print("\n--- Testing Streaming Generation via ParlerTTSStreamer ---")
    try:
        from parler_tts import ParlerTTSStreamer
        streamer = ParlerTTSStreamer(model, device=device)
        # Test streaming on EN_5
        desc_ids = description_tokenizer(DESC, return_tensors="pt").input_ids.to(device)
        prompt_ids = tokenizer(EN_5, return_tensors="pt").input_ids.to(device)
        
        import threading
        t0 = time.perf_counter()
        first_chunk_time = None
        chunks = []
        
        def run_gen():
            with torch.no_grad():
                model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids, streamer=streamer)

        gen_thread = threading.Thread(target=run_gen)
        gen_thread.start()
        
        for audio_chunk in streamer:
            if first_chunk_time is None:
                first_chunk_time = time.perf_counter() - t0
            chunks.append(audio_chunk)
        gen_thread.join()
        total_stream_time = time.perf_counter() - t0
        print(f"ParlerTTSStreamer on EN_5: TTFC={first_chunk_time:.3f}s, Total={total_stream_time:.2f}s, Chunks={len(chunks)}")
    except Exception as e:
        print(f"ParlerTTSStreamer run failed: {type(e).__name__}: {e}")

    # Test static cache on EN_5
    print("\n--- Testing Static Cache on EN_5 ---")
    try:
        model.generation_config.cache_implementation = "static"
        t0 = time.perf_counter()
        with torch.no_grad():
            gen_sc = model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids)
        t_sc = time.perf_counter() - t0
        print(f"Static Cache on EN_5: synth={t_sc:.2f}s vs standard synth={results[0]['synthesis_sec']:.2f}s")
    except Exception as e:
        print(f"Static Cache generate failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    benchmark()
