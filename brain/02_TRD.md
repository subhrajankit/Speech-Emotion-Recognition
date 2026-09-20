# 02 — Technical Requirements Document (TRD)

## Project: SenseAI Voice Assistant

---

## 1. System Specifications & Pipeline Stages

```text
[ Mic ] ──► [ Silero VAD ] ──► [ SenseVoiceSmall / IndicConformer ] ──► [ Intent Router ]
                                                                                │
  ┌─────────────────────────────────────────────────────────────────────────────┘
  ├──► Direct LLM (Qwen3-4B) ──────────┐
  ├──► Local RAG (e5-small + FAISS) ───┤
  └──► Command Execution ──────────────┤
                                       ▼
                     [ Qwen3-4B via llama.cpp ] ──► [ Indic Parler-TTS ] ──► [ Client Stream ]
```

---

## 2. Latency Budgets & Target Benchmarks

End-to-end target latency represents time from **User Voice Activity Silence Detection** to **First Audio Frame Played** on the client.

| Pipeline Stage | Component | GPU Mode Target (P95) | CPU Mode Target (P95) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **VAD Silence Detection** | Silero VAD (ONNX) | < 30 ms | < 50 ms | 30ms window frames; 300ms trailing silence threshold. |
| **ASR + SER + AED** | SenseVoiceSmall / IndicConformer | < 120 ms | < 350 ms | Single forward pass yields text, emotion, and acoustic tags. |
| **Language / Hinglish Routing** | Regex + Acoustic Heuristic | < 5 ms | < 10 ms | Deterministic classifier routes Indic/Hinglish to IndicConformer. |
| **Intent Gate** | Lightweight Regex / Embedding Match | < 15 ms | < 25 ms | Explicit branch router: Chat vs RAG vs Command. |
| **RAG Retrieval (Optional)** | `multilingual-e5-small` + FAISS | < 40 ms | < 100 ms | Top-k=3 retrieval over chunked local corpus; skipped in plain chat. |
| **LLM Time-to-First-Token (TTFT)** | Qwen3-4B (Q4_K_M via llama.cpp) | < 180 ms | < 450 ms | Warm context, prompt cache active. |
| **TTS First Chunk Synthesis** | Indic Parler-TTS | < 250 ms | < 600 ms | Streaming sentence/chunk level synthesis with emotion styling. |
| **Transport & Audio Buffer** | WebSocket (PCM16 16/24kHz) | < 30 ms | < 50 ms | Framed binary packets over localhost loopback. |
| **Total End-to-End Latency** | Full Pipeline | **< 670 ms** | **< 1,635 ms** | Meets conversational interaction threshold (< 1.0s on GPU). |

---

## 3. Supported Languages & Speech Models

### 3.1 Global Languages (SenseVoiceSmall)
- **Languages**: English (`en`), Mandarin (`zh`), Cantonese (`yue`), Japanese (`ja`), Korean (`ko`).
- **Capabilities**: Multi-task architecture outputting:
  - Automatic Speech Recognition (ASR).
  - Speech Emotion Recognition (SER): Neutral, Happy, Sad, Angry, Excited, Disgusted, Fearful.
  - Audio Event Detection (AED): Laughter, Cough, Sigh, Applause, Cry, Music, Snore.

### 3.2 Indic Languages (AI4Bharat IndicConformer-600m)
- **Primary**: Hindi (`hi`).
- **Official 21 Scheduled Languages**: Assamese, Bengali, Bodo, Dogri, Gujarati, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, Urdu.
- **Code-Switching (Hinglish)**:
  - Heuristic classifier detects mixed Hindi-English phonetic sequences.
  - Token-level normalization passes blended speech tokens to Qwen3-4B with dual language system context.

---

## 4. Hardware Profiles & Deployment Modes

### 4.1 Profile A: NVIDIA GPU Accelerated (Optimal)
- **Minimum Specs**: 8 GB VRAM (RTX 3060 / 4060 or better), 16 GB System RAM, 4 CPU Cores.
- **Recommended**: 12–16 GB VRAM (RTX 3080 / 4070 / 4080), 32 GB RAM.
- **Allocation**:
  - Qwen3-4B Q4_K_M: ~2.8 GB VRAM.
  - SenseVoiceSmall + Silero: ~0.8 GB VRAM.
  - IndicConformer-600m: ~1.4 GB VRAM (loaded conditionally or warm pool).
  - Indic Parler-TTS: ~2.2 GB VRAM.
  - CUDA Context & Buffers: ~0.6 GB.

