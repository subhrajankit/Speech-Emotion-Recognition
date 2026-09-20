# 16 — Changelog

All notable changes across build phases are recorded here.

## [Phase 6 - Target Migration] - Qwen3 / LLM Service Integration (2026-09-20)
- **Decoupled LLM Service Interface (`backend/app/services/llm_service.py`)**:
  - Implemented `LLMService` communicating with local `llama-server` over HTTP using `httpx` with explicit timeouts.
  - Implemented `generate(messages, *, emotion=None, language=None, stream=True, max_tokens=None, timeout=None)` supporting async token streaming and non-streaming modes.
  - Typed exceptions: `LLMError`, `LLMUnavailable` (unreachable/5xx), `LLMTimeout`, and `LLMResponseError`.
  - Circuit breaker / cool-down mechanism: trips into cooldown after `LLM_FAILURE_THRESHOLD=3` consecutive failures for `LLM_COOLDOWN_SECONDS=15.0`, short-circuiting doomed requests while keeping ASR/emotion alive.
  - Cached health check (`check_health()`) with `LLM_HEALTH_CACHE_SECONDS=5.0`.
  - Integrated into `/api/health` without failing overall system health when LLM is offline (`status: ok | degraded`).
- **Prompt Builder Module (`backend/app/services/prompt_builder.py`)**:
  - Clean separation of prompt construction: formats system prompt injecting detected emotion and spoken language, instructing the assistant to respond in the user's language and tone.
  - Token budget sliding window: trims conversation history to fit within a configurable token budget (`max_history_tokens=1024`).
- **Voice Latency Thinking Mode Filtering**:
  - Request payload sets `"chat_template_kwargs": {"enable_thinking": False}` for low-latency voice responses.
  - Streaming `ThinkingFilter` and non-streaming `strip_thinking_tags` regex parser strip `<think>...</think>` content even if split across chunk boundaries before reaching UI/TTS.
- **Strict Ordering & Resilience in WebSocket (`backend/app/websocket/speech_socket.py`)**:
  - `speech_result` event is guaranteed to be emitted BEFORE calling the LLM and never waits on it.
  - LLM tokens stream via `llm_delta` followed by `llm_done`.
  - On LLM failure/downtime, emits `{"type": "error", "code": "llm_unavailable", "message": ...}` and keeps the socket open for subsequent turns.
- **Strict Architectural Import Isolation (`tests/backend/test_isolation.py`)**:
  - Automated AST scan verifies that no file under `ai/` and no speech engine (`backend/app/services/speech_service.py`) imports or references `llm_service`.
- **Testing & Fault Injection (`tests/backend/test_llm_service.py`, `tests/backend/test_websocket.py`)**:
  - Comprehensive unit test suite with `httpx.MockTransport` simulating 503 errors, connect refusals, SSE token streams, thinking tag extraction, and cool-down resets.
  - 33 backend tests + 46 AI tests passing (79 total passed, 2 skipped cleanly).

## [Phase 4 - Target Migration] - Hindi / Indic Language Routing & Unified SpeechEngine (2026-09-20)
- **Standardized Language Router (`ai/routing/language_router.py`)**:
  - Implemented `RoutingDecision` schema: `{language, confidence, engine, source: "hint" | "detected" | "default"}`.
  - Implemented 3-tier precedence policy: explicit client `language_hint` wins (Tier 1); spoken LID above configurable threshold `LID_CONFIDENCE_THRESHOLD=0.6` (Tier 2); default engine `SenseVoiceSmall` (Tier 3).
  - Pluggable `LanguageIdentifier` protocol allowing arbitrary LID backends or injected detectors for pure logic testing.
  - Supported language registries: `INDIC_LANGUAGES` (22 scheduled Indian languages) and `SENSEVOICE_LANGUAGES` (`en`, `zh`, `yue`, `ja`, `ko`).
- **IndicConformer-600m SpeechEngine (`ai/inference/indicconformer.py`)**:
  - Implemented unified `SpeechEngine` abstract interface matching `SenseVoiceSpeechEngine`.
  - Documented real loading via NVIDIA NeMo (`EncDecCTCModelBPE.from_pretrained(...)`), CTC vs RNNT decoding modes, and `language_id` argument with academic citations.
  - Emotion Invariant: Guaranteed `emotion = None` and `emotion_scores = None` for all IndicConformer transcriptions. SenseVoice emotion head is never run on Hindi audio.
  - Phase 5 Seam: Clean `apply_emotion_hook` decoupling hook ready for independent emotion engine integration.
- **Unified Pipeline inside SpeechService (`backend/app/services/speech_service.py`)**:
  - Integrated `LanguageRouter`, `SenseVoiceSpeechEngine`, and `IndicConformerSpeechEngine` into the single singleton `SpeechService`.
  - Single non-blocking pipeline: `router.route()` -> select engine -> threadpool bounded execution -> unified `SpeechResult`.
  - Enriched `SpeechResult.debug["routing"]` with full routing decision telemetry.
  - Component health reporting updated for dual ASR engines.
- **REST & WebSocket Endpoints Wiring (`backend/app/api/speech.py`, `websocket/speech_socket.py`)**:
  - `POST /api/speech/upload`: Full support for `language_hint` form parameter, routing Indic audio to `indicconformer`.
  - `WS /ws/speech`: `start` control frame parses `language_hint` and routes dynamic audio frames to the correct engine.
- **LID Candidate Evaluation & Architectural Docs (`docs/architecture/language-routing.md`, `docs/api/websocket.md`)**:
  - Comparative evaluation of SpeechBrain VoxLingua107, Meta MMS-LID, and OpenAI Whisper head across license, model size, CPU latency, and language coverage.
  - Code-mixed speech (Hinglish) documented as an unmeasured known limitation until empirical benchmarks are established.
- **Testing & Verification (`tests/ai/`, `tests/backend/`)**:
  - `tests/ai/test_language_router.py`: 9 unit tests verifying pure decision logic with hand-written LID outputs.
  - `tests/ai/test_indicconformer.py`: 6 tests verifying `SpeechEngine` interface compliance, emotion invariant, silence gating, and `@pytest.mark.model` skipping cleanly when weights are absent.
  - `tests/backend/test_upload.py`, `tests/backend/test_websocket.py`: verified Hindi hint routes to IndicConformer returning `emotion = None`.
  - 66 tests passing across `tests/ai/` and `tests/backend/`, 2 skipped cleanly with reasons. Zero errors.

## [Phase 3 - Target Migration] - Clean Minimal Dashboard & WebSocket Protocol v1 (2026-09-20)
- **Repository Layout Relocation (`frontend/`)**:
  - Relocated frontend from `src/frontend/` to `frontend/` using `git mv` in accordance with target architecture (`docs/architecture/target-architecture.md`).
