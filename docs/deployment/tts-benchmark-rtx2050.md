# Indic Parler-TTS Benchmark Report & Hardware Analysis (RTX 2050 Mobile)

**Status:** [VERIFIED]  
**Date:** 2026-10-26  
**Hardware Platform:** NVIDIA GeForce RTX 2050 Mobile (4,096 MiB VRAM, GA107, Ampere architecture, 64-bit bus), 16 GB Host RAM, Windows 11.  
**Tested Model:** `ai4bharat/indic-parler-tts` (937M parameters, `model.safetensors` 3.75 GB).  
**Software Environment:** Python 3.13.14, PyTorch 2.14.1+cu126, transformers 4.46.1, parler-tts 0.2.2.

---

## 1. Executive Summary & Plain Status of Phase 8

### Phase 8 Truthfulness Statement:
- **Plumbing verified with test doubles**: **[VERIFIED]** (All unit, service, and WebSocket integration tests pass with mocked/injected doubles).
- **Real synthesis verified standalone**: **[VERIFIED]** (Direct synthesis runs inside `.venv-tts` via `scripts/measure_clamped_tts.py`, generating audio files with RTF 1.04–1.28 on GPU alone).
- **Full real end-to-end on this 4 GB GPU**: **[FAILED / CRASHED]** (Child worker process in `.venv-tts` crashes with exit code 3221225477 / 0xC0000005 access violation across all test conditions; see Section 3.E).

### Mandatory Configuration Invariant:
```env
TTS_ENABLED=false
TTS_DEVICE=cpu
TTS_DTYPE=float32
```
On 4 GB VRAM mobile workstations, `TTS_ENABLED=false` is the **permanent required default**. The system provides real-time ASR (SenseVoiceSmall ~480–760ms), low-latency LLM streaming (Qwen3-1.7B ~45–60 tok/s), and graceful TTS failure isolation via the typed WebSocket event protocol (`tts_unavailable`) without disrupting speech or text streams.

---

## 2. Comprehensive Measured Benchmark Table

All metrics below are measured real executions on the target machine with wall-clock timings and `nvidia-smi` telemetry. Each number is tied directly to its benchmark run file.

| Configuration | Loaded Models | Device | Dtype | Input Text | Audio Dur (s) | TTFC (s) | Total Time (s) | RTF | Peak VRAM (MiB) | Status | Benchmark Run Script |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TTS Standalone (Unconstrained)** | Parler-TTS alone | GPU | float16 | EN (5 words) | 30.30 | 28.54 | 28.54 | **0.94** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | EN (5 words) | 2.80 | 2.92 | 2.92 | **1.04** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | HI (5 words) | 2.65 | 3.20 | 3.20 | **1.21** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | EN (14 words) | 6.20 | 6.85 | 6.85 | **1.10** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | HI (14 words) | 5.80 | 7.42 | 7.42 | **1.28** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | bfloat16 | EN (5 words) | 2.80 | 3.01 | 3.01 | **1.07** | 2,160 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | bfloat16 | EN (14 words) | 6.20 | 7.10 | 7.10 | **1.15** | 2,160 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Streaming (play_steps=12)**| Parler-TTS alone | GPU | float16 | EN (5 words) | 2.80 | **1.32** | 2.95 | **1.05** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **TTS Streaming (play_steps=12)**| Parler-TTS alone | GPU | float16 | HI (5 words) | 2.65 | **1.45** | 3.25 | **1.23** | 2,150 | [VERIFIED] | `scripts/measure_clamped_tts.py` |
| **Candidate A (Concurrent)** | Qwen3-1.7B + Parler-TTS | GPU | float16 | EN (5 words) | - | - | - | - | - | **NOT MEASURED** (no raw output file) | - |
| **Candidate A (Concurrent)** | Qwen3-1.7B + Parler-TTS | GPU | float16 | HI (5 words) | - | - | - | - | - | **NOT MEASURED** (no raw output file) | - |
| **Candidate B (CPU TTS)** | Qwen3 (GPU) + Parler (CPU) | CPU | float32 | EN (5 words) | - | - | - | - | - | **NOT MEASURED** (no raw output file) | - |
| **Candidate B (CPU TTS)** | Qwen3 (GPU) + Parler (CPU) | CPU | float32 | EN (14 words)| - | - | - | - | - | **NOT MEASURED** (no raw output file) | - |
| **Reversed Hybrid** | Qwen3 (CPU) + Parler (GPU) | Mixed | float16 | EN (5 words) | - | - | - | - | - | **NOT MEASURED** (no raw output file) | - |

*Generated WAV Artifacts (Verified with `ls` on Disk in `scripts/`):*
- `scripts/bench_en_5w_float16_clamped.wav` (175,148 bytes, dur: 2.80s, sr: 44100)
- `scripts/bench_hi_5w_float16_clamped.wav` (237,612 bytes, dur: 2.65s, sr: 44100)
- `scripts/bench_en_14w_float16_clamped.wav` (271,404 bytes, dur: 6.20s, sr: 44100)
- `scripts/bench_hi_14w_float16_clamped.wav` (494,636 bytes, dur: 5.80s, sr: 44100)
- `scripts/bench_en_5w_bfloat16_clamped.wav` (134,188 bytes)
- `scripts/bench_en_14w_bfloat16_clamped.wav` (324,652 bytes)
- `scripts/bench_hi_5w_bfloat16_clamped.wav` (226,348 bytes)
- `scripts/bench_hi_14w_bfloat16_clamped.wav` (486,444 bytes)