### 4.2 Profile B: CPU-Only / Apple Silicon / Low-VRAM (Constrained)
- **Minimum Specs**: 8-core modern x86_64 AVX2 / ARM64, 16 GB RAM.
- **Optimizations**:
  - LLM: Qwen3-4B Q4_K_M via `llama.cpp` using AVX2/AVX-512 / NEON.
  - VAD: ONNX Runtime CPU.
  - ASR: Quantized ONNX / OpenVINO / CTranslate2.
  - TTS: PyTorch quantized CPU inference with reduced chunk lengths.

### 4.3 Profile C: Hybrid Mode
- **Specs**: 4 GB–6 GB VRAM (e.g. GTX 1660 / RTX 3050 Laptop).
- **Allocation**:
  - GPU: Qwen3-1.7B (offload full layers) + Silero VAD.
  - CPU: SenseVoiceSmall, IndicConformer, and Parler-TTS running in thread pools.

### 4.4 GPU Concurrency Budget & Queueing Backpressure (Phase 14)
- **Shared Hardware Constraint**: Designed for single-GPU deployments (e.g. 4GB VRAM RTX 2050 to 16GB VRAM server GPUs) serving concurrent voice clients.
- **Concurrency Limit**: `MAX_CONCURRENT_GPU_CALLS = 2` (default, configurable in `config.py` and `.env`).
- **Enforcement Mechanism**: Managed via an asynchronous semaphore (`GPUConcurrencyLimiter` in `src/backend/pipeline/concurrency.py`).
- **Behavior Under Load**:
  - Simultaneous LLM autoregressive generation and Indic Parler-TTS synthesis calls beyond the semaphore capacity are queued in memory without terminating client connections.
  - Eliminates CUDA Out-Of-Memory (OOM) crashes, GPU context thrashing, and process terminations.
  - Pipeline telemetry (`StageTiming`) records timing to measure queue wait times under high session concurrency.

---

## 5. Security & Data Retention Rules

1. **Audio Ephemerality**:
   - Audio chunks are processed directly in RAM buffers.
   - Immediate disposal: Once transcription and acoustic tagging are complete, raw audio buffers are purged.
   - Zero disk writing for raw `.wav` or audio frames under normal operational cycles.
2. **Persistence Rules**:
   - Transcripts: Stored in SQLite/PostgreSQL with user-controlled session lifecycle.
   - Emotion logs: Stored in `emotion_history` (timestamp, session_id, emotion_label, confidence, detected_events).
   - RAG Documents: Text chunks stored locally in `./database/documents`, vector embeddings in `./database/vector_index.faiss`.
3. **Network Isolation**:
   - All server processes (FastAPI backend, llama.cpp daemon, database) bind strictly to `127.0.0.1`.
   - Explicit prohibition of `0.0.0.0` wildcard interfaces in application configuration.

---

## 6. Non-Functional Requirements (NFRs)

- **Reliability & Crash Resilience**: Backend automatically catches model inference exceptions and gracefully falls back to text-only mode or returns acoustic status messages without terminating WebSocket connections.
- **Model Warm-Up Policy**: All core models (VAD, ASR, LLM, TTS) are initialized once during FastAPI `lifespan` startup. Zero per-request cold-starts allowed.
- **Transport Resilience**:
  - WebSocket protocol handles heartbeats/ping-pong every 15s.
  - Client implements exponential backoff reconnection (1s, 2s, 4s, up to 16s).
- **Testability & Observability**:
  - Every pipeline component exposes isolated test harnesses using mock audio fixtures.
  - Latency instrumentation metrics emitted at every pipeline transition.

---

## 7. Optional Cloud LLM Fallback & Explicit Privacy Exception (Phase 17)

SenseAI provides an **optional, opt-in** cloud LLM provider using Google Gemini 3 Flash (`gemini-2.5-flash` / Gemini API) alongside the primary local Qwen3-1.7B model.

> [!WARNING]
> **Privacy Notice & Cloud Opt-In Exception**:
> - The out-of-the-box and default configuration is strictly **`LLM_PROVIDER=local`**, ensuring 100% private, on-device offline reasoning with zero cloud leakage.
> - **Opt-In Exception**: If a user or operator explicitly enables cloud mode (`LLM_PROVIDER=cloud` in `.env` or toggles the runtime switch in the UI), **spoken transcripts, emotional classification tags, and linguistic context are transmitted to Google's Gemini API**.
> - Cloud mode requires a separate API key from **Google AI Studio** (`GEMINI_API_KEY`). A Google AI Pro / consumer subscription does NOT include API access; billing is managed independently.
> - Cloud mode exists strictly for latency and quality benchmarking comparisons during demos, and does NOT replace the default local pipeline.

