# 05 — Backend & API Deep Dive

Canonical backend: `backend/app/` — FastAPI app factory, SQLAlchemy 2.x,
Pydantic v2 settings/schemas. Entry: `uvicorn backend.app.main:app`.

## 1. Application factory & lifecycle (`backend/app/main.py`)

- `create_app()` builds the `FastAPI` instance (title "VoiceSense AI Backend",
  v0.2.0) with a `lifespan` context manager.
- **Startup rule (from AGENTS.md): every model loads ONCE at startup, never
  per-request.** `lifespan` calls `speech_service.initialize()` and
  `rag_service.initialize()`; engines themselves also support lazy loading
  (`LAZY_LOAD_MODELS=true`) which emits `loading_model`/`model_ready` status
  frames on first use.
- CORS from `settings.CORS_ORIGINS` (defaults: localhost:5173/5174/3000).
- Two exception handlers produce the uniform error envelope
  `{"error": {"code", "message", "details"}}` via `create_error_payload()`.

## 2. REST endpoints

### `GET /api/health` (`api/health.py`)
Aggregates per-component status — never fails the request for optional parts:

```json
{
  "status": "ok|degraded",
  "components": {"asr": "...", "emotion": "...", "llm": "...",
                 "rag": "...", "tts": "...", "db": "ok|unavailable|not_configured"},
  "details": {"model_version": "...", "llm": {...}, "rag": {...}, "tts": {...}}
}
```

### `POST /api/speech/upload` (`api/speech.py`)
Multipart file upload → stateless perception (no LLM/RAG/history):
- Validates `language_hint` via `normalize_language_hint()` (English-only MVP
  rejects e.g. `"hi"` with `INVALID_LANGUAGE_HINT`).
- MIME allow-list + filename extension check → `415 INVALID_CONTENT_TYPE`.
- Chunked in-memory read capped at `MAX_UPLOAD_SIZE_BYTES` (10 MB) → `413`.
- WAV/RIFF container validation via `soundfile` → `400 DECODE_ERROR`.
- `speech_service.transcribe_audio_bytes()` → `SpeechResult` JSON.
- **Zero disk persistence** — bytes live only in RAM for the request.

### `POST /api/predict` (`api/prediction.py`)
Same `process_audio_upload()` path, wrapped in `PredictionResponse`.
`include_assistant=true` currently returns a stub
(`{"status":"not_configured"}`) — documented gap; real assistant flow is WS-only.

### Auth (`api/auth.py`, prefix `/api/auth`)
| Endpoint | Behavior |
|---|---|
| `POST /register` | 201; scrypt hash; 409 on duplicate username; per-IP rate limit |
| `POST /login` | verify scrypt → HS256 JWT (`sub`, `username`, `session_id`, `iat/nbf/exp`); 401 on bad creds; `SESSION_TIMEOUT_MINUTES=60` |
| `GET /me` | current user profile (Bearer) |
| `POST /verify` | validate any token, return claims |

### History (`api/history.py`, prefix `/api/history`)
| Endpoint | Behavior |
|---|---|
| `GET /sessions` | list user's sessions + turn counts, newest first |
| `GET /sessions/{id}` | full detail (predictions, transcripts, emotions, messages); **404 for other users' sessions** |
| `DELETE /sessions/{id}` | cascade-delete one session |
| `DELETE /` (no path) | **delete-my-data**: purge ALL of the user's sessions + children |

All require `get_current_user`; isolation is enforced by `user_id` filters in
every query.

## 3. WebSocket protocol v1 — `ws://127.0.0.1:8000/ws/speech`

File: `backend/app/websocket/speech_socket.py`. Full schema also in
`docs/api/websocket.md`; the essentials:

### Client → server (JSON text frames)
```json
{"type":"start","sample_rate":16000,"encoding":"pcm_s16le",
 "language_hint":null,"auth_token":"...","session_id":"..."}
{"type":"stop"}
{"type":"ping"}
```
…plus **binary frames** of raw PCM16 mono audio between start/stop.

