"""
Experiment to evaluate exit code 3221225477 (0xC0000005) under 3 conditions:
Condition (a): llama-server stopped, ASR not loaded on GPU.
Condition (b): llama-server running, ASR not loaded on GPU.
Condition (c): llama-server running, ASR loaded on GPU.
"""

import asyncio
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

def get_nvidia_smi():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
            encoding="utf-8"
        ).strip()
        gpu_summary = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
            encoding="utf-8"
        ).strip()
        return f"Total GPU: {gpu_summary}\nProcesses:\n{out if out else '  (No compute processes)'}"
    except Exception as e:
        return f"nvidia-smi error: {e}"

async def run_tts_trial(label: str):
    print(f"\n{'='*60}")
    print(f"RUNNING TRIAL: {label}")
    print(f"{'='*60}")
    print("GPU state before TTS call:")
    print(get_nvidia_smi())
    print("-" * 60)

    if "Condition (c)" in label:
        print("Loading ASR on GPU for Condition (c)...")
        from backend.app.services.speech_service import speech_service
        speech_service.initialize()
        print("ASR initialized on GPU.")

    from backend.app.core.config import settings
    from backend.app.services.tts_service import tts_service, TTSError, TTSOOMError

    settings.TTS_ENABLED = True
    settings.TTS_DEVICE = "cuda"
    settings.TTS_DTYPE = "float16"
    settings.TTS_SENTENCE_TIMEOUT_SECONDS = 90.0
    tts_service._active_device = "cuda"
    tts_service._is_loaded = False
    tts_service._cooldown_until = 0

    test_sentence = "The quick brown fox jumps over the lazy dog."
    chunks_received = []
    error_encountered = None

    t0 = time.perf_counter()
    try:
        async for chunk in tts_service.synthesize(text=test_sentence, language="en"):
            chunks_received.append(chunk)
            print(f"[CHUNK] Index: {chunk.sentence_index} | Text: '{chunk.sentence_text}' | Bytes: {len(chunk.audio)} | SR: {chunk.sample_rate} | Synth Time: {chunk.synthesis_time_ms:.1f}ms | RTF: {chunk.rtf:.2f}")
    except Exception as e:
        error_encountered = e
        print(f"[ERROR ENCOUNTERED] {type(e).__name__}: {e}")

    elapsed = time.perf_counter() - t0
    print("-" * 60)
    print(f"Trial '{label}' finished in {elapsed:.2f}s")
    print(f"Chunks received: {len(chunks_received)}")
    print("GPU state after TTS call:")
    print(get_nvidia_smi())
    print(f"{'='*60}\n")
    return {
        "label": label,
        "chunks": len(chunks_received),
        "error": str(error_encountered) if error_encountered else None,
        "elapsed_s": elapsed,
    }

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "a"
    asyncio.run(run_tts_trial(f"Condition ({mode})"))
