# VoiceSense AI — Current Architecture State & Audit Map

**Audit Timestamp:** 2026-09-20  
**Audit Scope:** Pre-migration truthful baseline audit of repository `NewSenseVoice` against `docs/architecture/target-architecture.md`.  
**Operating Environment:** Windows (PowerShell), Python 3.13.14, Node.js v26.8.2, npm 11.19.1.  
**Evidence Standard:** Every finding is tagged with `[VERIFIED]` (tested/executed in this session), `[READ]` (verified by direct code analysis), or `[UNKNOWN]` (cannot be confirmed without further execution/access).

---

## A. Current Architecture (As Implemented, Not As Intended)

The codebase currently implements a working Phase 1–18 monolithic voice pipeline rooted primarily under `src/backend/` and `src/frontend/`.

```text
                                [ React 18 + Vite Frontend ]
                                  (src/frontend/src/App.tsx)
                                             │
                                             ▼
                             [ WebSocket Transport: /ws/voice ]
                       (src/backend/transport/websocket_fallback.py)
                                             │
                                             ▼
                               [ FastAPI Ingress Layer ]
                                 (src/backend/main.py)
                                             │
                                             ▼
                                    [ Silero VAD ]
                              (src/backend/audio/vad.py)
                                             │ (Audio Chunks)
                                             ▼
                      [ Voice Pipeline Orchestrator Singleton ]
                       (src/backend/pipeline/orchestrator.py)
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
            [ Anti-Spoofing / Liveness ]            [ Language Router ]
             (src/backend/audio/liveness.py)          (src/backend/asr/router.py)
                                                                  │
                                       ┌──────────────────────────┴──────────────────────────┐
                                       ▼                                                     ▼
                             [ SenseVoiceSmall ASR ]                               [ IndicConformer-600m ]
                           (src/backend/models/asr.py)                        (src/backend/asr/indicconformer.py)
                           (English / Global + SER tag)                         (Hindi + Indic Languages)
                                       │                                                     │
                                       └──────────────────────────┬──────────────────────────┘
                                                                  ▼
                                                    [ Emotion Analyzer (SER + Lexical) ]
                                                       (src/backend/emotion/emotion.py)
                                                                  │
                                                                  ▼
                                                      [ SQLite Emotion Storage ]
                                                     (src/backend/database/storage.py)
                                                                  │
                                                                  ▼
                                               [ Intent Router (Hard Gate Classifier) ]
                                                    (src/backend/pipeline/intent.py)
                                                                  │
                               ┌──────────────────────────────────┼──────────────────────────────────┐
                               ▼                                  ▼                                  ▼
                     [ Branch: Command ]                [ Branch: Knowledge ]               [ Branch: Chat ]
                     (Local whitelist)                 (RAG: e5-small + FAISS)             (Default fallback)
                               │                       (src/backend/rag/retriever.py)                │
                               │                                  │                                  │
                               │                                  ▼                                  ▼
                               │                       [ Qwen3-1.7B Streaming via llama.cpp / Cloud Gemini ]
                               │                                (src/backend/llm/qwen.py / gemini.py)
                               │                                  │
                               └──────────────────────────────────┼──────────────────────────────────┘
                                                                  ▼
                                                   [ SentenceBoundaryChunker ]
                                                  (src/backend/pipeline/chunker.py)
                                                                  │
                                                                  ▼
                                                     [ Indic Parler-TTS Engine ]
                                                   (src/backend/tts/indic_parler.py)
                                                                  │ (WAV Audio Chunks)
                                                                  ▼
                                                [ WebSocket Audio Frame Stream ]
```

### Key Reality Points of Current Implementation [READ]:
1. **Repository Layout**: Monolithic layout under `src/backend/` and `src/frontend/`. Target architecture directories (`backend/`, `frontend/`, `ai/`, `rag/`, `tts/`, `deployment/`) do not exist at root.
2. **Model Lifecycle**: Singletons are loaded once at startup via `ModelManager` (`src/backend/models/manager.py`), instantiated in FastAPI's `lifespan` handler.
3. **Transport Layer**: Primary real-time transport is WebSocket (`src/backend/transport/websocket_fallback.py`). A stubbed WebTransport abstraction exists (`src/backend/transport/webtransport.py`), but does not have native HTTP/3 QUIC runtime serving enabled.
4. **Database**: Direct SQLite interaction via `sqlite3` in `src/backend/database/storage.py`. PostgreSQL is configured in `docker-compose.prod.yml`, but completely ignored by application code.
5. **Frontend State**: Document management and file uploads are simulated in React component local state (`src/frontend/src/components/DocumentManager.tsx`); no backend document upload API endpoint exists in `src/backend/main.py`.

