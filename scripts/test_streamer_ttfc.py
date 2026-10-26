import sys
import time
import threading
import torch
from parler_tts import ParlerTTSForConditionalGeneration, ParlerTTSStreamer
from transformers import AutoTokenizer

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def main():
    device = "cuda"
    tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc_tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        "ai4bharat/indic-parler-tts",
        torch_dtype=torch.float16,
    ).to(device)
    model.eval()

    desc = "Aditi speaks with natural, balanced delivery and moderate pace."
    desc_ids = desc_tokenizer(desc, return_tensors="pt").input_ids.to(device)
    prompt_ids = tokenizer("Hello! How are you doing?", return_tensors="pt").input_ids.to(device)

    # Test ParlerTTSStreamer with play_steps=5 and play_steps=10
    for play_steps in [5, 10]:
        print(f"\n--- Testing ParlerTTSStreamer with play_steps={play_steps} ---", flush=True)
        streamer = ParlerTTSStreamer(model, device=device, play_steps=play_steps)
        
        t0 = time.perf_counter()
        first_chunk_time = None
        chunk_times = []
        chunks = []

        def run_gen():
            with torch.no_grad():
                model.generate(
                    input_ids=desc_ids,
                    prompt_input_ids=prompt_ids,
                    streamer=streamer,
                )

        t_thread = threading.Thread(target=run_gen)
        t_thread.start()

        for chunk in streamer:
            now = time.perf_counter()
            if first_chunk_time is None:
                first_chunk_time = now - t0
            chunk_times.append(now - t0)
            chunks.append(chunk)

        t_thread.join()
        total_time = time.perf_counter() - t0
        print(f"play_steps={play_steps}: TTFC={first_chunk_time:.2f}s, Total Time={total_time:.2f}s, Num Chunks={len(chunks)}", flush=True)

if __name__ == "__main__":
    main()
