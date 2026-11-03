# VoiceSense AI — WebSocket Streaming Protocol (v1)

This document defines the official **v1 WebSocket Streaming Protocol** for real-time speech perception over `/ws/speech`.

---

## 1. Connection Endpoint & Handshake

- **Endpoint**: `ws://127.0.0.1:8000/ws/speech`
- **In-Frame Authentication**:
  - In Phase 9+, authentication is performed via the initial `"start"` JSON text frame using the `auth_token` field (RFC 7515 HS256 JWT).
  - Passing authentication tokens via URL query parameters (`?token=...`) is deprecated and removed to prevent credential exposure in web server logs, proxy access logs, and browser histories.
  - When `AUTH_REQUIRED=true`:
    - The `"start"` message frame MUST contain a valid JWT in `auth_token`.
    - Omitting `auth_token` or supplying an invalid/expired token results in an `AUTH_REQUIRED` or `AUTH_FAILED` error frame, followed by immediate connection closure with RFC 6455 close code `1008` (Policy Violation).
  - When `AUTH_REQUIRED=false` (development mode):
    - Supplying `auth_token` associates the session with the authenticated user and persists history.
    - Omitting `auth_token` runs the session anonymously: speech recognition and LLM events function normally, but persistence is completely bypassed (no database records are created for anonymous sessions).

---

## 2. Framing & Message Types

All control messages are formatted as UTF-8 JSON text frames. Audio stream data is transmitted exclusively as raw binary frames.

### A. Client → Server Messages

1. **Session Initialization (`start`)**:
   Sent once to configure the audio stream before transmitting binary audio frames.
   ```json
   {
     "type": "start",
     "sample_rate": 16000,
     "encoding": "pcm_s16le",
     "language_hint": null,
     "auth_token": "<HS256_JWT_ACCESS_TOKEN>"
   }
   ```
   - `sample_rate`: Sample rate in Hz (default: `16000`).
   - `encoding`: Audio encoding format. Currently supported: `"pcm_s16le"` (16-bit signed integer, linear PCM, little-endian, mono).
   - `language_hint`: Optional ISO 639-1 language code hint or `null`:
     - Indic languages (`"hi"`, `"bn"`, `"mr"`, `"ta"`, `"te"`, etc.): routes dynamically to IndicConformer-600m.
     - Global languages (`"en"`, `"zh"`, `"yue"`, `"ja"`, `"ko"`): routes dynamically to SenseVoiceSmall.
     - When `null`: routes according to Spoken LID detection (if confidence $\ge$ threshold) or falls back to SenseVoice default.
   - `auth_token`: Optional (or mandatory if `AUTH_REQUIRED=true`) HS256 JWT access token acquired from `POST /api/auth/login` or `POST /api/auth/register`.

2. **Binary Audio Frames**:
   Continuous binary chunks of raw PCM16 mono audio (e.g. 512 samples / 1024 bytes per chunk at 16kHz).

3. **Session Stop / Utterance Flush (`stop`)**:
   Sent to stop audio streaming or flush any actively buffered speech.
   ```json
   {
     "type": "stop"
   }
   ```

4. **Keepalive Ping (`ping`)**:
   Clients may send application-layer keepalive pings:
   ```json
   {
     "type": "ping"
   }
   ```

---

### B. Server → Client Messages

1. **Session Ready (`ready`)**:
   Sent immediately in response to a valid `start` message.
   ```json
   {
     "type": "ready"
   }
   ```

2. **Keepalive Pong (`pong`)**:
   Sent in response to a client `ping` message.
   ```json
   {
     "type": "pong"
   }
   ```

3. **VAD State Transition (`vad`)**:
   Emitted automatically as server-side Silero VAD detects speech boundaries.
   ```json
   {
     "type": "vad",
     "state": "speech_start"
   }
   ```
   or
   ```json
   {
     "type": "vad",
     "state": "speech_end"
   }
   ```

