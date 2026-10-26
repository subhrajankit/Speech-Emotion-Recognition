"""
Fair Benchmark: CTC vs RNNT on IndicConformer-600m
Runs in a single process with identical thread settings.
- 1 warm-up call per mode
- 5 timed runs per mode on tests/samples/sample_hindi_speech.wav
- Records median, min, max, transcript each time, and working set RAM.
- Report-only experiment: prepends 300ms silence to test if 'नमस्ते' is recovered.
"""

import ctypes
import os
import time
from ctypes import wintypes
import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import numpy as np
import soundfile as sf
import torch

from ai.inference.indicconformer import IndicConformerSpeechEngine


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def get_working_set_mb() -> float:
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hProc = kernel32.OpenProcess(0x0400 | 0x0010, False, os.getpid())
    kernel32.K32GetProcessMemoryInfo(hProc, ctypes.byref(pmc), pmc.cb)
    kernel32.CloseHandle(hProc)
    return round(pmc.WorkingSetSize / (1024 * 1024), 2)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    wav_path = Path("tests/samples/sample_hindi_speech.wav")
    if not wav_path.exists():
        raise FileNotFoundError(f"Missing {wav_path}")

    audio_raw, sr = sf.read(str(wav_path), dtype="float32")
    if audio_raw.ndim > 1:
        audio_raw = np.mean(audio_raw, axis=-1)

    # Resample to 16kHz if needed
    if sr != 16000:
        num_target = int(len(audio_raw) * 16000 / sr)
        audio_raw = np.interp(
            np.linspace(0, len(audio_raw), num_target, endpoint=False),
            np.arange(len(audio_raw)),
            audio_raw
        ).astype(np.float32)
        sr = 16000

    duration_s = len(audio_raw) / sr

    print("=================================================================")
    print("INDICCONFORMER-600M FAIR BENCHMARK: CTC vs RNNT")
    print("=================================================================")
    print(f"File: {wav_path} ({len(audio_raw)} samples, 16000 Hz, {duration_s:.2f}s)")
    print(f"PyTorch Version: {torch.__version__}, Threads: {torch.get_num_threads()}")
    print(f"Initial Process RAM: {get_working_set_mb()} MB\n")

    # Load engine once
    print("Loading IndicConformer engine...")
    engine = IndicConformerSpeechEngine(device="cpu", auto_load=True)
    print(f"Model loaded. Current Process RAM: {get_working_set_mb()} MB\n")

    results = {}

    for mode in ["rnnt", "ctc"]:
        print(f"-----------------------------------------------------------------")
        print(f"Testing Mode: {mode.upper()}")
        print(f"-----------------------------------------------------------------")
        engine.decoder_type = mode

        # Warm-up call
        print(f"Executing warm-up run for {mode.upper()}...")
        t0 = time.perf_counter()
        warmup_res = engine.transcribe(audio_raw, sample_rate=sr, language_hint="hi")
        t_warmup = (time.perf_counter() - t0) * 1000
        print(f"Warm-up complete: {t_warmup:.1f} ms | Transcript: '{warmup_res.transcript}' | RAM: {get_working_set_mb()} MB")

        latencies = []
        transcripts = []
        rams = []

        for i in range(1, 6):
            t0 = time.perf_counter()
            res = engine.transcribe(audio_raw, sample_rate=sr, language_hint="hi")
            t_ms = (time.perf_counter() - t0) * 1000
            ram_mb = get_working_set_mb()
            latencies.append(t_ms)
            transcripts.append(res.transcript)
            rams.append(ram_mb)
            print(f"  Run {i}: {t_ms:.1f} ms | RAM: {ram_mb:.1f} MB | Transcript: '{res.transcript}'")

        results[mode] = {
            "latencies": latencies,
            "transcripts": transcripts,
            "rams": rams,
            "min": round(min(latencies), 1),
            "median": round(float(np.median(latencies)), 1),
            "max": round(max(latencies), 1),
            "final_ram": rams[-1],
        }
        print(f"Summary {mode.upper()}: min={results[mode]['min']} ms, median={results[mode]['median']} ms, max={results[mode]['max']} ms\n")

    # Experiment: Prepend 300ms silence
    print("=================================================================")
    print("REPORT-ONLY EXPERIMENT: PREPEND 300ms SILENCE")
    print("=================================================================")
    silence_300ms = np.zeros(int(sr * 0.3), dtype=np.float32)
    audio_padded = np.concatenate([silence_300ms, audio_raw])
    padded_dur = len(audio_padded) / sr
    print(f"Padded audio: {len(audio_padded)} samples ({padded_dur:.2f}s, +300ms prepended silence)")

    for mode in ["rnnt", "ctc"]:
        engine.decoder_type = mode
        t0 = time.perf_counter()
        res_padded = engine.transcribe(audio_padded, sample_rate=sr, language_hint="hi")
        t_ms = (time.perf_counter() - t0) * 1000
        has_namaste = "नमस्ते" in res_padded.transcript
        print(f"Mode {mode.upper()} with 300ms prepended silence:")
        print(f"  Time: {t_ms:.1f} ms")
        print(f"  Transcript: '{res_padded.transcript}'")
        print(f"  'नमस्ते' recovered? {has_namaste}")

    print("\nBenchmark and experiment run complete.")


if __name__ == "__main__":
    main()
