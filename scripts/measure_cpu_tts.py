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

def main():
    log("=== STEP 3: CPU TTS BENCHMARK (DEVICE-AWARE DTYPE) ===")
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc_tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc = "Aditi speaks with natural, balanced delivery and moderate pace."

    for dtype_name, torch_dtype in [("float32", torch.float32), ("bfloat16", torch.bfloat16)]:
        log(f"\n--- Loading model on CPU with dtype={dtype_name} ---")
        t0 = time.perf_counter()
        try:
            model = ParlerTTSForConditionalGeneration.from_pretrained(
                "ai4bharat/indic-parler-tts",
                torch_dtype=torch_dtype,
            ).to("cpu")
            model.eval()
            log(f"Model loaded in {time.perf_counter() - t0:.2f}s")
        except Exception as e:
            log(f"Failed to load on CPU with {dtype_name}: {e}")
            continue

        sr = getattr(model.config, "sampling_rate", 44100)
        desc_ids = desc_tokenizer(desc, return_tensors="pt").input_ids.to("cpu")

        tests = [
            ("EN_5_words", "Hello! How are you doing?"),
            ("HI_5_words", "नमस्ते! आप कैसे हैं आज?"),
        ]

        for label, text in tests:
            prompt_ids = tokenizer(text, return_tensors="pt").input_ids.to("cpu")
            log(f"Running CPU {label} ({dtype_name}): '{text}'")
            t_start = time.perf_counter()
            with torch.no_grad():
                gen = model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids)
            synth_sec = time.perf_counter() - t_start

            audio_arr = gen.to(torch.float32).cpu().numpy().squeeze()
            dur = len(audio_arr) / sr
            rtf = synth_sec / dur if dur > 0 else 0
            amp = float(np.max(np.abs(audio_arr)))
            out_path = f"tests/samples/{label.lower()}_cpu_{dtype_name}.wav"
            sf.write(out_path, audio_arr, sr, format="WAV", subtype="PCM_16")
            log(f"RESULT CPU {label} ({dtype_name}): synth_time={synth_sec:.2f}s, dur={dur:.2f}s, RTF={rtf:.2f}, peak_amp={amp:.3f}, file={out_path}")

        del model

    log("\n=== CPU BENCHMARK COMPLETE ===")

if __name__ == "__main__":
    main()