4. **Lazy Engine Load Status (`status`)**:
   When an engine loads lazily on its first turn, the server emits progressive status frames so the client can display appropriate loading UI:
   - On load start:
     ```json
     {
       "type": "status",
       "state": "loading_model",
       "engine": "sensevoice"
     }
     ```
   - On load completion:
     ```json
     {
       "type": "status",
       "state": "model_ready",
       "engine": "sensevoice"
     }
     ```
   - `engine`: Canonical identifier of the loading engine (`"sensevoice"` or `"indicconformer"`).
   - Subsequent turns do not emit `status` events once the engine is resident in memory.
   - **Configuration Preload**: To eliminate the first-turn lazy-load delay, set `PRELOAD_DEFAULT_ENGINE=true` in `backend/app/core/config.py` or via the environment. When enabled, the default engine (`SenseVoiceSmall`) is loaded once during application startup lifespan.

5. **Speech Perception Result (`speech_result`)**:
   Emitted when a complete speech segment has finished processing through the non-blocking perception engine. Conforms to the unified `SpeechResult` schema.
   ```json
   {
     "type": "speech_result",
     "transcript": "Hello, how are you today?",
     "language": "en",
     "emotion": "happy",
     "confidence": null,
     "processing_time_ms": 766,
     "model_version": "SenseVoiceSmall (funasr)",
     "audio_events": ["Speech"],
     "segments": [],
     "debug": {
       "raw_tags": ["<|en|>", "<|HAPPY|>", "<|Speech|>"],
       "vad_has_speech": true,
       "segment_index": 1,
       "segment_bytes": 64512,
       "segment_duration_s": 2.02,
       "session_total_audio_bytes": 263406,
       "flushed_on_stop": false
     }
   }
   ```

   **Multi-segment VAD Segmentation & Streaming Semantics**:
   - If the user speaks multiple phrases separated by pauses longer than the VAD silence threshold (`silence_timeout_ms = 700ms`), or if un-transcribed audio is flushed at connection close / `stop` frame, the VAD segmenter splits the input stream into distinct utterances.
   - **Each segment produces its own separate `speech_result` event**, followed immediately by its downstream LLM turn.
   - Clients receiving continuous audio streams must NOT expect a single monolithic `speech_result` for an entire multi-utterance session. Each utterance segment has its own `debug.segment_index`, `debug.segment_bytes`, and `debug.segment_duration_s`.

6. **RAG Citations (`rag_sources`)**:
   Emitted when a knowledge query retrieves grounded document chunks from the local vector index:
   ```json
   {
     "type": "rag_sources",
     "sources": [
       {
         "doc_name": "company_policy.md",
         "chunk_id": "chunk_0_1234abcd",
         "score": 0.8845
       }
     ]
   }
   ```

7. **LLM Token Delta (`llm_delta`)**:
   Emitted progressively as each generated token arrives from the local LLM server. Dispatched strictly after `speech_result`.
   ```json
   {
     "type": "llm_delta",
     "delta": "Hello"
   }
   ```

8. **LLM Completion (`llm_done`)**:
   Emitted once the LLM stream has finished, containing the full aggregated response text and any grounded citations:
   ```json
   {
     "type": "llm_done",
     "text": "According to the company policy, the refund window is 30 days.",
     "sources": [
       {
         "doc_name": "company_policy.md",
         "chunk_id": "chunk_0_1234abcd",
         "score": 0.8845
       }
     ]
   }
   ```

9. **TTS Audio Stream Chunk (`tts_chunk` + Binary Frame)**:
   Emitted as each sentence is synthesized by Indic Parler-TTS.
   Each chunk uses a deterministic **two-frame sequence**:
   1. **JSON Metadata Header**: A text JSON frame containing sentence metadata:
      ```json
      {
        "type": "tts_chunk",
        "index": 0,
        "sample_rate": 44100,
        "text": "Hello, how can I help you today?",
        "format": "wav"
      }
      ```
   2. **Binary Audio Frame**: Follows immediately as a raw binary WebSocket frame containing a self-contained 16-bit PCM WAV audio file (with standard 44-byte RIFF/WAVE header), decoded natively by client audio pipelines (e.g. `AudioContext.decodeAudioData`).
   - Sample rate: 44,100 Hz (44.1 kHz, mono).
   - Encoding: 16-bit signed integer linear PCM (`format: "wav"`).

