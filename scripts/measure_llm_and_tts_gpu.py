import sys
import time
import subprocess
import torch
import numpy as np

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

def main():
    model_id = "ai4bharat/indic-parler-tts"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    baseline_vram = get_nvidia_smi_vram()
    print(f"Baseline VRAM with llama-server active: {baseline_vram:.1f} MiB")
    
    desc_en = "A female speaker delivers her speech with a calm tone, low pitch at a normal pace."
    desc_hi = "A female speaker delivers her speech in Hindi with a calm tone, low pitch at a normal pace."
    
    en_5w = "Hello, how can I help?"
    hi_5w = "नमस्ते, मैं आपकी क्या मदद करूँ?"
    
    for dtype_val, dtype_name in [(torch.float16, "float16"), (torch.bfloat16, "bfloat16")]:
        print(f"\n==========================================")
        print(f"TESTING LLM ON GPU + TTS ON GPU ({dtype_name})")
        print(f"==========================================")
        
        try:
            model = ParlerTTSForConditionalGeneration.from_pretrained(
                model_id, torch_dtype=dtype_val
            ).to("cuda")
        except Exception as e:
            print(f"Failed to load TTS model on GPU ({e})")
            continue
            
        load_vram = get_nvidia_smi_vram()
        print(f"VRAM after TTS model load: {load_vram:.1f} MiB")
        
        for name, text in [("en_5w", en_5w), ("hi_5w", hi_5w)]:
            desc = desc_hi if name.startswith("hi") else desc_en
            input_ids = tokenizer(desc, return_tensors="pt").input_ids.to("cuda")
            prompt_input_ids = tokenizer(text, return_tensors="pt").input_ids.to("cuda")
            
            # Using ParlerTTSStreamer with play_steps=12
            streamer = ParlerTTSStreamer(model, device="cuda", play_steps=12)
            gen_kwargs = {
                "input_ids": input_ids,
                "prompt_input_ids": prompt_input_ids,
                "do_sample": True,
                "temperature": 1.0,
                "max_new_tokens": 258,
                "streamer": streamer,
            }
            
            import threading
            first_chunk_time = None
            peak_vram = 0.0
            
            t0 = time.perf_counter()
            gen_thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
            gen_thread.start()
            
            for chunk in streamer:
                if first_chunk_time is None:
                    first_chunk_time = time.perf_counter() - t0
                cur_vram = get_nvidia_smi_vram()
                if cur_vram > peak_vram:
                    peak_vram = cur_vram
                    
            gen_thread.join()
            total_time = time.perf_counter() - t0
            final_vram = get_nvidia_smi_vram()
            if final_vram > peak_vram:
                peak_vram = final_vram
                
            torch_alloc = torch.cuda.max_memory_allocated() / (1024 * 1024)
            print(f"[{name} - {dtype_name}] First Chunk Time: {first_chunk_time:.2f}s | Total Time: {total_time:.2f}s | Peak Total VRAM: {peak_vram:.1f} MiB | Torch Alloc: {torch_alloc:.1f} MiB")
            
        del model
        torch.cuda.empty_cache()

if __name__ == "__main__":
    main()
