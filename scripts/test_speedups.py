"""
Tests Parler-TTS speedups on this Windows setup:
1. attn_implementation="sdpa"
2. ParlerTTSStreamer
3. Static cache (cache_implementation="static")
"""
import sys
import time
import torch

def test_sdpa():
    print("--- Testing SDPA Attention ---")
    try:
        from parler_tts import ParlerTTSForConditionalGeneration
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            "ai4bharat/indic-parler-tts",
            torch_dtype=torch.float16,
            attn_implementation="sdpa",
        ).to("cuda")
        print("SDPA load SUCCESS: model loaded with attn_implementation='sdpa'")
        del model
        torch.cuda.empty_cache()
        return True
    except Exception as e:
        print(f"SDPA load FAILED: {type(e).__name__}: {e}")
        return False

def test_streamer():
    print("\n--- Testing ParlerTTSStreamer ---")
    try:
        import parler_tts
        print("parler_tts dir has streamer?", "ParlerTTSStreamer" in dir(parler_tts))
        if "ParlerTTSStreamer" in dir(parler_tts):
            streamer_cls = getattr(parler_tts, "ParlerTTSStreamer")
            print("ParlerTTSStreamer found:", streamer_cls)
            return True
        else:
            # Check transformers streamers
            import transformers
            print("transformers streamers:", [x for x in dir(transformers) if "stream" in x.lower()])
            return False
    except Exception as e:
        print(f"Streamer check FAILED: {e}")
        return False

def test_static_cache():
    print("\n--- Testing Static Cache ---")
    try:
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            "ai4bharat/indic-parler-tts",
            torch_dtype=torch.float16,
        ).to("cuda")
        tokenizer = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
        
        # Test if cache_implementation="static" can be set
        try:
            model.generation_config.cache_implementation = "static"
            desc_ids = tokenizer("Aditi speaks clearly.", return_tensors="pt").input_ids.to("cuda")
            prompt_ids = tokenizer("Hello.", return_tensors="pt").input_ids.to("cuda")
            with torch.no_grad():
                out = model.generate(input_ids=desc_ids, prompt_input_ids=prompt_ids)
            print("Static cache SUCCESS")
            del model
            torch.cuda.empty_cache()
            return True
        except Exception as gen_e:
            print(f"Static cache generate FAILED: {type(gen_e).__name__}: {gen_e}")
            del model
            torch.cuda.empty_cache()
            return False
    except Exception as e:
        print(f"Static cache check FAILED: {e}")
        return False

if __name__ == "__main__":
    sdpa_ok = test_sdpa()
    streamer_ok = test_streamer()
    static_ok = test_static_cache()
    print("\n=== Summary ===")
    print(f"SDPA: {sdpa_ok}")
    print(f"ParlerTTSStreamer: {streamer_ok}")
    print(f"Static Cache: {static_ok}")
