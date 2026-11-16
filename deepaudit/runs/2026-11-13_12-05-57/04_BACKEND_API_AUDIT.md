# 04 — Backend API Audit (`backend/app/`)

App factory `main.py`: lifespan calls `speech_service.initialize()` + `rag_service.initialize()` once; CORS `settings.CORS_ORIGINS` (default localhost list); two exception handlers → `create_error_payload`.

## Endpoint register (canonical)

| Method | Route | Handler | Auth | Validation | DB | ML | Frontend caller | Status |
|---|---|---|---|---|---|---|---|---|
| GET | /api/health | health.py:18 | none | — | `check_db_health` | aggregates speech/llm/rag/tts health | `useHealthStatus`→ServiceStatusCard | VERIFIED |
| POST | /api/speech/upload | speech.py:116→`process_audio_upload` | none | MIME+ext, 10MB, non-empty, WAV RIFF check via soundfile | none | `speech_service.transcribe_audio_bytes` | **none** | IMPLEMENTED—NOT RUNTIME VERIFIED |
| POST | /api/predict | prediction.py:17 | none | same shared handler | none | same | **none** | IMPLEMENTED—NOT RUNTIME VERIFIED |
| POST | /api/auth/register | auth.py:33 | IP rate-limit | Pydantic schema | users insert | — | AuthModal | VERIFIED (tests) |
| POST | /api/auth/login | auth.py:60 | IP rate-limit | schema | users query | — | AuthModal | VERIFIED |
| GET | /api/auth/me | auth.py:97 | Bearer JWT | — | users query | — | (unused by UI? AuthModal may call) | VERIFIED |
| POST | /api/auth/token | auth.py:109 | **NONE — mints JWT for arbitrary user_id/username/session_id** | none | none | — | test harnesses | **BROKEN/SECURITY HOLE** |
| POST | /api/auth/verify | auth.py:136 | none | — | — | — | test harnesses | VERIFIED |
| GET | /api/history/sessions | history.py:26 | Bearer | — | sessions+predictions count, user-scoped | — | ConversationHistory | VERIFIED |
| GET | /api/history/sessions/{id} | history.py:61 | Bearer + ownership (404 otherwise) | — | session detail | — | ConversationHistory | VERIFIED |
| DELETE | /api/history/sessions/{id} | history.py:86 | Bearer + ownership | — | cascade delete | — | ConversationHistory | VERIFIED |
| DELETE | /api/history | history.py:112 | Bearer | — | purge all user data | — | ConversationHistory | VERIFIED |
| WS | /ws/speech | speech_socket.py:229 | in-frame JWT if AUTH_REQUIRED | start-frame fields, buffer/duration/utterance limits | via history_service | full pipeline | useWebSocket | VERIFIED (tests+live runs in docs) |

## Legacy endpoints (`src/backend/main.py`, quarantined, not mounted by canonical app)

`POST /api/auth/token`, `POST /api/auth/verify`, `GET /health`, `GET /api/emotion/history/{id}`, `GET /api/benchmark/{metrics,summary}`, `POST /api/benchmark/reset`, `GET /api/transport/capabilities`, `GET /wt`, `WS /ws/voice`.

## Backend findings

1. **`/api/auth/token` auth bypass** — issues valid HS256 JWT for caller-supplied `user_id`/`username`/`session_id` with zero credential verification (`auth.py:109-133`). `get_current_user` then resolves `sub`→User row, so attacker needs only a valid username (e.g. enumerated via 409 on register or `/api/auth/me` error oracle). **Critical.**
2. **No auth on speech/predict/upload endpoints** — acceptable for dev (`AUTH_REQUIRED=false`) but means anonymous users get full ASR+LLM+TTS compute with only rate limits on WS utterances; REST upload has **no rate limiter at all** (only auth endpoints are IP-limited). DoS vector. Medium.
3. **`process_audio_upload` shared by two routes** — fine, but `/api/predict`'s `include_assistant` returns a hardcoded stub `{"status":"not_configured"}` (`prediction.py:29-34`) — never invokes LLM despite the flag's implication. Mock/placeholder.
4. Error responses leak `str(e)` internals in `details.error` for decode/inference errors (`speech.py:83,101,109`) — minor info disclosure.
5. Sync SQLAlchemy sessions inside async endpoints (`auth.py`, `history.py`) — blocking calls on event loop; small DB so low impact, but violates async hygiene.
6. `speech_socket.py` — solid: message pump prevents uvicorn read-pausing, keepalive ping fast-path, per-connection buffer cap, utterance+duration limits, LLM task cancel on new turn (barge-in), history write in `finally` via `asyncio.create_task` (fault-isolated). Note: `record_voice_turn` task created with `create_task` inside `finally` — if loop is closing it may be dropped silently (minor).
7. `health.py` calls `await llm_service.check_health()` on every request — cached 5s, OK.
8. No API versioning; no OpenAPI customization beyond defaults; `docs/api/openapi.json` exists (generated snapshot — verify freshness: unverified).
9. `database/migrations/001_create_emotion_history.py` + `schemas/001_emotion_history.sql` duplicate legacy table outside Alembic — orphaned artifacts.
