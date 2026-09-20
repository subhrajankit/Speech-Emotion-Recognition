# VoiceSense AI — WebSocket Streaming Protocol (v1)

This document defines the official **v1 WebSocket Streaming Protocol** for real-time speech perception over `/ws/speech`.

---

## 1. Connection Endpoint & Handshake

- **Endpoint**: `ws://127.0.0.1:8000/ws/speech`
- **Authentication**:
  - When `AUTH_REQUIRED=true`, clients must append an HS256 JWT access token as a query parameter:
    `ws://127.0.0.1:8000/ws/speech?token=<ACCESS_TOKEN>`
  - Unauthenticated connections are rejected with RFC 6455 close code `1008` (Policy Violation).
  - When `AUTH_REQUIRED=false` (default in dev), no query parameter is needed.

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
     "language_hint": null
   }
   ```
   - `sample_rate`: Sample rate in Hz (default: `16000`).
   - `encoding`: Audio encoding format. Currently supported: `"pcm_s16le"` (16-bit signed integer, linear PCM, little-endian, mono).
   - `language_hint`: Optional ISO 639-1 language code hint or `null`:
     - Indic languages (`"hi"`, `"bn"`, `"mr"`, `"ta"`, `"te"`, etc.): routes dynamically to IndicConformer-600m.
     - Global languages (`"en"`, `"zh"`, `"yue"`, `"ja"`, `"ko"`): routes dynamically to SenseVoiceSmall.
     - When `null`: routes according to Spoken LID detection (if confidence $\ge$ threshold) or falls back to SenseVoice default.

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

4. **Speech Perception Result (`speech_result`)**:
   Emitted when a complete speech segment has finished processing through the non-blocking perception engine. Conforms to the unified `SpeechResult` schema.
   ```json
   {
     "type": "speech_result",
     "transcript": "Hello, how are you today?",
     "language": "en",
     "emotion": "happy",
     "confidence": null,
     "processing_time_ms": 78,
     "model_version": "SenseVoiceSmall (funasr)",
     "audio_events": ["Speech"],
     "segments": [],
     "debug": {
       "raw_tags": ["<|en|>", "<|HAPPY|>", "<|Speech|>"],
       "vad_has_speech": true
     }
   }
   ```

5. **LLM Token Delta (`llm_delta`)**:
   Emitted progressively as each generated token arrives from the local LLM server. Dispatched strictly after `speech_result`.
   ```json
   {
     "type": "llm_delta",
     "delta": "Hello"
   }
   ```

6. **LLM Completion (`llm_done`)**:
   Emitted once the LLM stream has finished, containing the full aggregated response text.
   ```json
   {
     "type": "llm_done",
     "text": "Hello! I hear you're feeling happy today. How can I help?"
   }
   ```

7. **Error Frame (`error`)**:
   Emitted upon protocol violation, buffer overflow, or upstream/service error:
   ```json
   {
     "type": "error",
     "code": "BUFFER_OVERFLOW",
     "message": "Connection buffer limit (5242880 bytes) exceeded."
   }
   ```
   Or when LLM is unreachable/timed out:
   ```json
   {
     "type": "error",
     "code": "llm_unavailable",
     "message": "Cannot connect to local LLM server at http://127.0.0.1:8080/v1/chat/completions"
   }
   ```
   > **Note**: An `llm_unavailable` error keeps the WebSocket connection open so subsequent voice turns can still be transcribed.

---

## 3. Reserved Message Types

The following message types are reserved for downstream phases (TTS audio streaming) and must be ignored safely without raising errors or dropping connections:
- `tts_chunk`
- `tts_done`
- `status`

Any unknown message types received from the client are also safely ignored.

---

## 4. Operational Invariants & Limits

1. **Server-Side VAD Segmentation**:
   Audio chunks are processed through Silero VAD in 512-sample (32ms) frames with a 250ms pre-speech buffer. Speech ends after 700ms of sustained silence.
2. **Buffer Limits**:
   Per-connection memory buffer is capped at **5 MB** (`WS_MAX_BUFFER_BYTES`). Exceeding this threshold triggers an immediate `BUFFER_OVERFLOW` error and buffer reset.
3. **Resource Cleanup**:
   Disconnects clean up segmenter state and in-memory buffers immediately.
4. **Non-Blocking Inference**:
   ASR and SER inference runs off the asyncio event loop via threadpools (`asyncio.to_thread`) bounded by an asynchronous semaphore (`INFERENCE_CONCURRENCY_LIMIT`).