- **Typed WebSocket Hook & Protocol v1 (`frontend/src/hooks/useWebSocket.ts`, `services/protocol.ts`)**:
  - Handshake lifecycle: connects to `/ws/speech`, transmits `start` frame, handles `ready`, tracks `vad` (`speech_start`/`speech_end`), updates `speech_result`, and supports `ping`/`pong`.
  - Reconnection resilience: exponential backoff (min 1s, factor 1.5, max 10s) with clear connection state (`disconnected`, `connecting`, `connected`, `reconnecting`, `error`).
  - Safe ignoring: reserved downstream message types (`llm_delta`, `llm_done`, `tts_chunk`, `tts_done`, `status`) and unknown frames are logged to `console.debug` and safely passed without throwing errors or disconnecting.
- **Audio Capture & Downsampling (`frontend/src/hooks/useAudioCapture.ts`)**:
  - Real-time `getUserMedia` capture using `AudioWorklet` (`/audio-processor.js`) downsampling to 16 kHz mono signed 16-bit PCM.
  - Automatic fallback to `ScriptProcessorNode` if `AudioWorklet` is unavailable.
  - Hardware & permission error handling: handles `NotAllowedError` (permission denied), `NotFoundError` (no audio device), and tracks audio track `.onended` for mid-stream disconnects.
- **Audio Playback Queue (`frontend/src/hooks/useAudioPlayback.ts`)**:
  - Web Audio API FIFO playback queue decoding and playing chunks back-to-back without overlap. Built and verified, staying idle until Phase 8 delivers TTS chunks.
- **Graceful Assistant Degradation & Subsystem Health (`frontend/src/components/`)**:
  - `ResponseView`: when LLM and TTS are not configured (as in Phase 2/3), displays a graceful "assistant unavailable" notice while transcript, language, emotion, and latency continue to render normally.
  - `ServiceStatusCard`: polls `/api/health` and renders real-time status indicators for 6 subsystems (`asr`, `emotion`, `llm`, `rag`, `tts`, `db`).
- **In-Memory History Store (`frontend/src/stores/conversationStore.ts`)**:
  - Store-backed history with observer pattern, reactive React hook, and clear architectural seam (`syncWithBackend()`) ready for `/api/history` in Phase 9.
- **Accessibility & Design System (`frontend/src/components/`)**:
  - `MicrophoneControl` with explicit `aria-label`, `aria-pressed`, live indicator, and keyboard toggle shortcut (Spacebar).
  - Centralized environment variables (`VITE_API_URL`, `VITE_WS_URL`) via `frontend/src/lib/env.ts`.
- **Verification Suite**:
  - 17 unit tests in `frontend/src/tests/` verifying protocol serialization/parsing and store state management. All tests pass.
  - `npm run lint` (`eslint`), `npx tsc --noEmit`, and `npm run build` pass with zero warnings and zero errors.

## [Phase 2 - Target Migration] - Clean FastAPI Boundaries & Real-Time WebSocket (2026-09-20)
- **Modular Backend Architecture (`backend/app/`)**:
  - Application factory in `backend/app/main.py` with FastAPI lifespan model loading.
  - Configuration via `pydantic-settings` in `backend/app/core/config.py` with CORS origins from environment and strict privacy logging.
  - Core logging in `backend/app/core/logging.py` ensuring transcripts and audio bytes are never logged at INFO level.
  - Re-homed HMAC-SHA256 JWT auth in `backend/app/core/security.py` and `backend/app/api/auth.py`.
- **Non-Blocking Speech Service (`backend/app/services/speech_service.py`)**:
  - Encapsulates `ai/` speech engine (`SenseVoiceSpeechEngine`).
  - Offloads CPU/GPU synchronous inference from asyncio event loop to worker threads (`asyncio.to_thread`) bounded by `asyncio.Semaphore(settings.INFERENCE_CONCURRENCY_LIMIT)`.
  - In-memory audio decoding with zero audio persistence to disk.
- **REST Endpoints (`backend/app/api/`)**:
  - `GET /api/health`: Per-component readiness for ASR and emotion, placeholders for LLM, RAG, TTS, DB as `"not_configured"`. Responds in <10ms even during active heavy inference.
  - `POST /api/speech/upload`: Validates multipart audio, enforces 10MB size limit and content-type checks, and returns `SpeechResult`.
  - `POST /api/predict`: Shares upload service pipeline, returning `PredictionResponse(SpeechResult)` with optional downstream `assistant` block.
- **WebSocket Protocol v1 (`backend/app/websocket/speech_socket.py`, `docs/api/websocket.md`)**:
  - Full streaming protocol: `start` -> `ready` -> binary PCM16 audio -> `speech_result` -> `stop`.
  - Server-side VAD state transitions (`speech_start`, `speech_end`).
  - Keepalive ping/pong, per-connection 5MB buffer limit, and auth gating (`AUTH_REQUIRED`).
  - Safe ignoring of unknown and reserved message types (`llm_delta`, `llm_done`, `tts_chunk`, `tts_done`, `status`).
- **Test Client & Verification Suite (`scripts/ws_client.py`, `tests/backend/`)**:
  - Standalone `scripts/ws_client.py` streaming audio chunks and printing ordered server events.
  - 18 automated tests in `tests/backend/` covering health, upload validation, predict semantics, and full WebSocket sequences. All 50 tests pass.

## [Phase 1 - Target Migration] - Stable Base Speech Pipeline (2026-09-20)
- **Standalone Audio Preprocessing (`ai/preprocessing/audio.py`)**:
  - Implemented `load_and_preprocess_audio`, `to_mono`, `resample_audio`, `normalize_audio`, and `decode_audio`.
  - Supports file paths, raw PCM bytes, containerized audio (WAV, FLAC, OGG), and NumPy arrays.
  - Safe 0-byte file handling returning empty arrays with zero exceptions.
  - Linear fractional resampling to 16 kHz and peak normalization to `[-1.0, 1.0]`.
- **Silero VAD Isolation & Gating (`ai/preprocessing/vad.py`)**:
  - Refactored `SileroVAD` ONNX engine and `VADSpeechSegmenter` with configurable thresholds and durations (`SILERO_VAD_THRESHOLD`, `min_speech_duration_ms`).
  - Added `VADResult` dataclass and `analyze()` method guaranteeing explicit no-speech results for empty, silent, or sub-second audio.
  - Retained backward compatibility forwarder in `src/backend/audio/vad.py`.
- **Unified Speech Schema & Interface (`ai/inference/types.py`, `engine.py`)**:
  - Defined Pydantic `SpeechResult` with `transcript`, `language`, `emotion`, `confidence` (`None` by default per uncalibrated probability policy), `processing_time_ms`, and `model_version`.
  - Zero model-specific keys in root schema.
  - Implemented `SpeechEngine` abstract protocol.
- **SenseVoice Inference Engine & CLI (`ai/inference/sensevoice.py`)**:
  - Implemented `SenseVoiceSpeechEngine` with rich tag parsing for language (`zh`, `en`, `yue`, `ja`, `ko`), emotion (`happy`, `sad`, `angry`, `neutral`, `fearful`, `disgusted`, `surprised`), and AED events (`BGM`, `Speech`, `Applause`, etc.).
  - Standalone CLI: `python -m ai.inference.sensevoice <file.wav>` outputting schema-compliant JSON.
  - Actionable error naming expected path if weights/dependencies are missing; `--mock` flag for dry-run/mock verification.
