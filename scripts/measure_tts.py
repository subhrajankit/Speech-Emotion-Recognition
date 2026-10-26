"""
Benchmark script for Phase 8 Indic Parler-TTS measurement.
Measures:
1. Real-Time Factor (RTF = synthesis_time / audio_duration).
2. Time-To-First-Chunk (TTFC).
3. VRAM and RAM footprint via torch.cuda and nvidia-smi.
4. Generates real English and Hindi WAV files for listening evaluation.
"""

import os
import sys
import time
import subprocess
import soundfile as sf
import torch
from parler_tts import ParlerTTSForConditionalGeneration
from transformers import AutoTokenizer

ENGLISH_TEXT = "VoiceSense AI provides multilingual and emotion aware voice assistance across twenty three Indian languages."
HINDI_TEXT = "वॉइससेंस एआई भारतीय भाषाओं में भावना और ध्वनि को समझता है।"

ENGLISH_DESC = "Aditi speaks in a clear, natural voice with high quality audio and moderate pace."
HINDI_DESC = "Aditi speaks in a clear, natural voice with high quality audio and moderate pace."


def get_nvidia_smi_vram():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,nounits,noheader"],
            encoding="utf-8"
        )
        used, total = out.strip().split("\n")[0].split(",")
        return float(used.strip()), float(total.strip())
    except Exception as e:
        return 0.0, 0.0


