# 09 — Error Handling & Resilience Specification

## Project: SenseAI Voice Assistant
**Phase 14 — System Resilience, Fault Tolerance, and Graceful Degradation**

---

## 1. System Resilience Architecture & Principles

The SenseAI pipeline is designed around **fault containment and graceful degradation**. A single downstream failure (e.g., local model server outage, corrupted vector index, or uninstalled language module) must never crash the FastAPI process or leave client audio connections hanging indefinitely.

### Core Principles
1. **Bounded Retries with Fast-Fail**: Transient network or CUDA hiccups are retried 2–3 times with brief backoff (10ms–200ms). Never retry silently forever.
2. **Circuit Breaking on External Engines**: If a downstream service (`llama.cpp`) fails consecutively, cut off calls immediately and return an explicit unavailable status during a cooldown period.
3. **Graceful Sub-System Degradation**: The voice loop continues operating at the highest available capability tier:
   - If Hindi/Indic ASR fails to load $\to$ degrade to English/global ASR (SenseVoiceSmall).
   - If RAG vector search fails $\to$ degrade to direct conversational chat (Qwen3).
   - If neural TTS generation fails $\to$ degrade to synthesized harmonic acoustic tones.
4. **VRAM Backpressure Control**: Single-GPU environments enforce strict concurrency limits via asynchronous semaphores, queuing extra speech sessions rather than provoking CUDA Out-of-Memory (OOM) fatal crashes.

---

## 2. Failure Mode & Resilience Matrix

| Failure Mode | Root Causes | Resilience Mechanism | Degraded Behavior | Client Impact |
| :--- | :--- | :--- | :--- | :--- |
| **`llama.cpp` Down / Unreachable** | Port 8080 closed, server crashed, process starting | Retry 2x (0.2s, 0.4s backoff). Circuit breaker trips to `OPEN` after 3 consecutive failures. | Circuit breaker trips; fails fast (<50ms). Serves status text: *"The language reasoning service is temporarily unavailable."* | Client receives spoken notification; connection remains alive. |
| **`llama.cpp` Circuit Breaker Tripped** | 3 consecutive upstream request failures | Fast-fail without network call for 15.0s cooldown. Half-open probe resets on success. | Immediate return of unavailable response; zero HTTP wait time. | Zero latency lag on client; prompt audio delivered immediately. |
| **Indic Parler-TTS Generation Error** | CUDA OOM, PyTorch tensor error, missing weights | Retry 2x (50ms backoff). Fail-fast to `_generate_fallback_audio_wav`. | Synthesizes emotion-modulated harmonic tones matching detected sentiment. | Spoken audio replaced by distinct acoustic chime; transcript visible. |
| **IndicConformer Load Failure** | Missing NeMo/PyTorch dependencies, corrupt weights | `ModelManager` catches exception at boot; sets `is_loaded=False`; logs warning. | `LanguageRouter` detects unloaded state and serves utterance via SenseVoiceSmall. | Hindi audio transcribed via SenseVoice; English completely unaffected. |
| **FAISS Vector Index Missing / Corrupt** | Index not yet generated (`build_rag_index.py` unrun), missing `index.faiss` | `IntentRouter` and `VoicePipeline` inspect `retriever.is_loaded`. | Intent dynamically downgraded from `knowledge` to `chat`. | Assistant answers conversationally via LLM rather than throwing an unhandled 500 error. |
| **High Concurrent Voice Sessions** | Multiple browser clients speaking simultaneously | `GPUConcurrencyLimiter` (`asyncio.Semaphore(2)`). | Incoming turns exceeding capacity wait in in-memory queue. | Micro-delay in TTFT/TTFA; no VRAM OOM or driver crash. |
| **Client Audio Duration Exceeded** | Continuous background noise or mic left unmuted (>30s) | `SessionRateLimiter.validate_audio_chunk` | Discards buffer, resets VAD segmenter, emits `AUDIO_DURATION_LIMIT_EXCEEDED`. | Client receives clean warning frame; transport stays connected. |
| **Unauthorized Session Handshake** | Missing or expired JWT when `REQUIRE_AUTH=True` | `validate_token` during transport connection | Rejects WebSocket with close code `1008` (Policy Violation). | Client redirected to re-authenticate. |

---

## 3. Circuit Breaker Specification (`llama_cpp`)

Implemented in `src/backend/llm/circuit_breaker.py`.

```text
    +-------------------------+
    |         CLOSED          |<--------------------------+
    | (Normal HTTP Execution) |                           |
    +------------+------------+                           |
                 |                                        |
                 | [failure_count >= 3]                   |
                 ▼                                        |
    +-------------------------+                           |
    |          OPEN           |                           | [Probe Succeeded]
    |    (Fast-Fail Mode,     |                           |
    |   15s Cooldown Active)  |                           |
    +------------+------------+                           |
                 |                                        |
                 | [cooldown elapsed >= 15s]              |
                 ▼                                        |
    +-------------------------+                           |
    |        HALF_OPEN        |                           |
    |  (Single Trial Probe)   |---------------------------+
    +------------+------------+
                 |
                 | [Probe Failed]
                 ▼
          (Trip back to OPEN)
```