- **Packaging & Verification (`pyproject.toml`, `tests/ai/`)**:
  - Added root `pyproject.toml` registering `ai` package and pytest markers.
  - Created 33 new automated tests in `tests/ai/` (32 passed, 1 model test cleanly skipped when weights are absent).
  - All 80 existing unit tests in `tests/unit/` continue to pass.
  - Benchmark: Silero VAD cold start 343 ms; warm inference on 6s audio is 55.0 ms (RTF 0.0092, 108x faster than real-time).

## [Phase 17] - Optional Cloud Fallback (Gemini 3 Flash) alongside Local Qwen3 (2026-09-14)
- **Optional Gemini 3 Flash Cloud LLM Client**:
  - Implemented `GeminiClient` in `src/backend/llm/gemini.py` calling Google Gemini API (`gemini-2.5-flash` / Gemini 3 Flash) via asynchronous HTTP Server-Sent Events (SSE).
  - Matches the exact method signatures and input context (`prompt`, `emotion`, `language`, `mixed_language`, `messages`) of `QwenClient`.
  - Streams tokens sentence-by-sentence feeding directly into `SentenceBoundaryChunker` and emotion-styled Indic Parler-TTS without downstream pipeline modification.
- **Provider Router & Runtime Overrides**:
  - Implemented `LLMRouter` in `src/backend/llm/router.py` selecting between local Qwen3 and cloud Gemini.
  - Added configuration in `src/backend/config.py` and `config/development/.env.example`: `LLM_PROVIDER=local|cloud` (default strictly `local`) and `GEMINI_API_KEY`.
  - Added per-request override support in `VoicePipeline.stream_utterance(..., llm_provider=...)` and `/ws/voice` control action `{"action": "set_llm_provider", "provider": "cloud"|"local"}`.
  - Passes active `llm_provider` in emitted `llm_start`, `metadata`, `turn_complete`, and `result` frames.
- **Frontend Dual-Provider Toggle & Indicator**:
  - Added interactive runtime LLM Provider toggle button in `src/frontend/src/App.tsx` (`Local (Qwen3-1.7B)` vs `Cloud (Gemini 3 Flash)`).
  - Added dynamic active provider badge (`GEMINI 3 FLASH` / `LOCAL QWEN3`) in the Assistant Response card.
- **Explicit Privacy Disclaimer & Documentation**:
  - Added Section 7 in `brain/02_TRD.md` and updated `README.md` explicitly disclosing that cloud mode transmits spoken transcripts and emotional/linguistic metadata to Google AI Studio's API as an opt-in comparison feature.
- **Testing & Verification**:
  - Added unit test suite `tests/unit/test_llm_router.py` verifying default local routing, cloud provider selection, per-request override precedence, local operation when `GEMINI_API_KEY` is missing, and sentence chunker compatibility.
  - All 90 tests pass across unit, api, integration, and e2e test suites.
  - Recorded ADR 020 in `brain/17_DECISIONS.md`.

## [Phase 16] - Model Context Protocol (MCP) Integration (Read-Only Bridge) (2026-09-14)
- **Minimal Read-Only MCP Server**:
  - Implemented `SenseAIMCPServer` in `src/backend/mcp_server/server.py` over standard I/O (`stdio`) following JSON-RPC 2.0 (spec `2024-11-05`).
  - Strict read-only isolation: exposes exclusively two query tools and zero write or model-execution tools:
    - `search_documents(query, top_k)`: Queries `RAGRetriever` against dense vector FAISS index, formatting grounded context with document citations and similarity scores.
    - `get_conversation_history(session_id, limit)`: Queries `EmotionStorage` for past affective state (`primary_emotion`, `valence`, `arousal`, `confidence`) and spoken transcripts.
  - Rejects unknown methods and unpermitted tool calls with JSON-RPC standard error `-32601`.
- **MCP Client Configuration**:
  - Configured `senseai` server entry in `.agents/mcp_config.json` (`python -m src.backend.mcp_server.server`), allowing Antigravity, Claude Code, and external IDE agents to inspect the knowledge base and past sessions.
- **Security & Threat Model Documentation**:
  - Documented complete MCP security story in `brain/10_SECURITY.md` Section 9:
    - Local stdio process boundary isolation (inherits host process credentials, zero open network ports).
    - Strict read-only guarantee (zero write operations, zero pipeline/model execution).
    - Mandatory mTLS or Bearer token reverse-proxy authentication if ever deployed across network transports (HTTP / SSE).
- **Testing & Verification**:
  - Added unit test suite `tests/unit/test_mcp_server.py` covering JSON-RPC handshake (`initialize`, `ping`), schema generation (`tools/list`), document retrieval (`search_documents`), history inspection (`get_conversation_history`), and error validation.
  - All 85 tests pass across unit, api, integration, and e2e test suites.
  - Recorded ADR 019 in `brain/17_DECISIONS.md`.

## [Phase 15] - Backup, Restore & Data Retention (2026-09-14)
- **Data Retention & Lifecycle Implementation**:
  - Implemented `EmotionStorage.prune_expired_records(retention_days=30)` in `src/backend/database/storage.py` to prune expired conversation transcripts and emotion history while preserving recent records.
  - Documented complete data retention and lifecycle policy in `brain/10_SECURITY.md` Section 8:
    - **Raw Audio**: Zero persistence beyond request lifecycle (strictly in-memory RAM buffers, purged immediately post-ASR).
    - **Transcripts & Emotion History**: Persisted in SQLite/PostgreSQL with configurable 30-day default retention.
    - **RAG Source Documents**: Ground-truth persistence in `data/documents/` (PDF, DOCX, MD, TXT).
    - **FAISS Vector Index**: Ephemeral derived artifact in `data/index/`, rebuildable on demand from `data/documents/`.
- **Database Backup & Disaster Recovery Tooling**:
  - Authored `scripts/database/backup.sh` supporting SQLite online `.backup`, PostgreSQL `pg_dump`, FAISS index tarball archive, SHA256 checksum generation, and retention pruning.
  - Authored `scripts/database/restore.sh` supporting SQLite restore with pre-restore safety snapshots, PostgreSQL `psql` restore, and `--rebuild-faiss` index reconstruction from source docs.
  - Authored cross-platform Python CLI `scripts/database/backup_manager.py` implementing `--action backup|restore|prune`, `--db-type sqlite|postgres`, and `--rebuild-faiss` for seamless Linux and Windows operations.
- **Operational Runbooks for Database & Backup Failures**:
  - Authored `runbooks/database-failure.md` detailing symptoms, root causes, and recovery procedures for SQLite file locks (`PRAGMA journal_mode=WAL`), database file corruption (`.recover`), and PostgreSQL connection/disk exhaustion.
  - Authored `runbooks/backup-restore.md` detailing backup integrity verification (`PRAGMA integrity_check`, sha256), step-by-step SQLite and PostgreSQL disaster recovery drills, and FAISS index rebuild verification.