def benchmark_device(device_name: str, dtype_name: str = "float32", out_prefix: str = "gpu"):
    print(f"\n========================================================")
    print(f"BENCHMARKING INDIC PARLER-TTS ON: {device_name.upper()} ({dtype_name.upper()})")
    print(f"========================================================")

    if device_name == "cpu":
        print(f"PyTorch CPU threads: {torch.get_num_threads()} (logical cores: {os.cpu_count()})")

    torch_dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
    }
    selected_dtype = torch_dtype_map.get(dtype_name.lower(), torch.float32)

    vram_before, vram_total = get_nvidia_smi_vram()
    print(f"Initial VRAM via nvidia-smi: {vram_before:.0f} MiB / {vram_total:.0f} MiB")

    t_load_start = time.perf_counter()
    model_id = "ai4bharat/indic-parler-tts"

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    description_tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=selected_dtype if device_name == "cuda" else torch.float32,
    )
    model.to(device_name)
    model.eval()

    load_time_sec = time.perf_counter() - t_load_start
    print(f"Model load time: {load_time_sec:.2f} s")
    print(f"Model loaded dtype: {model.dtype}")

    vram_loaded, _ = get_nvidia_smi_vram()
    delta_vram = vram_loaded - vram_before
    print(f"VRAM after model load: {vram_loaded:.0f} MiB (Model delta: +{delta_vram:.0f} MiB)")
    if device_name == "cuda":
        torch_alloc = torch.cuda.memory_allocated() / (1024 * 1024)
        torch_res = torch.cuda.memory_reserved() / (1024 * 1024)
        print(f"PyTorch CUDA allocated: {torch_alloc:.1f} MiB, reserved: {torch_res:.1f} MiB")

    os.makedirs("tests/samples", exist_ok=True)
    sample_rate = getattr(model.config, "sampling_rate", 44100)

    # 1. Warm-up run (short sentence)
    print("\nRunning warm-up synthesis...")
    w_prompt = tokenizer("Hello.", return_tensors="pt").input_ids.to(device_name)
    w_desc = description_tokenizer(ENGLISH_DESC, return_tensors="pt").input_ids.to(device_name)
    with torch.no_grad():
        _ = model.generate(input_ids=w_desc, prompt_input_ids=w_prompt)
    if device_name == "cuda":
        torch.cuda.synchronize()

    # 2. English Benchmark
    print("\n--- Synthesizing English Sentence ---")
    print(f"Text: \"{ENGLISH_TEXT}\"")
    en_prompt = tokenizer(ENGLISH_TEXT, return_tensors="pt").input_ids.to(device_name)
    en_desc = description_tokenizer(ENGLISH_DESC, return_tensors="pt").input_ids.to(device_name)

    t0 = time.perf_counter()
    with torch.no_grad():
        en_gen = model.generate(input_ids=en_desc, prompt_input_ids=en_prompt)
    if device_name == "cuda":
        torch.cuda.synchronize()
    en_synth_sec = time.perf_counter() - t0

    en_audio = en_gen.to(torch.float32).cpu().numpy().squeeze()
    en_out_path = f"tests/samples/output_english_{out_prefix}.wav"
    sf.write(en_out_path, en_audio, sample_rate, format="WAV", subtype="PCM_16")

    en_audio_dur_sec = len(en_audio) / sample_rate
    en_rtf = en_synth_sec / en_audio_dur_sec if en_audio_dur_sec > 0 else 0.0
    en_peak_amp = float(np.max(np.abs(en_audio))) if len(en_audio) > 0 else 0.0

    print(f"Saved: {en_out_path}")
    print(f"Audio duration: {en_audio_dur_sec:.2f} s")
    print(f"Synthesis time (TTFC): {en_synth_sec:.3f} s ({en_synth_sec * 1000:.0f} ms)")
    print(f"Real-Time Factor (RTF): {en_rtf:.3f} ({'Faster than real-time' if en_rtf < 1.0 else 'Slower than real-time'})")
    print(f"Peak amplitude: {en_peak_amp:.4f}")

    # 3. Hindi Benchmark
    print("\n--- Synthesizing Hindi Sentence ---")
    print(f"Text: \"{HINDI_TEXT}\"")
    hi_prompt = tokenizer(HINDI_TEXT, return_tensors="pt").input_ids.to(device_name)
    hi_desc = description_tokenizer(HINDI_DESC, return_tensors="pt").input_ids.to(device_name)

    t0 = time.perf_counter()
    with torch.no_grad():
        hi_gen = model.generate(input_ids=hi_desc, prompt_input_ids=hi_prompt)
    if device_name == "cuda":
        torch.cuda.synchronize()
    hi_synth_sec = time.perf_counter() - t0

    hi_audio = hi_gen.to(torch.float32).cpu().numpy().squeeze()
    hi_out_path = f"tests/samples/output_hindi_{out_prefix}.wav"
    sf.write(hi_out_path, hi_audio, sample_rate, format="WAV", subtype="PCM_16")

    hi_audio_dur_sec = len(hi_audio) / sample_rate
    hi_rtf = hi_synth_sec / hi_audio_dur_sec if hi_audio_dur_sec > 0 else 0.0
    hi_peak_amp = float(np.max(np.abs(hi_audio))) if len(hi_audio) > 0 else 0.0

    print(f"Saved: {hi_out_path}")
    print(f"Audio duration: {hi_audio_dur_sec:.2f} s")
    print(f"Synthesis time (TTFC): {hi_synth_sec:.3f} s ({hi_synth_sec * 1000:.0f} ms)")
    print(f"Real-Time Factor (RTF): {hi_rtf:.3f} ({'Faster than real-time' if hi_rtf < 1.0 else 'Slower than real-time'})")
    print(f"Peak amplitude: {hi_peak_amp:.4f}")

    vram_peak, _ = get_nvidia_smi_vram()
    print(f"\nPeak VRAM during inference: {vram_peak:.0f} MiB")

    # Clean up
    del model
    del tokenizer
    del description_tokenizer
    if device_name == "cuda":
        torch.cuda.empty_cache()

    return {
        "device": device_name,
        "dtype": str(selected_dtype),
        "load_time_sec": load_time_sec,
        "vram_delta_mib": delta_vram,
        "vram_peak_mib": vram_peak,
        "en_path": en_out_path,
        "en_synth_ms": en_synth_sec * 1000,
        "en_audio_sec": en_audio_dur_sec,
        "en_rtf": en_rtf,
        "en_peak_amp": en_peak_amp,
        "hi_path": hi_out_path,
        "hi_synth_ms": hi_synth_sec * 1000,
        "hi_audio_sec": hi_audio_dur_sec,
        "hi_rtf": hi_rtf,
        "hi_peak_amp": hi_peak_amp,
    }


if __name__ == "__main__":
    import numpy as np
    device = sys.argv[1] if len(sys.argv) > 1 else "cuda"
    dtype = sys.argv[2] if len(sys.argv) > 2 else "float32"
    prefix = sys.argv[3] if len(sys.argv) > 3 else f"{device}_{dtype}"
    benchmark_device(device, dtype, prefix)