---

## B. Working Components

The following components were empirically executed, verified, and found functional in this session:

| Component | File Path | Verification Status | Evidence / Metrics |
|---|---|---|---|
| **VAD Engine** | `src/backend/audio/vad.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_vad.py`). Supports ONNX runtime and synthetic test signals. |
| **Language Router** | `src/backend/asr/router.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_language_router.py`). Heuristics correctly classify Devanagari, Latin English, and Hinglish. |
| **Emotion Analysis** | `src/backend/emotion/emotion.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_emotion_mapping.py`). Russell's circumplex coordinates and lexical sentiment polarity fusion function properly. |
| **Intent Router (Hard Gate)** | `src/backend/pipeline/intent.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_intent_router.py`) and integration tests (`tests/integration/test_rag_pipeline.py`). Chat defaults cleanly; RAG never triggers on plain chat. |
| **Sentence Chunker** | `src/backend/pipeline/chunker.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_sentence_chunker.py`). Splits sentences on punctuation, abbreviations, decimals, and Indic danda (`।`). |
| **LLM Client & Router** | `src/backend/llm/qwen.py`, `router.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_llm.py`, `test_llm_client.py`, `test_llm_router.py`). Reasoning toggle and provider routing function as designed. |
| **Circuit Breaker & Resilience** | `src/backend/llm/circuit_breaker.py` | `[VERIFIED]` | Passed integration tests (`tests/integration/test_failure_modes.py`). Transitions from CLOSED → OPEN → HALF-OPEN on repeated failures. |
| **TTS Fallback & Style Mapping** | `src/backend/tts/indic_parler.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_tts.py`, `test_tts_style_mapping.py`) and integration tests (`tests/integration/test_failure_modes.py`). Emits harmonic audio on failure. |
| **RAG Retrieval & Index** | `src/backend/rag/retriever.py`, `index.py` | `[VERIFIED]` | Passed integration tests (`tests/integration/test_rag_pipeline.py`). Semantic search, citation formatting, and pure-numpy fallback work. |
| **Security & JWT Auth** | `src/backend/security/auth.py`, `rate_limiter.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_security_hardening.py`). Token creation, tamper rejection, expiration, rate limits, and duration caps work. |
| **Prompt Injection Filter** | `src/backend/pipeline/orchestrator.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_prompt_injection.py`). Inbound delimiters neutralized; system prompt and API key leaks redacted. |
| **MCP Server** | `src/backend/mcp_server/server.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_mcp_server.py`). JSON-RPC 2.0 stdio server exposes read-only tools `search_documents` and `get_conversation_history`. |
| **Telemetry & Latency Tracking** | `src/backend/telemetry.py` | `[VERIFIED]` | Passed unit tests (`tests/unit/test_benchmarks.py`). Stage timing ring buffer, min/avg/max/p95 stats, and API endpoints work. |
| **Health Check API** | `src/backend/main.py` | `[VERIFIED]` | Passed API test (`tests/api/test_health.py`). Reports model loading status and degraded state dynamically. |
| **WebSocket Protocol** | `src/backend/transport/websocket_fallback.py` | `[VERIFIED]` | Passed API tests (`tests/api/test_websocket.py`) and streaming tests (`tests/integration/test_streaming_pipeline.py`). Ping/pong, reset, and turn roundtrip work. |
| **E2E Voice Pipeline** | `tests/e2e/test_voice_e2e.py` | `[VERIFIED]` | Passed 3/3 E2E scenarios: streaming voice turn, multi-intent branching, and handshake verification. |
| **Frontend Build** | `src/frontend/` | `[VERIFIED]` | Built production bundle with `tsc && vite build` in 1.57s with 0 errors (`dist/index.html`, `dist/assets/index-BVRudXzu.js` 209 kB). |

---

## C. Broken Components (With Real Error Output)

During the audit test execution, 3 concrete test failures/hangs and 5 missing runtime dependency failures were captured with actual command output:

