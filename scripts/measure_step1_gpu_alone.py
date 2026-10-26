import sys
import os
import time
import subprocess
import threading
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
    log(f"=== STEP 1: TTS ALONE ON GPU (FP16) ===")
    log(f"Baseline initial VRAM: {get_vram():.1f} MiB")

    from parler_tts import ParlerTTSForConditionalGeneration, ParlerTTSStreamer
    from transformers import AutoTokenizer

    t0 = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc_tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        "ai4bharat/indic-parler-tts",
        torch_dtype=torch.float16,
    ).to("cuda")
    model.eval()
    load_time = time.perf_counter() - t0
    log(f"Model loaded in {load_time:.2f}s. Loaded VRAM: {get_vram():.1f} MiB")

    sr = getattr(model.config, "sampling_rate", 44100)
    desc = "Aditi speaks with natural, balanced delivery and moderate pace."
    desc_ids = desc_tokenizer(desc, return_tensors="pt").input_ids.to("cuda")

    tests = [
        ("EN_5_words", "Hello! How are you doing?"),
        ("HI_5_words", "नमस्ते! आप कैसे हैं आज?"),
        ("EN_14_words", "VoiceSense AI provides multilingual and emotion aware voice assistance across twenty three Indian languages."),
        ("HI_14_words", "वॉइससेंस एआई भारतीय भाषाओं में भावना और ध्वनि को अच्छी तरह समझता है आज।"),
    ]

    os.makedirs("tests/samples", exist_ok=True)

    for label, text in tests:
        prompt_ids = tokenizer(text, return_tensors="pt").input_ids.to("cuda")
        log(f"\nEvaluating {label} ({len(text.split())} words): '{text}'")

        # 1. Standard full-sentence generation
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

        # 2. Streaming first-chunk latency measurement with ParlerTTSStreamer (play_steps=12 > 9)
        stream_ttfc = None
        try:
            streamer = ParlerTTSStreamer(model, device="cuda", play_steps=12, timeout=60.0)
            t_s0 = time.perf_counter()
            def run_stream():
                with torch.no_grad():
                    model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids, streamer=streamer)
            th = threading.Thread(target=run_stream)
            th.start()
            for chunk in streamer:
                if stream_ttfc is None:
                    stream_ttfc = time.perf_counter() - t_s0
                    break  # Got first chunk
            th.join()
        except Exception as e:
            stream_ttfc = f"error: {e}"

        log(f"-> {label} RESULTS:")
        log(f"   Full Synthesis Time: {synth_sec:.2f} s")
        log(f"   Audio Duration: {audio_dur:.2f} s")
        log(f"   RTF: {rtf:.2f}")
        log(f"   Peak VRAM: {peak_vram:.1f} MiB")
        log(f"   Peak Amplitude: {amp:.3f}")
        log(f"   Streaming TTFC (play_steps=12): {stream_ttfc if isinstance(stream_ttfc, str) else f'{stream_ttfc:.2f} s'}")
        log(f"   Output WAV: {out_path}")

    log("\n=== STEP 1 COMPLETE ===")

if __name__ == "__main__":
    main()
