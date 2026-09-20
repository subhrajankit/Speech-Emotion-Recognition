"""
Benchmark script for Phase 1: Base Speech Preprocessing & Silero VAD.
Measures cold start vs warm latency over sample recordings.
"""

import sys
import time
from pathlib import Path

# Ensure repo root is importable
_repo_root = str(Path(__file__).parent.parent.resolve())
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import numpy as np
from ai.preprocessing.audio import load_and_preprocess_audio
from ai.preprocessing.vad import SileroVAD


def run_benchmark():
    print("=== Phase 1 Pipeline Latency Benchmark ===")

    # 1. Cold start measurement
    t0 = time.perf_counter()
    vad = SileroVAD()
    audio = load_and_preprocess_audio("tests/samples/sample_chinese_speech.wav")
    cold_result = vad.analyze(audio)
    cold_ms = (time.perf_counter() - t0) * 1000.0

    print(f"Cold Start Latency (ONNX session creation + Audio Decode + VAD inference): {cold_ms:.2f} ms")
    print(f"Cold Result: has_speech={cold_result.has_speech}, speech_ms={cold_result.speech_duration_ms}ms, prob={cold_result.speech_probability}")

    # 2. Warm inference runs (5 iterations)
    warm_latencies = []
    for i in range(5):
        t_start = time.perf_counter()
        res = vad.analyze(audio)
        elapsed = (time.perf_counter() - t_start) * 1000.0
        warm_latencies.append(elapsed)

    mean_warm = float(np.mean(warm_latencies))
    min_warm = float(np.min(warm_latencies))
    max_warm = float(np.max(warm_latencies))

    print(f"Warm Inference Latency (6.0s audio):")
    print(f"  Mean: {mean_warm:.2f} ms")
    print(f"  Min:  {min_warm:.2f} ms")
    print(f"  Max:  {max_warm:.2f} ms")
    print(f"  Real-Time Factor (RTF): {mean_warm / 6000.0:.4f}")

    # 3. Audio Preprocessing breakdown
    t_pre0 = time.perf_counter()
    for _ in range(5):
        load_and_preprocess_audio("tests/samples/sample_chinese_speech.wav")
    pre_ms = ((time.perf_counter() - t_pre0) / 5.0) * 1000.0
    print(f"Audio Preprocessing Latency (Decode + Mono + Resample + Norm): {pre_ms:.2f} ms")


if __name__ == "__main__":
    run_benchmark()