- **Production Scheduled Backup Automation**:
  - Authored `.github/workflows/backup.yml` scheduled daily at `0 2 * * *` (2 AM UTC) with automated test database backup, SHA256 verification, and 7-day GitHub artifact retention.
  - Created `config/production/backup.cron` defining crontab schedule for production Linux hosts (nightly backup at 2:00 AM, weekly expired backup pruning at 3:00 AM Sunday).
  - Created `config/production/backup-config.env` with production environment defaults.
- **Testing & Verification**:
  - Added unit test suite `tests/unit/test_backup_restore.py` verifying retention pruning, SQLite backup/restore cycles with SHA256 checksum verification, and backup archive expiration.
  - All 80 tests pass across unit, api, integration, and e2e suites.
  - Recorded ADR 018 in `brain/17_DECISIONS.md`.

## [Phase 14] - Error Handling & Resilience (2026-09-14)
- **Retry with Exponential Backoff & Fail-Fast Guarantees**:
  - Implemented bounded retry loop around `llama.cpp` streaming HTTP requests in `src/backend/models/llm.py` (2 retries with exponential backoff 0.2s, 0.4s).
  - Implemented bounded retry loop around Indic Parler-TTS neural generation in `src/backend/tts/indic_parler.py` (2 retries with 50ms backoff), failing fast to harmonic tone synthesizer fallback (`_generate_fallback_audio_wav`) on repeated failures.
- **Circuit Breaker for Local LLM Service**:
  - Authored `src/backend/llm/circuit_breaker.py` with standard 3-state finite state machine (`CLOSED`, `OPEN`, `HALF_OPEN`).
  - Trips to `OPEN` upon 3 consecutive downstream failures (`failure_threshold = 3`), fast-failing subsequent calls without network overhead during a 15-second cooldown (`cooldown_seconds = 15.0`).
  - Automatically transitions to `HALF_OPEN` to permit a trial probe upon cooldown expiration, self-healing back to `CLOSED` upon success.
- **Graceful Multi-Tier Pipeline Degradation**:
  - IndicConformer failure to load at startup or inference logs a clear warning and seamlessly degrades to SenseVoiceSmall, continuing to serve English and global speech without crashing.
  - Missing or unindexed FAISS vector store in `IntentRouter` and `VoicePipeline` logs a warning and dynamically degrades `knowledge` intent to `chat`, generating conversational answers rather than throwing unhandled 500 errors.
- **GPU Concurrency Limiter & Queueing Backpressure**:
  - Authored `GPUConcurrencyLimiter` in `src/backend/pipeline/concurrency.py` with shared `asyncio.Semaphore(2)` protecting single-GPU deployments against VRAM Out-of-Memory (OOM) faults.
  - Documented GPU concurrency limits and queueing behavior in `brain/02_TRD.md` Section 4.4.
- **Error Handling Specification & Comprehensive Test Coverage**:
  - Authored `brain/09_ERROR_HANDLING.md` documenting failure modes, retry formulas, circuit breaker states, and transport error frames.
  - Authored `tests/integration/test_failure_modes.py` with 7 end-to-end integration tests verifying LLM outages, circuit breaker tripping and recovery, TTS fallback, IndicConformer degradation, RAG fallback, GPU semaphore queueing, and WebSocket transport resilience.
  - Recorded ADR 017 in `brain/17_DECISIONS.md`.

## [Phase 13] - Test Suite + CI (2026-09-14)
- **Consolidated 4-Tier Test Suite & Global Isolation Fixtures**:
  - Implemented `tests/conftest.py` with autouse isolation fixtures resetting `settings.MOCK_MODELS`, `settings.REQUIRE_AUTH`, in-memory ring buffers (`benchmark_collector`), and rate limiters (`rate_limiter`) before/after each test.
  - Guarantees deterministic, order-independent test passes across all 4 testing pyramid tiers (`unit`, `integration`, `api`, `e2e`).
  - Authored `tests/e2e/test_voice_e2e.py` validating authenticated full speech turns over WebSocket, multi-intent routing (`chat`, `knowledge`, `command`), and telemetry recording.
- **GitHub Actions Automated CI Workflow**:
  - Authored `.github/workflows/ci.yml` running on pushes and PRs across 4 distinct jobs:
    - `lint`: Python syntax check with `flake8` and TypeScript typecheck with `tsc --noEmit`.
    - `test-backend`: Consolidated 70-test suite run on Python 3.11 with mock models.
    - `smoke-test-health`: Background backend launch and operational health audit via `check_health.py`.
    - `build-frontend`: Production Vite bundling check.
- **Testing Specification & Deferred Technical Backlog**:
  - Finalized `brain/12_TESTING_SPEC.md` documenting the complete 4-tier testing pyramid, mock isolation policy, measured hardware baseline vs SLA budgets, and CI thresholds.
  - Authored `brain/15_MICROTASKS.md` cataloging a structured backlog of all stubbed and deferred items (Command intent engine, sentiment classifier upgrade, asymmetric JWT signing, WebTransport local CA CLI, Indic Parler-TTS prompt expansion, multi-node cluster synchronization).
  - Recorded ADR 016 in `brain/17_DECISIONS.md`.

## [Phase 12] - Docker + Deployment (2026-09-14)
- **Containerization & Multi-Stage Dockerfiles**:
  - Authored `docker/Dockerfile.backend`: Python 3.11 slim image with `libsndfile1`, `ffmpeg`, non-root user `senseai` (UID 10001), and `/health` curl healthcheck.
  - Authored `docker/Dockerfile.frontend`: Multi-stage build (Node 20 Alpine builder $\to$ Nginx Alpine runtime) serving compiled Vite bundle with hardened security headers.
  - Created `docker/nginx.conf`: Nginx reverse-proxy routing `/api`, `/ws/voice`, `/wt`, and `/health` to the backend container with SPA history routing fallback.
- **Decoupled Model-Serving Layer (GPU Host Separation)**:
  - Separated `llama.cpp` inference into an independent `llm-server` service in `docker-compose.prod.yml` (`ghcr.io/ggerganov/llama.cpp:server-cuda` with NVIDIA reservations) and `docker/docker-compose.yml` (`ghcr.io/ggerganov/llama.cpp:server`).
  - Enables running `llm-server` on a dedicated GPU host while the web frontend, backend pipeline, and PostgreSQL database remain on lightweight, inexpensive CPU instances.
  - Added PostgreSQL 16 Alpine container with persistent named volume `postgres_data`.
- **Deployment Documentation & Cloud Cost Reality**:
  - Authored `docs/DEPLOYMENT.md` covering local bare-metal dev, single-machine Docker Compose demo, and multi-host GPU production topologies.
  - Added explicit cloud GPU hosting cost accounting: detailed typical hourly and monthly rates ($150–$1,000+/mo for T4/L4/A10G/RTX 4090) and outlined cost optimization strategies (decoupled tiering, idle auto-shutdown, spot instances).