### 1. Test Hang: `test_authenticated_websocket_handshake_accepted` [VERIFIED]
- **File:** `tests/integration/test_security.py` (line 27)
- **Symptom:** Command hangs indefinitely waiting for WebSocket server message.
- **Root Cause:** In `src/backend/transport/websocket_fallback.py`, when a client connects with a valid JWT token, the server executes `await websocket.accept()` but does not send an initial greeting event (such as `{"type": "session_ready", "session_id": ...}`). The test executes `data = ws.receive_json()` and blocks indefinitely.
- **Real Trace Output:**
  ```text
  tests\integration\test_security.py . [Hangs indefinitely on 2nd test until cancelled]
  Step was canceled: context canceled by manage_task
  ```

### 2. Assertion Failure: `test_voice_liveness_detection` [VERIFIED]
- **File:** `tests/integration/test_security.py` (line 48)
- **Root Cause:** Schema mismatch between `LivenessResult` in `src/backend/audio/liveness.py` and the test assertion.
- **Real Error Output:**
  ```text
  ________________________ test_voice_liveness_detection ________________________
      def test_voice_liveness_detection(synthetic_speech_audio):
          detector = VoiceLivenessDetector()
          result = detector.analyze(synthetic_speech_audio)
  >       assert hasattr(result, "is_suspicious")
  E       AssertionError: assert False
  E        +  where False = hasattr(LivenessResult(is_live=False, confidence=0.85, score=0.5, details={'duration_sec': 1.0, 'energy_rms_std': 0.0, 'spectral_flatness': 0.0, 'vocal_to_high_ratio': 2208153197.01, 'is_synthetic_drone': True, 'is_abnormally_flat': False}), 'is_suspicious')

  tests\integration\test_security.py:51: AssertionError
  ```

### 3. Argument Type Failure: `test_audit_logger_hash_chain_and_tamper_detection` [VERIFIED]
- **File:** `tests/integration/test_security.py` (line 57)
- **Root Cause:** `AuditLogger.log_event()` in `src/backend/security/audit.py` accepts `(event_type: str, details: Optional[Dict] = None, session_id: Optional[str] = None)`, but the test passes `actor="user1"`.
- **Real Error Output:**
  ```text
  ______________ test_audit_logger_hash_chain_and_tamper_detection ______________
      def test_audit_logger_hash_chain_and_tamper_detection(tmp_path):
          log_file = str(tmp_path / "test_audit.log")
          logger = AuditLogger(log_path=log_file)
      
  >       e1 = logger.log_event("AUTH_SUCCESS", actor="user1", details={"ip": "127.0.0.1"})
  E       TypeError: AuditLogger.log_event() got an unexpected keyword argument 'actor'

  tests\integration\test_security.py:61: TypeError
  ```

### 4. Real Weight Execution Failures (Dependencies Missing Locally & in requirements.txt) [VERIFIED]
Attempting to run models outside mock mode (`MOCK_MODELS=false`) fails immediately with missing modules:
- **SenseVoiceSmall (`src/backend/models/asr.py`):**
  ```text
  Could not load real SenseVoice model (No module named 'funasr'). Falling back to stub/mock mode.
  ModuleNotFoundError: No module named 'funasr'
  ```
- **PyTorch (`torch`):**
  ```text
  ModuleNotFoundError: No module named 'torch'
  ```
- **Indic Parler-TTS (`src/backend/tts/indic_parler.py`):**
  ```text
  ModuleNotFoundError: No module named 'transformers'
  ```
- **Google Gemini Cloud Fallback (`src/backend/llm/gemini.py`):**
  ```text
  ModuleNotFoundError: No module named 'google.genai'
  ```
- **WebTransport over HTTP/3 (`src/backend/transport/webtransport.py`):**
  ```text
  ModuleNotFoundError: No module named 'aioquic'
  ```

### 5. IndicConformer Implementation Stubbed Out [READ]
- **File:** `src/backend/asr/indicconformer.py` (lines 37–42, 63–64)
- **Root Cause:** NeMo / HuggingFace model loading lines are commented out. Even if PyTorch were installed, `IndicConformerASR.transcribe()` returns a hardcoded string `("नमस्ते", 0.90)` without doing inference.

---

## D. Duplicate Components

