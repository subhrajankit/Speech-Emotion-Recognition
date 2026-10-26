import sys
import os
import time
import subprocess
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

def main():
    log(f"=== GPU ALONE (FP16) SENTENCE BENCHMARK ===")
    log(f"Initial VRAM: {get_vram():.1f} MiB")

    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer

    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc_tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        "ai4bharat/indic-parler-tts",
        torch_dtype=torch.float16,
    ).to("cuda")
    model.eval()
    log(f"Model loaded in {time.perf_counter() - t0:.2f}s. Loaded VRAM: {get_vram():.1f} MiB")

    sr = getattr(model.config, "sampling_rate", 44100)
    desc = "Aditi speaks with natural, balanced delivery and moderate pace."
    desc_ids = desc_tokenizer(desc, return_tensors="pt").input_ids.to("cuda")

    # Run remaining 3 sentences (EN_5 was already measured at synth_time=93.17s, dur=11.40s, RTF=8.17, peak_VRAM=3555.0MiB)
    tests = [
        ("HI_5_words", "नमस्ते! आप कैसे हैं आज?"),
        ("EN_14_words", "VoiceSense AI provides multilingual and emotion aware voice assistance across twenty three Indian languages."),
        ("HI_14_words", "वॉइससेंस एआई भारतीय भाषाओं में भावना और ध्वनि को अच्छी तरह समझता है आज।"),
    ]

    os.makedirs("tests/samples", exist_ok=True)

    for label, text in tests:
        log(f"\n--- Starting {label} ({len(text.split())} words) ---")
        prompt_ids = tokenizer(text, return_tensors="pt").input_ids.to("cuda")

        t_gen_0 = time.perf_counter()
        with torch.no_grad():
            gen = model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids)
        synth_sec = time.perf_counter() - t_gen_0
        peak_vram = get_vram()

        audio_arr = gen.to(torch.float32).cpu().numpy().squeeze()
        audio_dur = len(audio_arr) / sr
        rtf = synth_sec / audio_dur if audio_dur > 0 else 0
        amp = float(np.max(np.abs(audio_arr)))
        out_path = f"tests/samples/{label.lower()}_gpu_fp16.wav"
        sf.write(out_path, audio_arr, sr, format="WAV", subtype="PCM_16")

        log(f"RESULT {label}: synth_time={synth_sec:.2f}s, dur={audio_dur:.2f}s, RTF={rtf:.2f}, peak_VRAM={peak_vram:.1f}MiB, peak_amp={amp:.3f}, file={out_path}")

    log("\n=== ALL GPU BENCHMARKS COMPLETE ===")

if __name__ == "__main__":
    main()