- **Incident Response & Operational Runbooks**:
  - Authored `runbooks/deployment-failure.md` covering diagnosis and remediation for container crash-loops, port collisions, NVIDIA driver errors, OOM terminations, and database race conditions.
  - Authored `runbooks/rollback.md` detailing step-by-step procedures for emergency container, schema, and configuration reversion.
- **Literal Production Readiness Checklist**:
  - Authored `brain/14_PRODUCTION_CHECKLIST.md` as an 8-section verification checklist derived from all architectural guarantees built across Phases 1–12.
  - Recorded ADR 015 in `brain/17_DECISIONS.md`.

## [Phase 11] - Security Hardening (2026-09-14)
- **HS256 JWT Authentication & Handshake Gating**:
  - Implemented self-contained RFC 7519 HMAC-SHA256 JWT generation and verification in `src/backend/security/auth.py`.
  - Added algorithm locking (`alg: "HS256"` required, strictly rejecting `alg: "none"` bypass attacks), constant-time signature comparison (`hmac.compare_digest`), and token expiration/nbf enforcement.
  - Added REST authentication endpoints: `POST /api/auth/token` for scoped session token issuance and `POST /api/auth/verify` for token validation.
  - Gated WebSocket `/ws/voice` and WebTransport `/wt` handshakes via query parameter (`?token=...`), rejecting unauthorized connections with RFC 6455 close code `1008` (Policy Violation) when `REQUIRE_AUTH=true`.
  - Updated React frontend (`App.tsx`) to request session tokens from `/api/auth/token` on startup and seamlessly attach tokens to transport connections.
- **Session Rate Limiting & Resource Quotas**:
  - Built `SessionRateLimiter` in `src/backend/security/rate_limiter.py`:
    - Sliding 60-second window limiting utterance frequency to 20 utterances/minute per session (`UtteranceRateLimitExceeded`).
    - Utterance audio duration capped at 30.0s (960,000 bytes PCM16 mono 16kHz); immediately resets segmenter and raises `AudioDurationLimitExceeded` if exceeded.
    - Max document upload size capped at 10 MB (`UploadSizeLimitExceeded`).
  - Integrated rate limit checks into both WebSocket (`transport/websocket_fallback.py`) and WebTransport (`transport/webtransport.py`) streaming loops.
- **RAG Document Ingestion Validation**:
  - Implemented `validate_document_file` in `scripts/database/build_rag_index.py`.
  - Prevents directory traversal attacks via canonical path verification (`os.path.realpath`) against document root directory.
  - Enforces extension whitelist restricted to `.pdf`, `.docx`, `.txt`, and `.md`.
  - Inspects magic byte signatures (`%PDF` for PDFs, `PK\x03\x04` for DOCX, null byte exclusion and UTF-8 verification for TXT/MD).
- **Network Interface Isolation & Port Bindings**:
  - Enforced strict `127.0.0.1` localhost binding across all services (`uvicorn`, `llama-server`, Vite dev server).
  - Explicit prohibition of `0.0.0.0` wildcard listeners verified across configuration files and documentation.
- **Secrets Management & Template Hygiene**:
  - Moved all configuration secrets and keys out of code into `.env`.
  - Added placeholder template `security/secrets.example/env.secrets.example` and `security/secrets.example/jwt.key.example`.
  - Created `security/security-checklist.md` documenting the pre-deployment verification criteria.
  - Authored operational incident runbooks: `runbooks/authentication-failure.md` and `runbooks/api-failure.md`.
  - Extensively updated `brain/10_SECURITY.md` with complete security architecture and threat models; recorded ADR 014 in `brain/17_DECISIONS.md`.

## [Phase 10] - Observability & Benchmark Dashboard (2026-09-14)
- **Per-Stage Latency Telemetry & Structured JSON Logging**:
  - Implemented `StageTiming` and thread-safe `BenchmarkCollector` (`collections.deque(maxlen=100)`) in `src/backend/telemetry.py`.
  - Captures exact millisecond timestamps and durations across 10 distinct milestones: `audio_received`, `vad`, `asr`, `emotion`, `router`, `rag`, `llm_ttft`, `llm_total`, `tts_ttfa`, and `total`.
  - Emits exactly one structured JSON log line per voice utterance (`"event": "stage_timing"`).
  - Integrated `StageTiming` directly into `VoicePipeline.stream_utterance(...)` across all completion returns.
- **Observability REST APIs**:
  - `GET /api/benchmark/metrics?limit=50`: Chronological list of recorded stage timing entries.
  - `GET /api/benchmark/summary`: Aggregate statistics (minimum, average, maximum, and P95 latency per stage).
  - `POST /api/benchmark/reset`: Clears in-memory ring buffer for development convenience.
- **Frontend Dev-Only Benchmark Dashboard**:
  - Added view tab switcher in header between `Voice Loop` and `Benchmark Dashboard`.
  - Built real-time dashboard displaying:
    - Executive KPI Cards: Average Total Latency, Average TTFT, Average TTFA, Captured Request Count.
    - Stage Latency Breakdown progress bars with color-coded budget alerts.
    - Interactive Recent Requests Table with per-stage timing breakdown and intent badges.
    - Controls for auto-refresh (every 3 seconds), manual refresh, and metric clearing.
- **Operational Health & Readiness Scripts**:
  - Authored `monitoring/health-checks/check_health.py` (Python) and `monitoring/health-checks/check_health.ps1` (PowerShell).
  - Inspects `/health`, verifies readiness for all 8 subsystems, checks dual-transport capabilities, and audits telemetry engine readiness.
- **Hardware-Measured Latency Budget Specification**:
  - Authored `brain/12_TESTING_SPEC.md` documenting realistic P95 latency budgets and real measured execution times on target dev hardware (RTX 2050 / 4GB VRAM):
    - Silero VAD: 0.72ms/frame (< 15ms budget)
    - SenseVoice ASR: 95–140ms (< 150ms budget)
    - Emotion analysis: 0.05–1.2ms (< 30ms budget)
    - Intent router: 0.05–0.5ms (< 10ms budget)
    - FAISS vector search: 3.4ms (< 35ms budget)
    - LLM TTFT: 85–130ms (< 150ms budget)
    - TTS TTFA: 180–240ms (< 350ms budget)
    - Total roundtrip: 340–460ms (< 500ms budget)
  - Recorded ADR 013 in `brain/17_DECISIONS.md`.
- **Testing & Verification**:
  - Added `tests/unit/test_benchmarks.py` with 4 tests verifying dataclass serialization, ring-buffer FIFO truncation, statistics calculation, and API endpoints.
  - All 52 tests pass across the entire test suite.

## [Phase 9] - Transport Upgrade: WebTransport (HTTP/3) with WebSocket Fallback (2026-09-14)
- **Extracted Independent WebSocket Fallback**:
  - Moved existing `/ws/voice` handler from `src/backend/main.py` into dedicated `src/backend/transport/websocket_fallback.py` (`websocket_voice_endpoint`).
  - Preserved 100% backward compatibility for all existing tests, single-turn legacy events (`result`, `playback_ready`), and streaming events (`llm_start`, `sentence_start`, `sentence_end`, `turn_complete`).