### Server → client
| Type | Payload |
|---|---|
| `ready` | session accepted |
| `pong` | keepalive ack |
| `vad` | `{"state":"speech_start"\|"speech_end"}` |
| `status` | `loading_model`/`model_ready` (engine), `no_speech`, `rag_fallback` |
| `speech_result` | full `SpeechResult` + `debug.segment_index`, `segment_duration_s`, etc. |
| `rag_sources` | `{"sources":[{doc_name, chunk_id, score}]}` |
| `llm_delta` | `{"delta":"token"}` streaming |
| `llm_done` | `{"text":"...","sources":[...]}` |
| `tts_chunk` | header JSON `{"index","sample_rate","text","format":"wav"}` **followed by one binary WAV frame** |
| `tts_done` | `{"total_chunks","total_duration_ms"}` |
| `error` | `{"code","message"}` — codes: `INVALID_JSON`, `AUTH_REQUIRED`, `AUTH_FAILED`, `INVALID_LANGUAGE_HINT`, `NOT_STARTED`, `BUFFER_OVERFLOW`, `AUDIO_DURATION_LIMIT_EXCEEDED`, `RATE_LIMIT_EXCEEDED`, `INFERENCE_ERROR`, `llm_bad_response`, `llm_unavailable`, `tts_unavailable` |

### Server-side mechanics (what to explain in viva)

1. **`_message_pump` task**: continuously drains `websocket.receive()` into an
   `asyncio.Queue`, answering `ping` frames immediately. This exists because
   uvicorn pauses socket reads while the event loop is busy — the pump keeps
   the transport alive during multi-second model loads (measured max event-loop
   stall 225.9 ms over a 49 s cold load).
2. **Auth**: JWT verified **inside the `start` frame** (never URL query — avoids
   log leakage). If `AUTH_REQUIRED=true`: missing/bad token → error frame +
   close `1008 POLICY_VIOLATION`. Token `sub` must reference an existing,
   active user (FK-safe).
3. **VAD segmentation**: each binary chunk → `segmenter.process_chunk()`;
   completed utterance → rate-limit check → `speech_service.
   transcribe_pcm16_bytes()` off the event loop → `speech_result` first.
4. **Confirmed no-speech**: empty transcript → `refund_utterance()` (doesn't
   burn the 20/min budget) + `status:no_speech` instead of a result turn.
5. **Barge-in/cancellation**: a new utterance or disconnect cancels the
   in-flight `handle_llm_turn` task (`active_llm_task.cancel()`).
6. **`handle_llm_turn` order**: `rag_service.process_turn()` (hard gate) →
   `PromptBuilder.build_chat_messages()` → `llm_service.generate(stream=True)`
   → `llm_delta` frames → `llm_done` → in-memory history append → optional TTS
   stream → **finally**: `history_service.record_voice_turn()` as a background
   task (fault-isolated).
7. **Limits**: `WS_MAX_BUFFER_BYTES=5 MB` per connection, 30 s per utterance,
   inference semaphore = 2 concurrent transcriptions.

## 4. Services layer (the "why" of each file)

| Service | Singleton | Key behavior |
|---|---|---|
| `speech_service` | yes | engine+router lifecycle, threadpool inference, semaphore, English-only gate, health |
| `rag_service` | yes | intent gate → conditional retrieval; degrades to `no_index` gracefully |
| `llm_service` | yes | llama.cpp HTTP+SSE, thinking filter, circuit breaker, typed errors |
| `history_service` | yes | transactional turn persistence, ownership guard, redaction, swallow-errors |
| `tts_service` | yes | lazy load, sentence streaming, OOM/timeout cooldowns, worker isolation |
| `prompt_builder` | stateless | system prompt + history window + grounded-context injection |

## 5. Database (`backend/app/core/database.py` + `models/` + `alembic/`)