| Component / Artifact | Path A | Path B | Resolution Recommendation |
|---|---|---|---|
| **Environment Configuration** | `/.env.example` (Root) | `config/development/.env.example` | Root `.env.example` uses stale variable names (`LLAMA_MODEL_PATH`, `SENSEVOICE_MODEL_DIR`). Consolidate onto the schema in `config/development/.env.example`. |
| **TTS Module Adapter** | `src/backend/models/tts.py` | `src/backend/tts/indic_parler.py` | `models/tts.py` is an alias/re-export file. Remove once callers reference `tts/` directly. |
| **ASR Engines** | `src/backend/models/asr.py` (SenseVoice) | `src/backend/asr/indicconformer.py` (IndicConformer) | Split across disparate folders. Move both under `ai/inference/` as specified in target architecture. |
| **Docker Compose Configs** | `docker/docker-compose.yml` (Dev) | `docker-compose.prod.yml` (Prod root) | Relocate both into `deployment/docker-compose.dev.yml` and `deployment/docker-compose.prod.yml`. |
| **Audio Processing Scripts** | `src/frontend/public/audio-processor.js` | `src/frontend/dist/audio-processor.js` | `dist/` contains built artifacts tracked or copied into frontend dist. Keep only source in `public/`. |

---

## E. Missing Components (vs. Target Architecture)

Comparing current workspace to `docs/architecture/target-architecture.md`:

| Target Architecture Path | Description in Target | Current State in Repository |
|---|---|---|
| `backend/app/api/auth.py`, `speech.py`, `prediction.py`, `history.py`, `health.py` | Modular FastAPI sub-routers | `[READ]` Missing. All API endpoints are crammed into a single `src/backend/main.py` (155 lines). |
| `backend/app/models/user.py`, `session.py`, `prediction.py` | Domain/ORM entities | `[READ]` Missing. Zero ORM models exist. SQLite writes raw SQL tuples in `storage.py`. |
| `backend/app/schemas/auth.py`, `speech.py`, `prediction.py` | Pydantic request/response schemas | `[READ]` Missing. Endpoints accept untyped dictionaries or raw query params. |
| `ai/training/` (`datasets/`, `train.py`, `evaluate.py`, `config/`) | Model fine-tuning and evaluation pipelines | `[READ]` Missing. Entire directory does not exist. |
| `ai/notebooks/` | Interactive prototyping notebooks | `[READ]` Missing. Directory does not exist. |
| `rag/` (`ingestion/`, `embeddings/`, `retrieval/`, `vectorstore/`) | Dedicated RAG package at repository root | `[READ]` Missing at root. Implemented internally under `src/backend/rag/`. |
| `tts/` | Dedicated TTS package at repository root | `[READ]` Missing at root. Implemented internally under `src/backend/tts/`. |
| `frontend/src/` (`app/`, `components/audio/`, `emotion/`, `transcript/`, `dashboard/`, `ui/`, `hooks/`, `lib/`, `services/`, `types/`, `stores/`) | Structured frontend architecture | `[READ]` Missing. `src/frontend/src/components/` is a single flat folder. No `stores/`, `hooks/`, or `services/` exist. |
| `backend/app/services/document_service.py` + Upload Route | Real document upload endpoint | `[READ]` Missing. Frontend `DocumentManager.tsx` manages documents only in local component state. |
| Production PostgreSQL Implementation | Target database for production | `[READ]` Missing. Application code in `storage.py` only imports `sqlite3`. No PostgreSQL driver (`psycopg2`, `asyncpg`, or `SQLAlchemy`) exists in code or dependencies. |

---

## F. Dependencies

### 1. Current `src/backend/requirements.txt` vs. Actual Code Usage