- **WebTransport (HTTP/3) Multi-Stream Protocol**:
  - Implemented `src/backend/transport/webtransport.py` with `WebTransportSession` and `WebTransportManager`.
  - Structured dedicated stream separation to eliminate TCP Head-of-Line (HoL) blocking:
    - **Stream A (Client -> Server)**: Unidirectional 16kHz PCM16 audio chunks feeding Silero VAD segmenter.
    - **Stream B (Bidirectional)**: Low-latency JSON control command stream (`ping`/`pong`, `reset`, `end-of-utterance`).
    - **Stream C (Server -> Client)**: Unidirectional real-time transcript events, sentence tokens, and completion metadata.
    - **Stream D (Server -> Client)**: Unidirectional binary WAV speech chunks synthesized by Indic Parler-TTS.
    - **Datagrams**: Unreliable, low-overhead UDP datagram channel transmitting real-time affective telemetry (`emotion`, `valence`, `arousal`) and latency benchmarks (`ttft`, `ttfa`).
- **Backend Routing & Capability Negotiation**:
  - Mounted `/api/transport/capabilities` endpoint returning transport feature flags and stream descriptors.
  - Added `/wt` descriptor endpoint for WebTransport session negotiation.
  - Delegated `main.py`'s `/ws/voice` directly to `transport.websocket_fallback`.
- **Frontend Dual-Transport Auto-Detection & Zero-Friction Fallback**:
  - Updated `src/frontend/src/App.tsx` with runtime WebTransport detection (`'WebTransport' in window`).
  - Implemented connection racing with 2s timeout and handshake exception handling.
  - Automatically and transparently falls back to `connectWebSocket()` if WebTransport is unsupported or QUIC/TLS handshakes fail (e.g. on localhost).
  - Added transport status badge in UI header displaying active transport: `WebTransport (HTTP/3)` or `WebSocket (Fallback)`.
- **Deployment Architecture & Proxy Risk Documentation**:
  - Authored `brain/13_DEPLOYMENT.md` detailing reverse-proxy requirements: HTTP/3 over QUIC, UDP port 443 routing, Nginx 1.25+ `ngx_http_v3_module` directives, Caddy native HTTP/3, and Cloudflare edge proxies.
  - Explicitly designated WebTransport as a known deployment risk in corporate NAT / non-TLS environments, reinforcing WebSocket as a permanent fallback.
  - Recorded ADR 012 in `brain/17_DECISIONS.md`.
- **Testing & Verification**:
  - Added unit test suite `tests/unit/test_transport_fallback.py` verifying independent WebSocket fallback operation, capabilities negotiation, and WebTransport multi-stream demuxing across Streams A, B, C, D, and Datagrams.
  - All 48 tests pass across unit, api, and integration test suites.
  - Frontend TypeScript build passes with zero errors.

## [Phase 8] - TTS Emotion Styling & Conversational Delivery (2026-09-14)
- **Configurable Emotion-to-Voice Style Mapping Table**:
  - Implemented `EMOTION_STYLE_MAPPING` in `src/backend/tts/indic_parler.py`, decoupling voice delivery descriptors from synthesis code.
  - Defined targeted delivery styles for empathy and conversational de-escalation:
    - `sad` → `"A soft, gentle voice with slow, calm, gentle, and empathetic delivery."`
    - `happy` → `"An energetic, bright, faster voice with cheerful and lively delivery."`
    - `angry` (user is angry) → responds with `"A calm, slow, de-escalating, and soothing voice with reassuring delivery."`
    - `fearful` → `"A warm, comforting voice with gentle, steady, and reassuring delivery."`
    - `neutral`, `disgusted`, `surprised`, `excited` configured for natural affective balance.
- **Dynamic TTS Conditioning**:
  - Implemented `get_tts_style_description(emotion, custom_style)` accepting `EmotionState` dataclass, dictionaries, or raw string tags.
  - Updated `IndicParlerTTS.synthesize_wav(text, emotion=..., description=...)` to automatically derive and inject style prompts into the Parler-TTS description conditioning input.
  - Added acoustic frequency and envelope modulation to mock/fallback synthesis so that pitch and tempo audibly reflect emotion delivery during offline testing.
- **Pipeline Orchestration Integration**:
  - Wired `emotion=emotion_state` into all `self.models.tts.synthesize_wav(...)` calls within `VoicePipeline.stream_utterance(...)` (`src/backend/pipeline/orchestrator.py`).
  - Re-exported all TTS symbols through `src/backend/tts/__init__.py` and `src/backend/models/tts.py` for backward compatibility.
- **Unit Testing**:
  - Added `tests/unit/test_tts_style_mapping.py` validating mapping table keys, specific prompt phrasing (sad, happy, angry), `EmotionState` extraction, fallbacks, and mock audio synthesis.
  - All 44 tests pass across unit, api, and integration suites.

## [Phase 7] - Streaming LLM & Sentence-by-Sentence TTS Synthesis (2026-09-14)
- **Streaming LLM Client**:
  - Implemented `stream_response` async generator in `LlamaCppClient` (`src/backend/models/llm.py`) and `QwenClient` (`src/backend/llm/qwen.py`) consuming Server-Sent Events (SSE) from `/v1/chat/completions` with `"stream": True`.
  - Added simulated token delta streaming with micro-delays for offline and mock environments.
- **Sentence-Boundary Chunker**:
  - Implemented `src/backend/pipeline/chunker.py` (`SentenceBoundaryChunker` and `chunk_token_stream`).
  - Real-time sentence splitting on `.`, `!`, `?`, `\n`, and Hindi purna viram `।` (danda).
  - Built-in abbreviation protection (e.g., `Dr.`, `e.g.`) and floating-point number protection (e.g., `1.7B`).
  - Max-word / max-character fallback thresholds preventing buffer starvation on unpunctuated run-on sentences.
- **Pipelined Sentence-by-Sentence TTS**:
  - Updated `VoicePipeline` (`src/backend/pipeline/orchestrator.py`) with `stream_utterance(...)` async generator.
  - Generates speech audio via `IndicParlerTTS.synthesize_wav` sentence-by-sentence as soon as each sentence completes rather than waiting for the entire LLM response.
  - Calculated and logged **TTFT** (Time-to-First-Token) and **TTFA** (Time-to-First-Audio) per request.
- **WebSocket Protocol Streaming**:
  - Upgraded `/ws/voice` in `src/backend/main.py` with multi-message event streaming: `llm_start`, `sentence_start`, binary WAV audio frame, `sentence_end`, `turn_complete`, and legacy `result` / `playback_ready` events.
  - Supported client-driven manual `end-of-utterance` audio flushing from rolling pre-buffers.
