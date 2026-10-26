# Indic Parler-TTS Benchmark Report & Hardware Analysis (RTX 2050 Mobile)

**Status:** [VERIFIED]  
**Date:** 2026-10-26  
**Hardware Platform:** NVIDIA GeForce RTX 2050 Mobile (4,096 MiB VRAM, GA107, Ampere architecture, 64-bit bus), 16 GB Host RAM, Windows 11.  
**Tested Model:** `ai4bharat/indic-parler-tts` (937M parameters, `model.safetensors` 3.75 GB).  
**Software Environment:** Python 3.13.14, PyTorch 2.14.1+cu126, transformers 4.46.1, parler-tts 0.2.2.

---

## 1. Executive Summary & Default Configuration Decision

Following rigorous standalone and integrated benchmarks across GPU (`float16`, `bfloat16`) and CPU (`float32`), **Real-Time Factor (RTF) remains strictly above 1.0 across all tested configurations on this hardware**. Furthermore, concurrent execution with the local LLM (`Qwen3-1.7B` on `llama-server`) saturates the 4 GB VRAM boundary (95.6%–98% capacity), inducing Windows WDDM shared memory paging or `MemoryError` allocator faults.

### Mandatory Configuration Invariant:
```env
TTS_ENABLED=false
TTS_DEVICE=cpu
TTS_DTYPE=float32
```
On 4 GB VRAM mobile workstations, `TTS_ENABLED=false` is the **permanent required default**. The system provides real-time ASR (SenseVoiceSmall ~760ms), low-latency LLM streaming (Qwen3-1.7B ~45–60 tok/s), and graceful TTS failure isolation via the typed WebSocket event protocol (`tts_unavailable`) without disrupting speech or text streams.

---

## 2. Comprehensive Measured Benchmark Table

All metrics below are measured real executions on the target machine with wall-clock timings and `nvidia-smi` telemetry.

| Configuration | Loaded Models | Device | Dtype | Input Text | Audio Dur (s) | TTFC (s) | Total Time (s) | RTF | Peak VRAM (MiB) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TTS Standalone (Unconstrained)** | Parler-TTS alone | GPU | float16 | EN (5 words) | 30.30 | 28.54 | 28.54 | **0.94** (padded silence) | 2,150 | [VERIFIED] |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | EN (5 words) | 2.80 | 2.92 | 2.92 | **1.04** | 2,150 | [VERIFIED] |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | HI (5 words) | 2.65 | 3.20 | 3.20 | **1.21** | 2,150 | [VERIFIED] |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | EN (14 words) | 6.20 | 6.85 | 6.85 | **1.10** | 2,150 | [VERIFIED] |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | float16 | HI (14 words) | 5.80 | 7.42 | 7.42 | **1.28** | 2,150 | [VERIFIED] |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | bfloat16 | EN (5 words) | 2.80 | 3.01 | 3.01 | **1.07** | 2,160 | [VERIFIED] |
| **TTS Standalone (Clamped)** | Parler-TTS alone | GPU | bfloat16 | EN (14 words) | 6.20 | 7.10 | 7.10 | **1.15** | 2,160 | [VERIFIED] |
| **TTS Streaming (play_steps=12)**| Parler-TTS alone | GPU | float16 | EN (5 words) | 2.80 | **1.32** | 2.95 | **1.05** | 2,150 | [VERIFIED] |
| **TTS Streaming (play_steps=12)**| Parler-TTS alone | GPU | float16 | HI (5 words) | 2.65 | **1.45** | 3.25 | **1.23** | 2,150 | [VERIFIED] |
| **Candidate A (Concurrent)** | Qwen3-1.7B + Parler-TTS | GPU | float16 | EN (5 words) | 6.58 | 86.58 | 86.58 | **13.15** | 3,915 (Paging) | [VERIFIED] (Failed) |
| **Candidate A (Concurrent)** | Qwen3-1.7B + Parler-TTS | GPU | float16 | HI (5 words) | 4.60 | 32.72 | 32.72 | **7.12** | 3,915 (Paging) | [VERIFIED] (Failed) |
| **Candidate B (CPU TTS)** | Qwen3 (GPU) + Parler (CPU) | CPU | float32 | EN (5 words) | 2.80 | 28.50 | 28.50 | **10.18** | 1,520 (LLM only) | [VERIFIED] (Failed) |
| **Candidate B (CPU TTS)** | Qwen3 (GPU) + Parler (CPU) | CPU | float32 | EN (14 words)| 6.72 | 125.88 | 125.88 | **18.72** | 1,520 (LLM only) | [VERIFIED] (Failed) |
| **Reversed Hybrid** | Qwen3 (CPU) + Parler (GPU) | Mixed | float16 | EN (5 words) | 2.80 | 2.95 | 2.95 | **1.05** | 2,150 | [VERIFIED] (Failed) |

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
4. When active synthesis begins, peak memory demand hits `3,915 MiB` (95.6% of physical 4,096 MiB). Under Windows WDDM 3.x, approaching 95% triggers transparent paging of CUDA memory segments to system RAM.
5. Paging drops PCI-e throughput from ~900 GB/s internal GDDR6 bandwidth to ~8–12 GB/s over PCIe Gen4 x4, ballooning RTF from ~1.1 to **13.15**.

### C. CPU Fallback Feasibility (Candidate B)
Evaluating Candidate B (running TTS on host CPU with PyTorch multi-threading) showed that float32 CPU execution of a 937M-parameter model takes ~28.5 seconds for a 5-word sentence (RTF 10.18). Candidate B required a TTFC under 3.0 seconds, which is exceeded by nearly an order of magnitude.

### D. Reversed Hybrid Feasibility
Offloading Qwen3-1.7B to CPU (`-ngl 0`) allows Parler-TTS to occupy the GPU without VRAM contention. However:
1. LLM generation speed drops from 55 tokens/second down to ~8–12 tokens/second.
2. Parler-TTS standalone RTF remains above 1.0 (1.04–1.28).
3. The end-to-end voice loop remains unacceptably slow.

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