| Package | Status in `requirements.txt` | Installed Locally? [VERIFIED] | Actual Code Usage [READ] | Issue / Recommendation |
|---|---|---|---|---|
| `fastapi` | `>=0.110.0` (pinned) | Yes (`0.141.1`) | `src/backend/main.py` | OK |
| `uvicorn` | `[standard]>=0.28.0` | Yes (`0.52.4`) | ASGI server | OK |
| `pydantic` | `>=2.6.0` | Yes (`2.13.5`) | Schemas & validation | OK |
| `pydantic-settings` | `>=2.2.0` | Yes (`2.15.0`) | `src/backend/config.py` | OK |
| `httpx` | `>=0.27.0` | Yes (`0.28.1`) | `src/backend/llm/qwen.py` | OK |
| `websockets` | `>=12.0` | Yes (`17.1`) | WebSocket transport | OK |
| `numpy` | `>=1.26.0` | Yes (`2.5.3`) | Audio buffer math | OK |
| `soundfile` | `>=0.12.1` | Yes (`0.14.0`) | WAV encoding/decoding | OK |
| `python-multipart` | `>=0.0.9` | No | None found in backend | **Unused**. Remove or add file upload endpoint. |
| `cryptography` | `>=42.0.0` | Yes (`50.0.1`) | Fernet database encryption | OK |
| `pytest` | `>=8.0.0` | Yes (`9.1.1`) | Test runner | OK |
| `pytest-asyncio` | `>=0.23.0` | Yes (`1.4.0`) | Async test fixtures | OK |
| `torch` | Commented out (`# torch>=2.2.0`) | **NO** | Needed by SenseVoice, IndicConformer, Parler-TTS | **Missing Dependency** for real model execution. |
| `torchaudio` | Commented out (`# torchaudio>=2.2.0`) | **NO** | Needed by audio models | **Missing Dependency**. |
| `funasr` | Commented out (`# funasr>=1.0.0`) | **NO** | `src/backend/models/asr.py` | **Missing Dependency**. |
| `transformers` | Commented out (`# transformers>=4.40.0`) | **NO** | `src/backend/tts/indic_parler.py` | **Missing Dependency**. |
| `onnxruntime` | **NOT IN FILE** | Yes (`1.30.0`) | `src/backend/audio/vad.py` (Silero VAD) | **Unlisted Dependency**. Must be added to `requirements.txt`. |
| `faiss-cpu` | **NOT IN FILE** | Yes (`1.15.0`) | `src/backend/rag/index.py` | **Unlisted Dependency**. Must be added to `requirements.txt`. |
| `pypdf` | **NOT IN FILE** | Yes (`6.18.1`) | Document ingestion validation | **Unlisted Dependency**. |
| `python-docx` | **NOT IN FILE** | Yes (`1.2.0`) | Document ingestion validation | **Unlisted Dependency**. |
| `aioquic` | **NOT IN FILE** | **NO** | `src/backend/transport/webtransport.py` | **Unlisted Dependency**. |
| `google-genai` | **NOT IN FILE** | **NO** | `src/backend/llm/gemini.py` | **Unlisted Dependency**. |
| `parler_tts` | **NOT IN FILE** | **NO** | `src/backend/tts/indic_parler.py` | **Unlisted Dependency**. |

### 2. Frontend Dependencies (`src/frontend/package.json`) [VERIFIED]
- **Dependencies:** `react` (`^18.3.1`), `react-dom` (`^18.3.1`), `lucide-react` (`^1.16.0`).
- **DevDependencies:** `@types/react` (`^18.3.5`), `@types/react-dom` (`^18.3.0`), `@vitejs/plugin-react` (`^4.3.1`), `typescript` (`^5.5.3`), `vite` (`^5.4.2`).
- **Audit:** Clean build with `npm run build`. No conflicting packages or unpinned dependencies.

---

## G. Docker Problems

| Issue | Severity | File | Evidence & Impact |
|---|---|---|---|
| **Missing Model Packages in Backend Dockerfile** | High | `docker/Dockerfile.backend` | `Dockerfile.backend` runs `pip install -r /app/requirements.txt`. Because heavy dependencies (`torch`, `funasr`, `transformers`) are commented out and `onnxruntime` is unlisted, the container cannot run real models. |
| **Production Mode Contradiction** | High | `docker-compose.prod.yml` | Sets `MOCK_MODELS: "false"`. In production, the backend container will attempt to import `funasr` and `transformers`, crash on startup, or fall back to stub mode because those packages are not installed in the image. |
| **Postgres Service Ignored by Backend** | Medium | `docker-compose.prod.yml` | Spins up `db: postgres:16-alpine`, but backend environment specifies `DATABASE_PATH: database/prod.db` (SQLite) and mounts `./database:/app/database`. Application code never connects to Postgres. |
| **Plaintext Password in Git** | Medium | `docker-compose.prod.yml` | Line 78 defines `POSTGRES_PASSWORD: senseai_secure_prod_password` directly in version-controlled compose file. |
| **Host/Container Volume Conflict** | Low | `docker/docker-compose.yml` | Service `frontend` mounts `./src/frontend:/app` and executes `npm install`. Windows `node_modules` mounted over Linux container filesystem can cause architecture/binary mismatches. |

---

## H. Invariant Check