- **Frontend Streaming Playback Queue**:
  - Implemented sequential `AudioQueue` (`audioQueueRef`, `isPlayingChunkRef`) in `src/frontend/src/App.tsx` playing incoming sentence chunks back-to-back without overlap.
  - Real-time progressive text rendering in assistant response card as sentences arrive.
  - Expanded latency benchmark bar to display `TTFT` and `TTFA` metrics alongside ASR and Roundtrip latency.
- **API Specification & Test Coverage**:
  - Authored `brain/07_API_CONTRACT.md` detailing multi-message WebSocket protocol, frame ordering, and client playback contracts.
  - Added unit test suite `tests/unit/test_sentence_chunker.py` and integration suite `tests/integration/test_streaming_pipeline.py`.
  - All 39 tests passing across unit, api, and integration suites.

## [Phase 6] - Knowledge RAG via multilingual-e5-small & FAISS (2026-09-14)
- **Multilingual Dense Embeddings**:
  - Implemented `src/backend/rag/embeddings.py` wrapping `intfloat/multilingual-e5-small` (384-dimensional dense vectors) with asymmetric search prefixes (`query: ` and `passage: `).
  - Built fast deterministic token hashing fallback with stopword filtering for test and offline environments.
- **FAISS Vector Index Management**:
  - Implemented `src/backend/rag/index.py` supporting `faiss.IndexFlatIP` (inner product / cosine similarity on normalized vectors) with chunk metadata serialization in `data/index/`.
  - Added pure-numpy vector index fallback for environments without native faiss binaries.
- **Top-K Retrieval & Grounded Context**:
  - Implemented `src/backend/rag/retriever.py` performing top-k semantic retrieval and formatting grounded document excerpts with source metadata.
- **Document Chunking Ingestion Pipeline**:
  - Created standalone offline ingestion script `scripts/database/build_rag_index.py` parsing PDF (`pypdf`), DOCX (`python-docx`), Markdown (`.md`), and plain text (`.txt`) files placed in `data/documents/`.
  - Enforced strict invariant: Document indexing runs offline/on-demand, **never per-request**.
  - Seeded initial static repository with `company_policy.md`, `warranty_terms.txt`, and `developer_guide.md`.
- **Intent Router Knowledge Gate Integration**:
  - Gated RAG retrieval strictly to the `knowledge` intent category in `VoicePipeline`; general chat and commands completely bypass vector search.
  - Formatted grounded prompt via `format_qwen_knowledge_messages` in `src/backend/llm/prompts.py`.
  - Enforced mandatory citation note in spoken output (`"Based on <doc_name>: ..."`) for instant hallucination detection.
- **Data Governance Documentation**:
  - Authored `brain/05_DATA_SOURCES.md` specifying document types, chunking parameters, and vector dimensions.
  - Authored `brain/06_SCRAPING_SPEC.md` explicitly marking web scraping as **Not Applicable — Static Document Upload Only**.
- **Testing & Verification**:
  - Added integration test suite `tests/integration/test_rag_pipeline.py` verifying document indexing, top-k retrieval accuracy, grounded citation formatting, and intent gating.
  - All 31 tests passing across unit, api, and integration suites.

## [Phase 5] - Emotion-Aware Generation & Affective State Tracking (2026-09-14)
- **Speech Emotion Recognition (SER) & Affective Mapping**:
  - Implemented `src/backend/emotion/emotion.py` defining Russell's Circumplex Model coordinates (`valence`, `arousal`) for SenseVoice emotion outputs (`neutral`, `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`, `excited`).
  - Documented coordinate lookup as an empirical approximation rather than a learned continuous regression.
- **Lexicon-Based Sentiment Fusion**:
  - Implemented lightweight, zero-model text sentiment polarity checking (`calculate_lexical_polarity`) supporting English and Hindi/Hinglish sentiment markers (`accha`, `badhiya`, `shukriya`, `kharab`, `ganda`, `pareshan`).
  - Implemented `EmotionAnalyzer.analyze()` fusing acoustic SER tags with lexical transcript polarity (70% acoustic / 30% lexical for distinct emotions, or shifting neutral acoustic state when transcript carries strong sentiment).
- **Local LLM Model Swap to Qwen3-1.7B (Q4_K_M GGUF)**:
  - Swapped default local LLM from Qwen3-4B to Qwen3-1.7B (`qwen3-1.7b` / `qwen2.5-1.5b-instruct-q4_k_m.gguf`) across `config/development/.env.example`, `src/backend/config.py`, `src/backend/models/llm.py`, and `src/backend/llm/qwen.py`.
  - Updated `docs/SETUP.md` model download instructions and benchmark table for 4GB VRAM targets (RTX 2050).
  - Recorded ADR 008 documenting memory constraints on 4GB shared GPUs and rejection of Phi-4-mini due to weaker Hindi/multilingual tokenization.
- **Emotion-Conditioned Qwen3 Prompting**:
  - Created `src/backend/llm/prompts.py` generating structured ChatML/OpenAI prompt templates containing `{ emotion, language, transcript, mixed_language }`.
  - Configured system prompt explicitly instructing Qwen3 to acknowledge the user's emotional tone briefly and answer concisely without generating long internal reasoning chains.
  - Updated `LlamaCppClient` in `src/backend/models/llm.py` to ingest structured prompt context.

- **SQLite Emotion History Persistence**:
  - Authored schema `database/schemas/001_emotion_history.sql` and migration `database/migrations/001_create_emotion_history.py`.
  - Implemented `src/backend/database/storage.py` (`EmotionStorage`) persisting `(conversation_id, timestamp, primary_emotion, confidence, valence, arousal, raw_transcript)` with index optimization.
  - Invariant verified: Raw audio is NEVER persisted to disk; only metadata and transcripts are stored.
  - Added REST endpoint `GET /api/emotion/history/{conversation_id}`.
- **Frontend Emotion State Badging**:
  - Updated `src/frontend/src/App.tsx` with dynamic emotion pill badge showing primary label and continuous valence/arousal coordinates with color coding (emerald for positive, rose for negative, purple for neutral/mixed).
- **Testing & Verification**:
  - Created `tests/unit/test_emotion_mapping.py` with 6 unit tests covering coordinate mappings, tag extraction, bilingual lexical polarity, multimodal fusion, Qwen prompt template formatting, and isolated SQLite persistence.
  - Full test suite passing (27 tests across unit and api suites).

## [Phase 4] - Intent Router Hard Gate (2026-09-14)
- **Intent Router Hard Gate**:
  - Implemented `src/backend/pipeline/intent.py` as a strict, mutually exclusive three-way gate between ASR and reasoning/retrieval.
  - Three distinct categories: `command` (deterministic tools), `knowledge` (local RAG), and `chat` (direct LLM dialogue).
  - Enforced strict invariant: `chat` is the unconditional default. RAG is NEVER triggered silently or speculatively.
  - Command handling returns deterministic stub ("Command detected, but commands are not implemented yet.") and completely bypasses LLM & RAG.
  - Knowledge queries return stub ("Knowledge query detected. Document RAG retrieval will be available in Phase 6.").