- **Engine**: `create_engine(settings.DATABASE_URL)` — default
  `sqlite:///./database/dev.db`; PostgreSQL URL supported (`psycopg` driver in
  `requirements/runtime.txt`). SQLite gets `check_same_thread=False`, per-
  connection `PRAGMA foreign_keys=ON` (via `event.listens_for(engine,"connect")`
  so pooled connections each enable it), `StaticPool` for `:memory:` tests.
- **Two session styles**: `get_db()` (FastAPI dependency, request-scoped) and
  `get_db_session()` (context manager for threadpool persistence).
- **ORM models** (SQLAlchemy 2.x `DeclarativeBase` in `database.py`):
  - `User` — id, username (unique), hashed_password (scrypt), is_active
  - `Session` — id (`sess_…`), user_id FK, primary_language, timestamps
  - `Prediction` — id, session_id FK, model_version_id FK, audio_duration_ms,
    processing_time_ms, confidence, created_at
  - `Transcript` — prediction_id FK, session_id, text (redactable), language,
    script, mixed_language, audio_events
  - `EmotionResult` — prediction_id, primary_emotion, confidence/valence/
    arousal (**nullable — never fabricated**), raw_tags
  - `Message` — role user/assistant, text, sources (RAG citations JSON)
  - `ModelVersion` — engine_name, model_id, pinned_revision, decoder_type
- **Migrations**: Alembic, 3 revisions — initial schema; emotion metrics made
  nullable; transcript `mixed_language` nullable. Legacy
  `database/migrations/001_create_emotion_history.py` +
  `schemas/001_emotion_history.sql` predate Alembic (early schema).

### Persistence flow per turn (`history_service.persist_turn_sync`)

```text
user_id None?            → return (anonymous = zero persistence)
session exists?          → ownership check (user_id must match, else reject)
model_version row        → get-or-create keyed by engine+model+revision+decoder
INSERT prediction        → audio_duration_ms, processing_time_ms, confidence
INSERT transcript        → text or "[REDACTED_BY_POLICY]" if STORE_TRANSCRIPTS=false
INSERT emotion_result    → only if emotion label exists; scores stay NULL
INSERT messages          → user turn + assistant turn (with RAG sources)
COMMIT                   → any failure logged + swallowed (never breaks voice)
```

## 6. Security & limits (`core/security.py`, `core/rate_limiter.py`, `core/config.py`)

- **Passwords**: `hashlib.scrypt` (n=16384, r=8, p=1, maxmem=32 MB), 16-byte
  `os.urandom` salt, `hmac.compare_digest` verify — stdlib only, memory-hard.
- **JWT**: hand-rolled HS256 per RFC 7515 — header/payload/signature base64url,
  `alg` pinned to HS256 (algorithm-confusion safe), `exp`/`nbf` validated with
  10 s leeway, signature via `hmac.compare_digest`. No PyJWT dependency.
- **Production guard**: `Settings.validate_production_security` refuses startup
  when `APP_ENV=production` with a default/short (<32 char) `JWT_SECRET` or
  `AUTH_REQUIRED=false`.
- **Rate limits**: per-session sliding-window 20 utterances/min (with refund on
  confirmed silence); 30 s max utterance; 10 MB uploads; per-IP 10 auth
  attempts/min.
- **Prompt-injection guard**: RAG excerpts are framed as "untrusted reference
  data, never instructions" in the system prompt; TTS input strips citation/
  markdown artifacts.
- **Privacy**: raw audio never touches disk (in-memory decode only); transcripts
  redactable; `DELETE /api/history` = GDPR-style purge; tokens in-frame not URL.

## 7. Configuration (`core/config.py`)

Single `Settings` class — every tunable is an env var with a safe default.
Notable: `ASR_ENGLISH_ONLY=true`, `LAZY_LOAD_MODELS=true`,
`INFERENCE_CONCURRENCY_LIMIT=2`, all `LLM_*`/`TTS_*` params, model paths and
the pinned `INDICCONFORMER_REVISION`. `.env.example` documents all of them.
