# REST API Reference

**Machine-Readable Specification:** [`openapi.json`](./openapi.json) (`OpenAPI 3.1.0`, exported from `backend.app.main:app`)  
**Real-Time Voice Protocol:** [`websocket.md`](./websocket.md)

> [!NOTE]
> The exported `openapi.json` info header still reports `"version": "0.2.0"` and `"Phase 2: Modular FastAPI backend..."` in application metadata even though Phase 9 auth and history routes are mounted and active. Treat this document and the OpenAPI path schemas below as canonical.

---

## 1. Endpoint Overview

All REST endpoints run under `/api/*` and share the FastAPI application lifespan initialized at startup.

| Method & Path | Tags | Auth Required | Purpose | Schema |
|---|---|---|---|---|
| `GET /api/health` | `health` | No | Per-component health (`asr`, `emotion`, `llm`, `rag`, `tts`, `db`) & overall `ok`/`degraded` | Unstructured JSON |
| `POST /api/speech/upload` | `speech` | No | In-memory audio decode + speech perception (`SpeechResult`); zero disk audio | [`SpeechResult`](./openapi.json#L1112) |
| `POST /api/predict` | `prediction` | No | Same speech perception path with optional `assistant` stub field | [`PredictionResponse`](./openapi.json#L826) |
| `POST /api/auth/register` | `auth` | IP rate-limited | Register user account with `hashlib.scrypt` password hash | [`UserResponse`](./openapi.json#L1346) |
| `POST /api/auth/login` | `auth` | IP rate-limited | Authenticate username/password and issue HS256 JWT | [`TokenResponse`](./openapi.json#L1210) |
| `GET /api/auth/me` | `auth` | Bearer JWT | Return current authenticated user profile | [`UserResponse`](./openapi.json#L1346) |
| `POST /api/auth/token` | `auth` | Optional JSON | Issue an HS256 JWT token for session establishment | Unstructured JSON |
| `POST /api/auth/verify` | `auth` | JSON body | Validate a JWT token and return claims if valid | Unstructured JSON |
| `GET /api/history/sessions` | `history` | Bearer JWT | List conversational sessions owned by authenticated user | [`SessionSummarySchema`](./openapi.json#L1071)[] |
| `GET /api/history/sessions/{session_id}` | `history` | Bearer JWT | Retrieve full session turns (`predictions`, `transcript`, `emotion_result`, `messages`) | [`SessionDetailSchema`](./openapi.json#L1019) |
| `DELETE /api/history/sessions/{session_id}` | `history` | Bearer JWT | Delete a single owned session (cascades children) | `{}` / status |
| `DELETE /api/history` | `history` | Bearer JWT | Delete-My-Data purge of all sessions, transcripts, predictions, and messages | [`DeleteHistoryResponse`](./openapi.json#L643) |

---

## 2. Health & Perception Endpoints

### `GET /api/health`
Returns live readiness for `asr`, `emotion`, `llm`, `rag`, `tts`, and `db`. Returns HTTP `200` even when optional services (`llm`, `rag`, `tts`, or `db`) are down or degraded; `tts` reports `"disabled"` when `TTS_ENABLED=false` (the default).

> **Doc/Code Mismatch:** `/api/health` does not include an `auth_required` boolean. The React frontend falls back to build-time `VITE_AUTH_REQUIRED` to decide whether to show the sign-in screen.

### `POST /api/speech/upload`
- **Content-Type:** `multipart/form-data`
- **Fields:**
  - `file` *(required)*: Binary audio file (`MAX_UPLOAD_SIZE_BYTES=10485760` / 10 MB default).
  - `language_hint` *(optional `string | null`)*: `"en"`, `"hi"`, or `null`.
- **Supported Formats:** OpenAPI description mentions `(WAV, MP3, FLAC, OGG)`; runtime `Settings.ALLOWED_AUDIO_MIME_TYPES` accepts `audio/wav`, `audio/x-wav`, `audio/wave`, `audio/mpeg`, `audio/mp3`, `audio/ogg`, `audio/flac`, `audio/webm`, `application/octet-stream`, and the upload handler also accepts `.m4a` filenames.
- **Privacy Guarantee:** Audio bytes are decoded strictly in memory and discarded at the end of the request.

### `POST /api/predict`
- **Content-Type:** `multipart/form-data`
- **Fields:** `file` *(required)*, `language_hint` *(optional)*, `include_assistant` *(boolean, default `false`)*.
- **Doc/Code Mismatch:** Passing `include_assistant=true` still returns the Phase 2 stub (`{"status": "not_configured", "message": "Assistant LLM reasoning is not configured in Phase 2."}`) because live streaming Qwen3 + RAG turns run over the `/ws/speech` WebSocket protocol rather than REST.

### `SpeechResult` Confidence & Null Semantics
- **SenseVoiceSmall (`language_hint=null` / `"en"` / `"zh"` / `"ja"` / `"ko"` / `"yue"`):** Emits greedy discrete tokens with `emotion` normalized when detected (or `null`) and `confidence: null` (never fabricated).
- **IndicConformer-600m (`language_hint="hi"`):** Performs Hindi ASR only; emits `emotion: null` and `confidence: null` because Hindi emotion recognition is separate and unimplemented at runtime.

---

## 3. Authentication & Rate Limiting

Auth routes enforce per-IP rate limiting via `IPRateLimiter` (`RATE_LIMIT_AUTH_PER_MINUTE=10` requests/minute).

- **`POST /api/auth/register`** (`201 Created`)
  - Body: `{"username": "<3-64 chars>", "password": "<6-128 chars>"}`
  - Stores scrypt-hashed credentials (`hashlib.scrypt`) in SQLite/PostgreSQL.
- **`POST /api/auth/login`** (`200 OK`)
  - Body: `{"username": "...", "password": "..."}`
  - Returns `access_token`, `token_type: "Bearer"`, `expires_in_seconds` (`SESSION_TIMEOUT_MINUTES * 60`), `user_id`, `username`.
- **`GET /api/auth/me`**, **`POST /api/auth/token`**, **`POST /api/auth/verify`**
  - Bearer JWT validation uses `JWT_SECRET` (validated to be >= 32 non-default characters when `APP_ENV=production`).

---

## 4. Conversation History & User Isolation

All `/api/history*` routes extract the authenticated user from the `OAuth2PasswordBearer` header (`Authorization: Bearer <token>`):

- **Strict Tenant Isolation:** Queries filter by `user_id`; requesting another user's `session_id` returns `404` rather than leaking existence.
- **Known Persistence Fallback:** When storing historical `emotion_results` for a turn whose live prediction had `emotion=null` (such as Hindi turns), `HistoryService` persists `primary_emotion="neutral"` and `confidence=0.8` in SQL storage rather than nullable values (`backend/app/services/history_service.py`). Live WebSocket and REST perception responses remain unaffected and continue returning `null`.
- **Permanent Purge:** `DELETE /api/history` deletes all sessions, predictions, transcripts, emotion records, and assistant messages for the caller in one transaction and returns `DeleteHistoryResponse`.