| Invariant | Status | Evidence Label | Direct Evidence & Finding |
|---|---|---|---|
| **1. SenseVoiceSmall can run inference standalone** | **PASS** (Code) / **FAIL** (Weights) | `[VERIFIED]` | `SenseVoiceASR` in `src/backend/models/asr.py` has no imports or dependency on Qwen3, RAG, or TTS. In mock mode, standalone execution returns stub text cleanly. In real mode, execution fails with `ModuleNotFoundError: No module named 'funasr'` because dependencies are missing. |
| **2. ASR/emotion code has no dependency on Qwen3/RAG/TTS** | **PASS** | `[VERIFIED]` | Verified imports and standalone call: `python -c "from src.backend.emotion.emotion import EmotionAnalyzer; ..."` runs cleanly with zero imports of LLM, RAG, or TTS modules. If LLM or TTS crashes, ASR and Emotion classification continue to operate unaffected. |
| **3. RAG is intent-gated, not run per utterance** | **PASS** | `[VERIFIED]` | `VoicePipeline.stream_utterance()` in `src/backend/pipeline/orchestrator.py` gates RAG strictly under `elif intent_cat == IntentCategory.KNOWLEDGE:`. Default is `chat`. Verified by running `tests/integration/test_rag_pipeline.py::test_chat_intent_never_triggers_rag` (PASSED). |
| **4. TTS failure cannot break ASR/emotion** | **PASS** | `[VERIFIED]` | In `VoicePipeline.stream_utterance()`, ASR transcription and emotion metadata are yielded to the client and saved to database before TTS synthesis is called. In addition, `IndicParlerTTS.synthesize_wav()` catches synthesis exceptions and falls back to harmonic audio. Verified by `tests/integration/test_failure_modes.py::test_tts_retry_and_fallback_audio` (PASSED). |
| **5. Model weights and secrets are not in Git** | **FAIL** (Secrets) / **PASS** (Weights) | `[VERIFIED]` | `git ls-files` confirms `models/silero_vad.onnx` and `database/dev.db` are properly git-ignored and not committed. However, `POSTGRES_PASSWORD: senseai_secure_prod_password` is committed in plaintext in `docker-compose.prod.yml`, and fallback secrets exist in `src/backend/config.py`. |

---

## I. Keep / Move / Remove Table

Following the rule of smallest reasonable change, here is the comprehensive mapping from the current layout to the target layout:

