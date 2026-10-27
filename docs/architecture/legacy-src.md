# Legacy `src/` Inventory and Porting Assessment

This document provides a comprehensive inventory of the quarantined `src/` tree (restored to the baseline merge-base commit `ebd84078`).

The legacy tree represents the pre-migration baseline architecture. It has been quarantined under option (b) and decoupled from the canonical test suite (`tests/legacy/` excluded via `--ignore=tests/legacy`). Zero production modules in `backend/app/`, `ai/`, or `rag/` import from `src/`.

---

## 1. Subsystem Inventory and Porting Evaluation

| Legacy Path | Description / Role | Current Target Counterpart | Worth Porting? | What It Needs to Fit `backend/app/` |
| :--- | :--- | :--- | :--- | :--- |
| **`src/backend/security/auth.py`** | JWT access/refresh token generation, verification, and API key hashing. | None (Phase 1 currently unauthenticated; Phase 10 roadmap). | **Yes (Phase 10)** | Refactor from hardcoded global settings to `backend.app.core.config.Settings` dependency injection; integrate as FastAPI dependency (`Depends(get_current_user)`) on routes `/api/*` and `/ws/speech`. |
| **`src/backend/security/rate_limiter.py`** | In-memory sliding-window token bucket / utterance counter per client/IP. | None (`backend/app/` lacks rate limiter middleware). | **Yes (Phase 10)** | Wrap into FastAPI middleware or ASGI rate-limiting middleware; inject settings via `pydantic-settings`; add support for WebSocket frame-rate clamping. |
| **`src/backend/security/audit.py`** | SHA-256 hash-chained immutable audit ledger for security and compliance events. | None (`backend/app/` logs to standard Python `logging`). | **Legacy Reference / UNSURE** | Legacy implementation, not wired into target architecture. If ported, wrap file I/O in async worker/threadpool to avoid event loop blocking during disk append, and wire into `backend/app/core/`. |
| **`src/backend/database/storage.py`** | SQLite storage for session transcripts and emotion events (`transcripts`, `emotion_history`). | SQLite dev database (`backend/app/database/` or direct SQL). | **Yes (Phase 9/10)** | Align schema with `brain/04_DATA_MODEL.md` and Pydantic v2 schemas; replace raw `sqlite3` sync calls with `aiosqlite` or SQLAlchemy async session to avoid blocking async event loops. |
| **`src/backend/llm/gemini.py`** | Google Gemini cloud API fallback client (`google-generativeai`). | `backend/app/services/llm_service.py` (currently llama.cpp local HTTP client). | **Yes (Optional Cloud Fallback)** | Refactor to use modern `google-genai` SDK per workspace plugin guidelines; implement as a swappable `LLMClient` provider interface inside `backend/app/services/llm_service.py` triggered only when local Qwen3 fails. |
| **`src/backend/audio/liveness.py`** | Audio anti-spoofing and synthetic speech detection using spectral flatness and drone heuristics. | None (Target architecture VAD only evaluates speech probability via Silero). | **Legacy Reference / UNSURE** | Legacy implementation, not wired into target architecture. If enabled in future phases, integrate as a pre-VAD signal check in `ai/preprocessing/`. |
| **`src/backend/transport/webtransport.py`** | aioquic-based WebTransport session handler for low-latency bidirectional voice streams. | `backend/app/websocket/speech_socket.py` (WebSocket MVP). | **Legacy Reference / UNSURE (Phase 9)** | Legacy implementation, not wired into target architecture. Roadmap specifies WebTransport as a Phase 9 upgrade; will require HTTP/3 server runner and certificate provisioning. |
| **`src/backend/asr/router.py`** | Language router dispatching between SenseVoice and IndicConformer. | `ai/routing/language_router.py` (Active canonical router). | **No (Superseded)** | Target implementation in `ai/routing/` is already tested and feature-complete with 3-tier precedence. |
| **`src/backend/asr/indicconformer.py`** | IndicConformer ASR wrapper. | `ai/inference/indicconformer.py` (Active canonical engine). | **No (Superseded)** | Target implementation in `ai/inference/` conforms to the canonical `SpeechEngine` and `SpeechResult` schema. |
| **`src/backend/audio/vad.py`** | Silero VAD buffer chunker. | `ai/preprocessing/vad.py` (Active canonical VAD). | **No (Superseded)** | Target implementation in `ai/preprocessing/` is verified with robust stateful segmentation. |
| **`src/backend/emotion/emotion.py`** | Fixed valence/arousal emotion lookup table. | `ai/emotion/` (Active canonical emotion parsing). | **No (Superseded)** | SenseVoice emotion tags (`<|HAPPY|>`, `<|SAD|>`, etc.) are parsed directly in `ai/inference/sensevoice.py`. |
| **`src/backend/llm/qwen.py`** | llama.cpp streaming client. | `backend/app/services/llm_service.py` (Active canonical service). | **No (Superseded)** | Target implementation handles circuit breaker, backoff, and async streaming via `httpx`. |
| **`src/backend/pipeline/intent.py`** | Intent classification logic. | `rag/intent_router.py` (Active canonical router). | **No (Superseded)** | Target router in `rag/` is fully tested with hard gate rules and regex/keyword evaluation. |
| **`src/backend/rag/`** | FAISS index and e5 embedding utilities. | `rag/` (Active canonical package). | **No (Superseded)** | Canonical package `rag/` implements ingestion, cosine indexing, and citation generation. |
| **`src/backend/tts/indic_parler.py`** | Parler TTS wrapper. | `backend/app/services/tts_service.py` (Active canonical service). | **No (Superseded)** | Canonical service provides 23-language voice profiles and sentence-level streaming. |
| **`src/backend/transport/websocket_fallback.py`** | Legacy `/ws/voice` WebSocket endpoint. | `backend/app/websocket/speech_socket.py` (`/ws/speech`). | **No (Superseded)** | Target `/ws/speech` socket uses Protocol v1 JSON framing and verified audio streaming. |
| **`src/backend/mcp_server/`** | Model Context Protocol server. | Independent MCP components in workspace. | **No (Quarantined)** | Not part of MVP voice turn path. |
| **`src/frontend/`** | Legacy React 18 prototype. | `frontend/` (Active React 18 + Vite canonical client). | **No (Superseded)** | `frontend/` is the active UI client. `src/frontend/` is retained for historical diff reference. |