### State Definitions
- **`CLOSED`**: All streaming calls pass to `http://127.0.0.1:8080/v1/chat/completions`. Every successful turn resets `failure_count = 0`.
- **`OPEN`**: Network calls are strictly bypassed. `can_execute()` returns `False`. The client receives an instantaneous fallback notification without hanging up to the 30-second socket timeout.
- **`HALF_OPEN`**: Exactly one trial probe is permitted. If it succeeds, the state transitions back to `CLOSED`. If it fails, the circuit trips back to `OPEN` for another cooldown cycle.

---

## 4. Bounded Retries & Exponential Backoff

All network and GPU-bound operations enforce strict retry ceilings:

### LLM Streaming Invocations (`LlamaCppClient`)
- **Max Retries**: 2 attempts (total 3 tries).
- **Backoff Formulation**: `delay = backoff_factor * (2 ** attempt)` where `backoff_factor = 0.2s`.
- **Delays**:
  - Attempt 1: immediate.
  - Attempt 2: 0.20s backoff.
  - Attempt 3: 0.40s backoff.
- **Total Max Overhead**: ~0.60s before circuit breaker failure recording and fast-fail.

### Neural TTS Generation (`IndicParlerTTS`)
- **Max Retries**: 2 attempts (total 3 tries).
- **Backoff Formulation**: 50ms linear pause.
- **Fail-Safe Target**: `_generate_fallback_audio_wav` (local NumPy harmonic chime generator).

---

## 5. Graceful Degradation Invariants

### 5.1 IndicConformer $\to$ SenseVoice Fallback
When initializing `ModelManager`:
```python
try:
    self.indic_conformer = IndicConformerASR(...)
except Exception as e:
    logger.warning("IndicConformer unavailable; falling back to SenseVoice English/global")
    self.indic_conformer = None
```
In `LanguageRouter`:
- Any Devanagari or low-confidence script evaluates `if self.indic_conformer and self.indic_conformer.is_loaded:`.
- If `False`, `LanguageRouter` falls back to `SenseVoiceASR` and outputs `model_used="sensevoice"`. The pipeline continues without interruption.

### 5.2 RAG $\to$ Direct Chat Fallback
In `IntentRouter` and `VoicePipeline`:
- When user query matches `KNOWLEDGE_PATTERNS` (e.g. *"according to the manual"*):
- If `retriever is None` or `not retriever.is_loaded`:
  - `IntentRouter` logs a warning and maps the request to `IntentCategory.CHAT` (`matched_rule="knowledge_fallback"`).
  - `VoicePipeline` executes direct Qwen3 LLM reasoning without raising index errors or attempting vector retrieval on non-existent FAISS indexes.

---

## 6. GPU Concurrency & Resource Backpressure

In `src/backend/pipeline/concurrency.py`:
- **Default Limit**: `MAX_CONCURRENT_GPU_CALLS = 2`.
- **Target Operations**: Autoregressive token generation (`stream_response`) and sentence-level acoustic synthesis (`synthesize_wav`).
- **Telemetry**: Monitored via `GPUConcurrencyLimiter.get_stats()`:
  - `active_calls`: Number of tasks actively computing on GPU.
  - `queued_calls`: Number of sessions waiting for GPU slot.
  - `total_acquired`: Cumulative session count.
- **Guaranteed Behavior**: Under heavy multi-user load, requests execute FIFO with slight latency degradation, completely eliminating GPU out-of-memory faults.

---

## 7. Transport Layer Error Propagation

When an error occurs during an active WebSocket `/ws/voice` connection:

### Recoverable Operational Error (Rate Limit / Buffer Overflow)
```json
{
  "type": "error",
  "error_code": "AUDIO_DURATION_LIMIT_EXCEEDED",
  "message": "Utterance audio exceeded 30.0s limit.",
  "conversation_id": "session-123",
  "recoverable": true
}
```
*Client action*: Reset mic state, update UI warning badge, maintain WebSocket connection.

### Upstream Service Downtime (LLM / Model Failure)
Rather than closing the socket, the pipeline delivers synthesized speech:
1. `{"type": "sentence_start", "text": "The language reasoning service is temporarily unavailable. Please try again shortly."}`
2. Binary WAV audio frame synthesized via harmonic chime fallback.
3. `{"type": "turn_complete", "status": "degraded"}`
*Client action*: Spoken error audible to user; prompt input re-enabled for immediate retry.