| Current Path | Action | Target Path | Rationale |
|---|---|---|---|
| `src/backend/main.py` | **MOVE & SPLIT** | `backend/app/main.py` + `backend/app/api/*` | Align with modular target FastAPI architecture. |
| `src/backend/config.py` | **MOVE** | `backend/app/core/config.py` | Configuration module in target core. |
| `src/backend/telemetry.py` | **MOVE** | `backend/app/core/logging.py` / `telemetry.py` | Telemetry and benchmarking core module. |
| `src/backend/requirements.txt` | **MOVE & UPDATE** | `backend/requirements.txt` | Backend dependency manifest. Needs unlisted dependencies added. |
| `src/backend/security/auth.py` | **MOVE** | `backend/app/core/security.py` | Core authentication & JWT verification. |
| `src/backend/security/audit.py` | **MOVE** | `backend/app/core/audit.py` | Tamper-evident audit logger. |
| `src/backend/security/rate_limiter.py` | **MOVE** | `backend/app/core/rate_limiter.py` | Session and duration limiter. |
| `src/backend/database/storage.py` | **MOVE & ENHANCE** | `backend/app/services/storage_service.py` | Data access layer; prepare for PostgreSQL adapter. |
| `src/backend/models/asr.py` | **MOVE** | `ai/inference/sensevoice.py` | Target places SenseVoice inference under `ai/inference/`. |
| `src/backend/asr/indicconformer.py` | **MOVE** | `ai/inference/indicconformer.py` | Target places IndicConformer inference under `ai/inference/`. |
| `src/backend/asr/router.py` | **MOVE** | `ai/routing/language_router.py` | Target places language routing under `ai/routing/`. |
| `src/backend/emotion/emotion.py` | **MOVE** | `ai/inference/emotion.py` | Target places SER & emotion analysis under `ai/inference/`. |
| `src/backend/audio/vad.py` | **MOVE** | `ai/preprocessing/vad.py` | Silero VAD preprocessing. |
| `src/backend/audio/liveness.py` | **MOVE** | `ai/preprocessing/liveness.py` | Audio anti-spoofing heuristic. |
| `src/backend/pipeline/orchestrator.py` | **MOVE** | `backend/app/services/speech_service.py` | Coordinates speech-to-speech orchestration. |
| `src/backend/pipeline/intent.py` | **MOVE** | `backend/app/services/intent_service.py` | Intent classification hard gate. |
| `src/backend/pipeline/chunker.py` | **MOVE** | `backend/app/services/chunker_service.py` | Real-time sentence chunking. |
| `src/backend/pipeline/concurrency.py` | **MOVE** | `backend/app/core/concurrency.py` | GPU semaphore limiter. |
| `src/backend/llm/qwen.py` | **MOVE** | `backend/app/services/llm_service.py` | Local LLM streaming client. |
| `src/backend/llm/gemini.py` | **MOVE** | `backend/app/services/gemini_service.py` | Optional cloud LLM client. |
| `src/backend/llm/router.py` | **MOVE** | `backend/app/services/llm_router.py` | Provider selection router. |
| `src/backend/llm/circuit_breaker.py` | **MOVE** | `backend/app/core/circuit_breaker.py` | LLM fault tolerance circuit breaker. |
| `src/backend/llm/prompts.py` | **MOVE** | `backend/app/core/prompts.py` | System prompt formatting. |
| `src/backend/rag/*` | **MOVE** | `rag/*` | RAG ingestion, embeddings, retriever, and index. |
| `src/backend/tts/indic_parler.py` | **MOVE** | `tts/indic_parler.py` | Indic Parler-TTS synthesis service. |
| `src/backend/models/tts.py` | **REMOVE** | — | Redundant alias shim; callers should import from `tts/`. |
| `src/backend/models/manager.py` | **MOVE** | `backend/app/core/model_manager.py` | Singleton model lifecycle manager. |
| `src/backend/transport/websocket_fallback.py` | **MOVE** | `backend/app/websocket/speech_socket.py` | Primary WebSocket voice endpoint. |
| `src/backend/transport/webtransport.py` | **MOVE** | `backend/app/transport/webtransport.py` | WebTransport abstraction. |
| `src/backend/mcp_server/*` | **KEEP** | `backend/app/mcp_server/*` | External agent integration tools. |
| `src/frontend/*` | **MOVE** | `frontend/*` | Move frontend out of `src/` to repository root. |
| `docker/docker-compose.yml` | **MOVE** | `deployment/docker-compose.dev.yml` | Consolidate compose files in target `deployment/`. |
| `docker-compose.prod.yml` | **MOVE** | `deployment/docker-compose.prod.yml` | Consolidate compose files in target `deployment/`. |
| `docker/Dockerfile.backend` | **MOVE** | `deployment/docker/Dockerfile.backend` | Consolidate Dockerfiles under deployment. |
| `docker/Dockerfile.frontend` | **MOVE** | `deployment/docker/Dockerfile.frontend` | Consolidate Dockerfiles under deployment. |
| `docker/nginx.conf` | **MOVE** | `deployment/docker/nginx.conf` | Nginx reverse proxy configuration. |
| `tests/` | **KEEP & REORGANIZE** | `tests/` (`backend/`, `ai/`, `integration/`) | Align test suite structure with target architecture. |
| `brain/*` | **KEEP** | `brain/*` | Preserve project specifications and decision records. |
| `docs/*` | **KEEP** | `docs/*` | Architecture documentation and manuals. |
| `runbooks/*` | **KEEP** | `runbooks/*` | Production disaster recovery runbooks. |
| `monitoring/*` | **KEEP** | `monitoring/*` | Health checks and metric scripts. |
| `data/*` | **KEEP** | `data/*` | Document store and vector index files. |
| `database/*` | **KEEP** | `database/*` | Schemas and dev sqlite databases. |
| `scripts/*` | **KEEP** | `scripts/*` | Operational maintenance scripts. |

---

## J. Migration Plan

Execution must follow the project rule: **work on branch `migration/voicesense`, one commit per step, state what will change/preserve, run verification tests, and STOP for review.**

```text
Step 1: Fix Regression Tests
          ↓
Step 2: Harmonize .env & Requirements
          ↓
Step 3: Move Frontend to Root
          ↓
Step 4: Extract Standalone AI, RAG & TTS Modules
          ↓
Step 5: Restructure Backend to app/ Architecture
          ↓
Step 6: Consolidate Deployment & Docker Configs
          ↓
Step 7: Verification & Final Smoke Test
```

### Step 1: Repair Existing Test Regressions
- **Files Touched:**
  - `src/backend/transport/websocket_fallback.py` (send `{"type": "session_ready", "session_id": ...}` on accept)
  - `tests/integration/test_security.py` (fix `is_suspicious` attribute check to `not result.is_live` and fix `AuditLogger.log_event` parameter call)