---

## 2. Recommendation on Legacy Code

1. **Quarantine Preserved**: `src/` remains in place without deletion to serve as a reference implementation for future phases (such as Phase 9 WebTransport and Phase 10 Auth/Dashboard).
2. **Strict Isolation**: No files in `backend/app/`, `ai/`, or `rag/` may import from `src/`.
3. **No Unrequested Terminology**: Features such as hash-chained audit logging, audio anti-spoofing liveness detection, and WebTransport were part of the initial commit (`ebd84078`). They are properly designated as **legacy implementations, not wired into the target architecture**.

---

## 3. References to the Legacy Tree to Fix in Phase 11

The following configuration files and utility scripts reference `src/` or `src.backend` paths and are scheduled for remediation in Phase 11 (Containerization & Deployment Hardening):

1. **`docker/Dockerfile.backend`**: References `COPY src/backend/requirements.txt` and `CMD ["uvicorn", "src.backend.main:app"]`. Update to package `backend/app/main:app`.
2. **`docker/Dockerfile.frontend`**: References `COPY src/frontend/package*.json` and `COPY src/frontend/`. Update to package active `frontend/`.
3. **`docker/docker-compose.yml`**: Mounts `../src/frontend:/app`. Update to mount `../frontend:/app`.
4. **`scripts/measure_stages.py`**: Legacy benchmarking harness importing `src.backend.config`, `src.backend.models.manager`, and `src.backend.pipeline.orchestrator`. Update to import canonical services in `backend.app.services`.
5. **`scripts/database/build_rag_index.py`**: Replaced in Phase 8g with a pointer to canonical `rag.ingestion` (`python -m rag.ingestion`). In Phase 11, consolidate directly into production CLI tooling.