10. **TTS Synthesis Completion (`tts_done`)**:
    Emitted once all synthesized sentences for the turn have finished streaming:
    ```json
    {
      "type": "tts_done",
      "total_chunks": 2,
      "total_duration_ms": 3450.0
    }
    ```

11. **Status Notice (`status`)**:
    Emitted for non-fatal runtime notices, such as when a knowledge query falls back to direct chat due to missing vector indices:
    ```json
    {
      "type": "status",
      "status": "rag_fallback",
      "message": "Knowledge base index unavailable or no relevant chunks found; falling back to direct chat."
    }
    ```

12. **Error Frame (`error`)**:
    Emitted upon protocol violation, buffer overflow, or upstream/service error:
    ```json
    {
      "type": "error",
      "code": "BUFFER_OVERFLOW",
      "message": "Connection buffer limit (5242880 bytes) exceeded."
    }
    ```
    Or when LLM is unreachable, timed out, or in cool-down:
    ```json
    {
      "type": "error",
      "code": "llm_unavailable",
      "message": "Cannot connect to local LLM server at http://127.0.0.1:8080/v1/chat/completions"
    }
    ```
    Or when TTS synthesis is unavailable or encounters an error (including CUDA OOM):
    ```json
    {
      "type": "error",
      "code": "tts_unavailable",
      "message": "TTS model or dependencies unavailable; continuing in text-only mode."
    }
    ```
    > **Note**: An `llm_unavailable` or `tts_unavailable` error keeps the WebSocket connection open so subsequent voice turns can still be transcribed.

13. **Cancellation & Ordering Guarantees**:
    - `speech_result` is always dispatched BEFORE any LLM or TTS request is started and never waits on them.
    - Full event ordering: `speech_result` → `llm_delta...` → `llm_done` → `tts_chunk (JSON)` → `tts_chunk (binary)` ... → `tts_done`.
    - If the client disconnects or transmits a new `start` control frame while `llm_delta` or `tts_chunk` streams are in-flight, the server immediately cancels the active generation/synthesis task, closes upstream streams, and discards queued audio chunks.
    - Non-blocking database turn persistence is dispatched asynchronously in a threadpool worker (`HistoryService.record_voice_turn`) strictly AFTER `speech_result` and `llm_done` are emitted. If the database is unreachable, the error is logged and swallowed; the WebSocket connection remains completely uninterrupted.

---

## 3. Reserved Message Types

The following message types are reserved for telemetry and client controls:
- `status`

Any unknown message types received from the client are safely ignored.

---

## 4. Operational Invariants & Limits

1. **Server-Side VAD Segmentation**:
   Audio chunks are processed through Silero VAD in 512-sample (32ms) frames with a 250ms pre-speech buffer. Speech ends after 700ms of sustained silence.
2. **Buffer Limits**:
   Per-connection memory buffer is capped at **5 MB** (`WS_MAX_BUFFER_BYTES`). Exceeding this threshold triggers an immediate `BUFFER_OVERFLOW` error and buffer reset.
3. **Turn Rate Limiting**:
   Sessions are capped at a maximum of **20 utterances per 60-second sliding window** (`RATE_LIMIT_UTTERANCES_PER_MINUTE`). Exceeding this threshold triggers a `RATE_LIMIT_EXCEEDED` error frame.
4. **Turn Audio Duration Cap**:
   Individual audio turns cannot exceed **30.0 seconds** (`MAX_AUDIO_DURATION_SECONDS`). Audio exceeding this limit is rejected with `AUDIO_DURATION_LIMIT_EXCEEDED`.
5. **Zero Raw Audio Persistence**:
   Raw audio bytes and PCM waveforms are NEVER stored in the database or persisted to disk. Only processed transcripts, acoustic tags, and latency metrics are retained.
6. **Resource Cleanup**:
   Disconnects clean up segmenter state and in-memory buffers immediately.
7. **Non-Blocking Inference**:
   ASR and SER inference runs off the asyncio event loop via threadpools (`asyncio.to_thread`) bounded by an asynchronous semaphore (`INFERENCE_CONCURRENCY_LIMIT`).