- **Risk:** Low. Fixes 3 known failures before touching any repository directory structure.
- **Verification:** `python -m pytest tests/` runs 100% green without hanging or failures.
- **Rollback:** `git checkout HEAD -- src/backend/transport/websocket_fallback.py tests/integration/test_security.py`.

### Step 2: Harmonize Environment Variables & Package Manifest
- **Files Touched:**
  - `.env.example` (sync variable names with `src/backend/config.py`)
  - `src/backend/requirements.txt` (add missing `onnxruntime`, `faiss-cpu`, `pypdf`, `python-docx`)
- **Risk:** Low. Non-breaking documentation and package alignment.
- **Verification:** `pip check` and `python -m pytest tests/`.
- **Rollback:** `git checkout HEAD -- .env.example src/backend/requirements.txt`.

### Step 3: Relocate Frontend (`src/frontend` → `frontend/`)
- **Files Touched:**
  - Move `src/frontend/` → `frontend/` using `git mv`.
  - Update `docker/docker-compose.yml` and `.github/workflows/ci.yml` paths.
- **Risk:** Low. Frontend is fully decoupled from backend Python imports.
- **Verification:** `cd frontend && npm run build` and `npx tsc --noEmit`.
- **Rollback:** `git mv frontend src/frontend`.

### Step 4: Extract Standalone AI, RAG, and TTS Packages
- **Files Touched:**
  - Create `ai/inference/`, `ai/routing/`, `ai/preprocessing/` via `git mv`.
  - Create `rag/` and `tts/` at repository root via `git mv`.
  - Update imports across moved modules.
- **Risk:** Medium. Requires careful path updates in `__init__.py` files.
- **Verification:** Run `python -m pytest tests/unit/test_asr.py tests/unit/test_emotion_mapping.py tests/unit/test_tts.py tests/integration/test_rag_pipeline.py`.
- **Rollback:** `git reset --hard HEAD` (to previous step commit).

### Step 5: Restructure Backend to `backend/app/`
- **Files Touched:**
  - Move `src/backend/` → `backend/app/` using `git mv`.
  - Extract sub-routers from `main.py` into `backend/app/api/` (`auth.py`, `speech.py`, `history.py`, `health.py`).
  - Update all internal imports.
- **Risk:** Medium. Requires ensuring FastAPI lifespan and WebSocket endpoint remain intact.
- **Verification:** Run full suite: `python -m pytest tests/`.
- **Rollback:** `git reset --hard HEAD` (to Step 4 commit).

### Step 6: Consolidate Deployment & Docker Files
- **Files Touched:**
  - Move `docker/` and `docker-compose.prod.yml` into `deployment/`.
  - Update paths inside `Dockerfile.backend` and compose files.
  - Remove hardcoded PostgreSQL plaintext password from `deployment/docker-compose.prod.yml`.
- **Risk:** Low. Docker configurations are isolated.
- **Verification:** `docker compose -f deployment/docker-compose.dev.yml config` and `docker compose -f deployment/docker-compose.prod.yml config`.
- **Rollback:** `git reset --hard HEAD` (to Step 5 commit).

### Step 7: Final Verification & Smoke Test
- **Files Touched:**
  - `brain/16_CHANGELOG.md` (record completed migration).
- **Risk:** None.
- **Verification:** Execute consolidated test run:
  1. `python -m pytest tests/ -v` (106 tests collected and passing).
  2. `cd frontend && npm run build` (Clean production bundle).
  3. Manual smoke test confirmation with user.
- **Rollback:** N/A.

---

## Needs My Approval (Action Items Excluded Under Permissions)

The following operational tasks could not be performed during this planning audit without explicit user approval:
1. **Model Weights Download:** Downloading real weights for `SenseVoiceSmall` (~1.2 GB), `IndicConformer-600m` (~2.4 GB), or `qwen3-1.7b.gguf` (~1.1 GB).
2. **Heavy Package Installation:** Installing PyTorch (`torch`), `funasr`, `transformers`, `parler_tts`, or `aioquic` into the local Python 3.13 environment.
3. **Database Execution / Migrations:** Running PostgreSQL schema migrations or modifying `database/dev.db`.
4. **Container Execution:** Running `docker compose up` to start active containers.
5. **Git Branch Creation & Commits:** Checking out `migration/voicesense` and committing file moves.
