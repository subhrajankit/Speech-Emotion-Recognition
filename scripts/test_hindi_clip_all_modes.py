import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import json
import soundfile as sf
import numpy as np
import time
import asyncio

from ai.inference.indicconformer import IndicConformerSpeechEngine
from ai.preprocessing.audio import load_and_preprocess_audio
from backend.app.services.speech_service import speech_service

WAV_PATH = "tests/samples/sample_hindi_speech.wav"
GROUND_TRUTH = "नमस्ते, आज मौसम बहुत अच्छा है।"

print("=" * 80)
print("PHASE 8c: HINDI AUDIO REAL VERIFICATION (ai4bharat/indic-conformer-600m-multilingual)")
print(f"Target Clip: {WAV_PATH}")
print(f"Ground Truth Spoken Sentence: \"{GROUND_TRUTH}\"")
print("=" * 80)

# Load audio
audio_16k = load_and_preprocess_audio(WAV_PATH)
info = sf.info(WAV_PATH)
print(f"Audio Properties: duration={len(audio_16k)/16000:.2f}s, original_sr={info.samplerate}, resampled_sr=16000")

# 1. Direct Engine Test
print("\n--- 1. DIRECT ENGINE TEST (IndicConformerSpeechEngine) ---")
indic_engine = IndicConformerSpeechEngine(
    model_dir="ai4bharat/indic-conformer-600m-multilingual",
    device="cpu",
    decoder_type="rnnt",
    auto_load=True
)

t0 = time.perf_counter()
direct_res = indic_engine.transcribe(audio_16k, language_hint="hi")
t_direct = time.perf_counter() - t0

print(f"Real Transcript: \"{direct_res.transcript}\"")
print(f"Ground Truth:    \"{GROUND_TRUTH}\"")
print(f"Language: {direct_res.language} | Emotion: {direct_res.emotion} (invariant=None)")
print(f"Processing Time: {direct_res.processing_time_ms} ms (wall-clock: {t_direct:.2f}s)")
print(f"Model Version: {direct_res.model_version}")

# Read raw PCM bytes for service tests
with open(WAV_PATH, "rb") as f:
    # Use load_and_preprocess_audio converted to int16 PCM bytes
    pcm16_bytes = (audio_16k * 32767.0).astype(np.int16).tobytes()

async def run_service_tests():
    speech_service.initialize()
    # 2. Through SpeechService with language_hint="hi"
    print("\n--- 2. ROUTER WITH language_hint=\"hi\" ---")
    t1 = time.perf_counter()
    res_hi = await speech_service.transcribe_pcm16_bytes(
        pcm_bytes=pcm16_bytes,
        sample_rate=16000,
        language_hint="hi"
    )
    t_hi = time.perf_counter() - t1
    print(f"Transcript: \"{res_hi.transcript}\"")
    print(f"Routing debug: {res_hi.debug.get('routing')}")
    print(f"Fallback debug: {res_hi.debug.get('fallback')}")
    print(f"Language: {res_hi.language} | Emotion: {res_hi.emotion}")
    print(f"Processing Time: {res_hi.processing_time_ms} ms")

    # 3. Through SpeechService with NO hint (language_hint=None)
    print("\n--- 3. ROUTER WITH NO HINT (language_hint=None) ---")
    t2 = time.perf_counter()
    res_none = await speech_service.transcribe_pcm16_bytes(
        pcm_bytes=pcm16_bytes,
        sample_rate=16000,
        language_hint=None
    )
    t_none = time.perf_counter() - t2
    print(f"Transcript: \"{res_none.transcript}\"")
    print(f"Routing debug: {res_none.debug.get('routing')}")
    print(f"Fallback debug: {res_none.debug.get('fallback')}")
    print(f"Language: {res_none.language} | Emotion: {res_none.emotion}")
    print(f"Processing Time: {res_none.processing_time_ms} ms")

asyncio.run(run_service_tests())