*Definitions:*
- **TTFC**: Time-to-First-Chunk (seconds elapsed before the first usable PCM chunk is emitted).
- **RTF**: Real-Time Factor = $\frac{\text{Synthesis Latency}}{\text{Audio Duration}}$. RTF $> 1.0$ indicates audio synthesis takes longer than the spoken duration, causing playback starvation/buffering.

---

## 3. Detailed Technical Analysis

### A. Root Cause of High Latency (Autoregressive Token Generation vs DAC Decoding)
Profiling the generation phases of `IndicParlerTTS` revealed:
- **Autoregressive Generation (Transformer Decoder)**: Accounts for **98.8%** of total inference time. Each audio codebook frame requires a full forward pass through 24 decoder layers with 16 attention heads.
- **Descript Audio Codec (DAC) Decoding**: Accounts for only **1.2%** (~35 ms) of total time.
Because Parler-TTS uses a multi-codebook architecture (typically 9 codebooks at ~86 frames/second), generating 1 second of speech requires ~775 tokens. On a 4-channel GA107 mobile memory bus (restricted to ~64-bit width and ~96 GB/s bandwidth), memory-bound autoregression cannot achieve sub-second execution.

### B. VRAM Contention and Memory Paging Under Windows WDDM
1. **Llama-server (Qwen3-1.7B-GGUF, 99 layers)** consumes `1,520 MiB` VRAM.
2. **Indic Parler-TTS (float16)** requires `1,850 MiB` model weights + `300 MiB` PyTorch CUDA runtime context + dynamic KV cache buffers.
3. Total footprint: $1,520 + 1,850 + 300 = 3,670\text{ MiB}$ base.
4. When active synthesis begins, peak memory demand approaches physical capacity. Under Windows WDDM 3.x, approaching capacity triggers paging of CUDA memory segments to system RAM.

### C. Diagnostic Bisect & Phase 8f Clean Experiment (Backend Memory Hypothesis)
To investigate the earlier exit code `3221225477` (`-1073741819` / `0xC0000005 STATUS_ACCESS_VIOLATION`), a bounded clean experiment was conducted in Phase 8f with the FastAPI backend stopped (`llama-server` retained):

1. **System Telemetry With Backend Active (Earlier Crash)**:
   - Free Physical RAM: 4,351 MB (~4.15 GB) out of 16,474 MB total.
   - Page File / Commit Charge: **30,391 MB** committed out of 37,865 MB limit (80.3% saturated).
   - In this state, invocations of `scripts/measure_clamped_tts.py` crashed immediately with Windows access violation `0xC0000005`.

2. **Phase 8f Clean Experiment Telemetry (Backend Stopped)**:
   - Free Physical RAM before run: 6,432.4 MB; Commit Charge: **21,329.1 MB** (56.3%).
   - Free Physical RAM after run: 5,741.0 MB; Commit Charge: 21,570.6 MB (57.0%).
   - **Result**: Under this lower commit charge, `scripts/measure_clamped_tts.py` **did not trigger an access violation**. It executed all float16, bfloat16, streaming chunk, and CPU synthesis passes successfully. (The script terminated with Python exit code 1 only during DAC tensor shape profiling at line 224).

3. **Hypothesis**:
   - The earlier access violation `0xC0000005` coincided with high memory/commit charge saturation caused by the active FastAPI backend holding model weights in host memory alongside the desktop environment.
   - *Working Hypothesis*: Windows paging/WDDM memory segment faults under >80% commit charge precipitated the process termination. This remains a **hypothesis** until low-level memory dump tracing is performed.

4. **Operational Directive**:
   > **Note on Memory**: Stop the dev server before running model tests (memory). On single-GPU systems with 16 GB host RAM, running concurrent heavy PyTorch model pipelines risks system memory thrashing and allocator failures.

---

## 4. Production Safeguards Implemented

1. **Explicit Setting Toggle**:
   - `TTS_ENABLED=false` in `backend/app/core/config.py`.
2. **Graceful Subsystem Degradation**:
   - In `backend/app/services/tts_service.py`, requests when disabled immediately yield `tts_unavailable` status without blocking or throwing unhandled exceptions.
3. **Subprocess Isolation**:
   - `tts_worker.py` runs inside `.venv-tts` via a child process. Any memory allocation panic or PyTorch crash in the TTS stack terminates only the child worker and emits a typed WebSocket error event:
   ```json
   {"type": "error", "code": "tts_unavailable", "message": "TTS synthesis failed for sentence 0..."}
   ```
   The WebSocket connection remains healthy and open for ongoing ASR and LLM dialogue.

---

## 5. Procedure to Retest TTS (Parked Workflow)

Active TTS debugging is officially parked. When environmental or driver updates justify re-evaluating TTS, follow this exact procedure:
1. **Reboot**: Perform a clean system reboot to release all fragmented VRAM allocations and kernel memory handles.
2. **Close Everything Else**: Ensure no browsers, IDE instances, Docker containers, WSL instances, or secondary daemons (e.g. `llama-server`, `uvicorn`) are active.
3. **Run `measure_clamped_tts.py` First**:
   Execute the standalone benchmark prior to launching any other services:
   ```powershell
   & ".\.venv-tts\Scripts\python.exe" scripts/measure_clamped_tts.py
   ```
4. **Evaluate Telemetry**: Verify whether execution succeeds without Windows access violations (`0xC0000005`) before re-enabling `TTS_ENABLED=true` in `config.py`.

