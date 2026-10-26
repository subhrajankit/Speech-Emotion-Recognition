"""
Worker script executed inside .venv-tts for Indic Parler-TTS synthesis.
Isolates PyTorch and Parler-TTS dependencies from the main environment.
"""

import argparse
import io
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Indic Parler-TTS Worker")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--description", required=True, help="Voice description prompt")
    parser.add_argument("--device", default="cuda", help="cuda or cpu")
    parser.add_argument("--dtype", default="float16", help="float32, float16, or bfloat16")
    parser.add_argument("--model", default="ai4bharat/indic-parler-tts", help="Hugging Face model ID")
    parser.add_argument("--output", default=None, help="Optional output WAV path")
    args = parser.parse_args()

    import torch
    import soundfile as sf
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
        "fp16": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
    }
    requested_dtype = args.dtype.lower()
    if device == "cuda":
        torch_dtype = dtype_map.get(requested_dtype, torch.float16)
    else:
        # Never float16 on CPU
        if requested_dtype in ("bfloat16", "bf16"):
            torch_dtype = torch.bfloat16
        else:
            torch_dtype = torch.float32

    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model)
        description_tokenizer = AutoTokenizer.from_pretrained(args.model)
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            args.model,
            torch_dtype=torch_dtype,
        )
        model.to(device)
        model.eval()

        sample_rate = getattr(model.config, "sampling_rate", 44100)

        input_ids = description_tokenizer(args.description, return_tensors="pt").input_ids.to(device)
        prompt_input_ids = tokenizer(args.text, return_tensors="pt").input_ids.to(device)

        with torch.no_grad():
            generation = model.generate(
                input_ids=input_ids,
                prompt_input_ids=prompt_input_ids,
            )

        audio_arr = generation.to(torch.float32).cpu().numpy().squeeze()
    except (torch.cuda.OutOfMemoryError, MemoryError, RuntimeError) as e:
        if "out of memory" in str(e).lower() or isinstance(e, (torch.cuda.OutOfMemoryError, MemoryError)):
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            sys.stderr.write(f"CUDA out of memory in TTS worker: {e}\n")
            sys.exit(137)
        raise



    if args.output:
        sf.write(args.output, audio_arr, sample_rate, format="WAV", subtype="PCM_16")
    else:
        wav_buf = io.BytesIO()
        sf.write(wav_buf, audio_arr, sample_rate, format="WAV", subtype="PCM_16")
        wav_buf.seek(0)
        sys.stdout.buffer.write(wav_buf.read())

if __name__ == "__main__":
    main()