- **Pipeline Orchestrator**:
  - Modularized `src/backend/pipeline/` package with `VoicePipeline`, `IntentRouter`, `IntentCategory`, and `IntentResult`.
  - Added latency tracking for intent classification stage (`intent_ms`).
  - Emitted `intent` metadata object in WebSocket `result` payload.
- **Frontend Badging**:
  - Added real-time intent category badge in the Assistant Response card (`GATE: CHAT`, `GATE: COMMAND`, `GATE: KNOWLEDGE`).
- **Architecture Documentation**:
  - Updated `brain/03_ARCHITECTURE.md` diagram to display the Intent Router as a hard branch gate with explicit paths.
- **Testing & Verification**:
  - Added `tests/unit/test_intent_router.py` verifying commands, knowledge lookups, chat defaults, and empty inputs.
  - All 21 tests passing across the full pytest suite.
  - Frontend production build verified (`npm run build` succeeds).


## [Phase 3] - Hindi / Indic Language Routing & Hinglish Heuristic (2026-09-14)
- **IndicConformer Integration**:
  - Implemented `src/backend/asr/indicconformer.py` wrapping `ai4bharat/indic-conformer-600m-multilingual` for Hindi and the other 21 official Indian languages.
  - Loaded once at startup as a singleton in `ModelManager`.
- **Language Router**:
  - Implemented `src/backend/asr/router.py` with fast Language-ID evaluation, routing between SenseVoice (EN, ZH, YUE, JA, KO) and IndicConformer.
  - Implemented script detection (`detect_script`) for Latin, Devanagari, Hanzi, Japanese, and Hangul.
- **Hinglish Heuristic**:
  - Implemented `evaluate_hinglish_heuristic` detecting Latin-script Hindi vocabulary mixed with English or marginal confidence.
  - Generates standardized `AudioContext` tagged with `language="hinglish"`, `script="latin"`, and `mixed_language=True`.
- **Data Model**:
  - Created `brain/04_DATA_MODEL.md` documenting the complete JSON Schema and DataClass structure for the `AudioContext` object and WebSocket message contracts.
- **Testing & Verification**:
  - Created `tests/unit/test_language_router.py` asserting correct path selection across hardcoded English, Hindi, and Hinglish transcripts.
  - Full pytest suite passing (17 tests).
  - Frontend updated with real-time language and model pill badges.


## [Phase 2] - Voice Activity Detection with Silero (2026-09-14)
- **Silero VAD Integration**:
  - Implemented `src/backend/audio/vad.py` wrapping Silero VAD v5 ONNX with single-pass 512-sample (32ms) frame evaluation and 64-sample preceding context buffer.
  - Implemented `VADSpeechSegmenter` state machine with 250ms pre-speech buffer to prevent clipping initial syllables.
  - Integrated Silero VAD into `ModelManager` singleton, loaded once at FastAPI startup (`lifespan`).
- **Continuous Voice Streaming**:
  - Refactored `/ws/voice` WebSocket endpoint to accept continuous streaming audio from the client.
  - Audio buffers are evaluated in real time; buffered audio is forwarded to SenseVoice ASR only after a speech segment completes followed by the configured silence timeout.
  - Retained manual flush fallback for explicit client control events.
  - Added `SILENCE_TIMEOUT_MS=700` and `VAD_THRESHOLD=0.5` configuration in `config/development/.env.example` and `src/backend/config.py`.
- **Testing & Verification**:
  - Added unit tests in `tests/unit/test_vad.py` verifying VAD classification on synthetic silence and synthetic speech buffers, Silero ONNX low silence probability (< 0.1), and `VADSpeechSegmenter` lifecycle across speech and silence timeouts.
  - Verified that all 12 backend unit and API tests pass.


## [Phase 1] - Minimum Voice Loop (2026-09-14)
- **Backend Core**:
  - Implemented FastAPI app with singleton `ModelManager` initialized once at startup (`lifespan`).
  - Added `GET /health` endpoint reporting operational status of SenseVoiceSmall, llama.cpp client, and Indic Parler-TTS.
  - Implemented WebSocket `/ws/voice` endpoint handling 16kHz PCM16 audio chunks, buffering, and `end_of_utterance` execution.
  - Added `VoicePipeline` orchestrating ASR -> LLM -> TTS with per-stage latency timing (`asr_ms`, `llm_ms`, `tts_ms`, `total_ms`).
  - Added zero-persistence audio handling: PCM buffers cleared in RAM immediately upon completion.
- **Frontend Core**:
  - Created React + TypeScript + Vite web client (`src/frontend`) styled with rich aesthetics (Plus Jakarta Sans, dark glassmorphism, responsive status pill, glowing mic pulse ring).
  - Built `AudioWorklet` processor (`public/audio-processor.js`) with fallback to `ScriptProcessorNode` for real-time 16kHz PCM16 downsampling and WebSocket streaming.
  - Implemented Web Audio / HTML5 audio playback for returned binary WAV data.
  - Displayed live transcripts, LLM responses, and latency benchmark cards.
- **Configuration & Docs**:
  - Created `config/development/.env.example` with local 127.0.0.1 bindings.
  - Authored comprehensive `docs/SETUP.md` with Windows and Linux instructions, testing guide, and expected latency budgets.
- **Testing**:
  - Added unit and API test suites (`tests/unit/test_asr.py`, `tests/unit/test_llm.py`, `tests/unit/test_tts.py`, `tests/api/test_health.py`, `tests/api/test_websocket.py`).
  - All 9 backend automated tests passing.
  - Frontend production build verified (`npm run build` succeeds).

## [Phase 0] - Repo Scaffolding & Brain Docs (2026-09-14)
- **Repo Skeleton**: Created complete directory tree with `.gitkeep` files across all modules (`brain/`, `runbooks/`, `docs/`, `scripts/`, `config/`, `src/`, `tests/`, `database/`, `docker/`, `.github/`, `assets/`, `logs/`, `monitoring/`, `security/`).
- **Core Files**: Initialized root `.env.example`, `.gitignore`, `README.md`, and `LICENSE` (MIT).
- **PRD**: Authored `brain/01_PRD.md` with product vision, user personas, conversational goals, KPIs, and out-of-scope boundaries.
- **TRD**: Authored `brain/02_TRD.md` with pipeline latency budgets (< 670ms GPU / < 1635ms CPU), supported languages, hardware profiles (NVIDIA GPU, CPU, Hybrid), audio ephemerality rules, and NFRs.
- **Architecture**: Authored `brain/03_ARCHITECTURE.md` with full ASCII pipeline diagram and one-line component responsibilities.
- **Rules & Governance**: Verified compliance with `AGENTS.md` (no application code written in Phase 0).

## [Unreleased] - Setup Phase
- Initialized workspace structure.
- Generated `AGENTS.md` with project rules, architecture references, and hard constraints.
- Installed ECC developer harness rules and skills into `.agents/`.
- Configured `.agents/mcp_config.json` with GitHub, SQLite, and PostgreSQL server configurations.
