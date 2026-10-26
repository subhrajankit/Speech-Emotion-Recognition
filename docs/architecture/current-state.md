# VoiceSense AI — Current Architecture State & Audit Map

**Audit Date:** 2026-10-22  
**Audit Scope:** Pre-migration truthful baseline audit of repository `NewSenseVoice` against `docs/architecture/target-architecture.md`.  
**Operating Environment:** Windows 11 (PowerShell), Python 3.13.14, Node.js v26.8.2, npm 11.19.1.  
**Git Context:** Active Branch `migration/voicesense` (5 commits ahead of `main` at `ebd8407`).  
**Evidence Standard:** Every finding is tagged with `[VERIFIED]` (executed and measured in this session), `[READ]` (verified by direct code analysis), or `[UNKNOWN]` (cannot be confirmed without further execution/access).

---

## A. Current Architecture (As Implemented, Not As Intended)

The repository currently exists in a **hybrid/transitional state**. Two coexisting backends and test suites are present simultaneously in the filesystem:
1. **The Legacy Monolith (`src/backend/`)**: Retained from commit `ebd8407`. Houses a single-pipeline architecture exposed on WebSocket `/ws/voice`, coordinated by `model_manager` in `src/backend/models/manager.py` and direct SQLite storage in `src/backend/database/storage.py`.
2. **The Target Modular System (`backend/app/`, `ai/`, `frontend/`, `rag/`)**: Incrementally introduced across migration commits `cf82ba9` through `4473f49`, plus uncommitted changes for RAG (`rag/`, `backend/app/services/rag_service.py`) and TTS (`backend/app/services/tts_service.py`). Exposes WebSocket `/ws/speech`.

```text
                                [ React 18 + Vite Frontend ]
                                   (frontend/src/App.tsx)
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
             [ Target Ingress ]                              [ Legacy Ingress ]
        (backend/app/main.py:8000)                        (src/backend/main.py:8000)
            [ /ws/speech ]                                   [ /ws/voice ]
                  │                                               │
                  ▼                                               ▼
     [ Silero VAD (ONNX CPU) ]                        [ Silero VAD (ONNX CPU) ]
     (ai/preprocessing/vad.py)                        (src/backend/audio/vad.py)
                  │                                               │
                  ▼                                               ▼
     [ Language Router (3-Tier) ]                     [ Language Router (Regex) ]
    (ai/routing/language_router.py)                   (src/backend/asr/router.py)
                  │                                               │
       ┌──────────┴──────────┐                         ┌──────────┴──────────┐
       ▼                     ▼                         ▼                     ▼
[SenseVoiceSmall]    [IndicConformer-600m]       [SenseVoiceSmall]    [IndicConformer-600m]
(ai/inference/       (ai/inference/              (src/backend/models/ (src/backend/asr/
 sensevoice.py)       indicconformer.py)          asr.py)              indicconformer.py)
(Global + SER tags)  (Indic + emotion=None)      (Global + SER tags)  (Hindi/Indic)
       │                     │                         │                     │
       └──────────┬──────────┘                         └──────────┬──────────┘
                  ▼                                               ▼
        [ Unified SpeechResult ]                     [ Emotion Analyzer (Circumplex) ]
        (ai/inference/types.py)                      (src/backend/emotion/emotion.py)
                  │                                               │
                  ▼                                               ▼
     [ Intent Router (Hard Gate) ]                   [ Intent Router (Regex Hard Gate) ]
        (rag/intent_router.py)                       (src/backend/pipeline/intent.py)
                  │                                               │
       ┌──────────┼──────────┐                         ┌──────────┼──────────┐
       ▼          ▼          ▼                         ▼          ▼          ▼
   [Command] [Knowledge]  [Chat]                   [Command] [Knowledge]  [Chat]
    (noop)   (e5 + FAISS) (default)                 (regex)  (e5 + FAISS) (default)
                  │          │                                    │          │
                  └────┬─────┘                                    └────┬─────┘
                       ▼                                               ▼
            [ Qwen3-1.7B Streaming ]                        [ Qwen3-1.7B / Gemini ]
         (Local llama-server via HTTP)                (src/backend/llm/qwen.py, gemini.py)
        (backend/app/services/llm_service.py)                          │
                       │                                               ▼
                       ▼                                  [ SentenceBoundaryChunker ]
          [ Indic Parler-TTS Service ]                 (src/backend/pipeline/chunker.py)
         (ai4bharat/indic-parler-tts)                                  │
      (backend/app/services/tts_service.py)                            ▼
                       │                                    [ Indic Parler-TTS ]
                       ▼                               (src/backend/tts/indic_parler.py)
        [ WebSocket Audio/Text Stream ]                                │
                                                                       ▼
                                                        [ WebSocket Audio/Text Stream ]
```

### Key Reality Points of Current Implementation [READ]:
1. **Repository Layout**: Transitional. `frontend/`, `backend/`, `ai/`, `rag/`, `models/`, `data/`, `database/`, and `tests/` exist at root. However, `src/backend/` still remains fully populated. Top-level `tts/` and `deployment/` (specified in target architecture) do not exist.
2. **Model Lifecycle**: Models are initialized once at startup. In `backend/app/main.py`, `speech_service.initialize()` and `rag_service.initialize()` are called inside the FastAPI `lifespan` hook. In `src/backend/main.py`, `model_manager.initialize()` is called.
3. **Transport Layer**: Real-time streaming occurs over WebSockets. Frontend connects to `ws://127.0.0.1:8000/ws/speech` (`frontend/src/lib/env.ts`). Legacy backend exposes `ws://127.0.0.1:8000/ws/voice`. A WebTransport descriptor endpoint exists in `src/backend/main.py`, but native HTTP/3 QUIC socket serving is not running.
4. **Database**: Persistent storage remains direct SQLite (`database/dev.db`, `storage.py`). Target ORM models (`backend/app/models/user.py`, `session.py`, `prediction.py`) are not implemented.
5. **Working Directory Cleanliness**: Branch `migration/voicesense` has 9 modified tracked files and 12 untracked files/directories in progress (RAG service and TTS service).

---

## B. Working Components

The following components were empirically executed, tested, and verified in this session:

| Component | File Path | Status | Evidence / Real Test Output |
|---|---|---|---|
| **Silero VAD (ONNX)** | `ai/preprocessing/vad.py` | `[VERIFIED]` | 7 unit tests passed in `tests/ai/test_vad.py`. Evaluates 512-sample (32ms) frames via ONNX Runtime CPU. Correctly flags synthetic speech vs silence. |
| **Audio Preprocessing** | `ai/preprocessing/audio.py` | `[VERIFIED]` | 10 unit tests passed in `tests/ai/test_audio_preprocessing.py`. Mono conversion, 16kHz resampling, int16/float32 normalization pass. |
| **Language Router (3-Tier)** | `ai/routing/language_router.py` | `[VERIFIED]` | 9 unit tests passed in `tests/ai/test_language_router.py`. Tier 1 (explicit hint), Tier 2 (LID threshold > 0.6), Tier 3 (default SenseVoice) verified. |
| **IndicConformer Engine** | `ai/inference/indicconformer.py` | `[VERIFIED]` | 5 tests passed in `tests/ai/test_indicconformer.py`. Enforces `emotion = None` for all Indic audio; raises actionable `RuntimeError` when NeMo/weights are missing. |
| **SenseVoice Engine & CLI** | `ai/inference/sensevoice.py` | `[VERIFIED]` | 6 tag parsing tests passed in `tests/ai/test_tag_parsing.py`. Standalone CLI executed: `python -m ai.inference.sensevoice --mock --test-silence` returned valid `SpeechResult` JSON (exit 0). `python -m ai.inference.sensevoice --test-silence` ran VAD-gated silent pass (exit 0). |
| **LLM Service & Circuit Breaker** | `backend/app/services/llm_service.py` | `[VERIFIED]` | 11 tests passed in `tests/backend/test_llm_service.py`. Strips `<think>` tags, trips cooldown after 3 consecutive 5xx/connection failures, handles streaming tokens. |
| **Prompt Builder & Security Sanitizer** | `backend/app/services/prompt_builder.py` | `[VERIFIED]` | Verified token budget sliding window (1024 tokens) and emotion/language conditioning in `test_llm_service.py`. Inbound prompt injection sanitizer passed in `test_prompt_injection.py`. |
| **RAG Core (Embeddings, FAISS, Chunker)** | `rag/` (`chunking.py`, `embeddings.py`, `vectorstore.py`, `retriever.py`, `intent_router.py`) | `[VERIFIED]` | 13 tests passed in `tests/rag/`. Verifies document chunking, SHA256 checksumming, normalized L2 vectors, FAISS cosine similarity, and grounded citations. |
| **RAG Intent Gate** | `backend/app/services/rag_service.py`, `rag/intent_router.py` | `[VERIFIED]` | Passed with call spy in `tests/backend/test_rag_service.py`: conversational chat queries result in exactly 0 retrieval calls. |
| **Modular Backend API & WebSockets** | `backend/app/` (`main.py`, `api/upload.py`, `api/predict.py`, `websocket/speech_socket.py`) | `[VERIFIED]` | 36 tests passed in `tests/backend/`. Handles audio upload, speech perception, client ping/pong, and error framing. |
| **Frontend React 18 + Vite** | `frontend/` (`src/App.tsx`, `src/hooks/useWebSocket.ts`, `src/services/protocol.ts`) | `[VERIFIED]` | 17 Vitest unit tests passed (`npm test` in `frontend/`). Production build `npm run build` compiled 1,901 modules to `dist/` in 13.93s with 0 errors. |
| **Legacy Unit Test Suite** | `tests/unit/` | `[VERIFIED]` | 80 tests passed in `tests/unit/` covering legacy VAD, emotion mapping, sentence chunker, and security JWT handling. |

---

## C. Broken Components (With Real Error Output)

The following components were empirically executed and failed or caused blocking errors:

### 1. `tests/integration/test_security.py::test_authenticated_websocket_handshake_accepted` [VERIFIED]
- **Symptom**: Hangs indefinitely during test run until canceled via `manage_task kill`.
- **Root Cause**: The test executes:
  ```python
  with client.websocket_connect(f"/ws/voice?token={token}") as ws:
      data = ws.receive_json()
      assert data.get("type") == "session_ready"
  ```
  However, in `src/backend/transport/websocket_fallback.py`, line 53 executes `await websocket.accept()`, but does **not** send any greeting or `session_ready` JSON frame. The client blocks indefinitely waiting for data.

### 2. `tests/integration/test_security.py::test_voice_liveness_detection` [VERIFIED]
- **Command**: `python -m pytest tests/integration/test_security.py -k "test_voice_liveness_detection"`
- **Real Error Output**:
  ```text
  FAILED tests/integration/test_security.py::test_voice_liveness_detection - AssertionError: assert False
  >       assert hasattr(result, "is_suspicious")
  E       AssertionError: assert False
  E        +  where False = hasattr(LivenessResult(is_live=False, confidence=0.85, score=0.5, details={'duration_sec': 1.0, 'energy_rms_std': 0.0, 'spectral_flatness': 0.0, 'vocal_to_high_ratio': 2208153197.01, 'is_synthetic_drone': True, 'is_abnormally_flat': False}), 'is_suspicious')
  ```
- **Root Cause**: Attribute mismatch. `LivenessResult` defines `is_live`, `confidence`, `score`, `details`, but the test checks for nonexistent `is_suspicious`.

### 3. `tests/integration/test_security.py::test_audit_logger_hash_chain_and_tamper_detection` [VERIFIED]
- **Command**: `python -m pytest tests/integration/test_security.py -k "test_audit_logger_hash_chain_and_tamper_detection"`
- **Real Error Output**:
  ```text
  FAILED tests/integration/test_security.py::test_audit_logger_hash_chain_and_tamper_detection - TypeError: AuditLogger.log_event() got an unexpected keyword argument 'actor'
  >       e1 = logger.log_event("AUTH_SUCCESS", actor="user1", details={"ip": "127.0.0.1"})
  E       TypeError: AuditLogger.log_event() got an unexpected keyword argument 'actor'
  ```
- **Root Cause**: Signature mismatch between `src/backend/security/audit.py` and the integration test.

### 4. Docker Frontend Container Build (`docker/Dockerfile.frontend`) [VERIFIED / READ]
- **Symptom**: Build will fail immediately.
- **Root Cause**: Line 12 specifies:
  ```dockerfile
  COPY src/frontend/package*.json ./
  COPY src/frontend/ ./
  ```
  `src/frontend/` was moved to `frontend/` in Phase 3. The path no longer exists.

### 5. Docker Backend Container Build (`docker/Dockerfile.backend`) [READ]
- **Symptom**: Containers build an outdated legacy application.
- **Root Cause**: Line 25 copies `src/backend/requirements.txt`, line 34 copies `src`, and line 56 launches `CMD ["uvicorn", "src.backend.main:app", ...]`. The container completely ignores `backend/app`, `ai/`, and `rag/`.

### 6. GitHub Actions CI (`.github/workflows/ci.yml`) [READ]
- **Symptom**: CI fails on any push or PR.
- **Root Cause**:
  - Line 37: `cache-dependency-path: src/frontend/package-lock.json` (does not exist).
  - Line 40: `working-directory: src/frontend` (does not exist).
  - Line 30: `flake8 src/backend tests scripts` (checks legacy code, ignores `backend/` and `ai/`).

---

## D. Duplicate Components

Because the migration is in-progress, multiple subsystems are duplicated across `src/backend/` and the target directories:

| Subsystem | Legacy Location (`src/backend/`) | Target Location | Migration Status |
|---|---|---|---|
| **Backend Entry & Lifespan** | `src/backend/main.py` | `backend/app/main.py` | Target operational on `/ws/speech`; legacy remains on `/ws/voice`. |
| **Config & Settings** | `src/backend/config.py` | `backend/app/core/config.py` | Target uses `pydantic-settings` with typed limits. |
| **VAD Segmentation** | `src/backend/audio/vad.py` | `ai/preprocessing/vad.py` | Target refactored into `SileroVAD` and `VADSpeechSegmenter`. |
| **Language Routing** | `src/backend/asr/router.py` | `ai/routing/language_router.py` | Target features 3-tier precedence with `LanguageIdentifier` protocol. |
| **ASR Models** | `src/backend/models/asr.py`, `src/backend/asr/indicconformer.py` | `ai/inference/sensevoice.py`, `ai/inference/indicconformer.py` | Target uses unified `SpeechEngine` and `SpeechResult`. |
| **Intent Classification** | `src/backend/pipeline/intent.py` | `rag/intent_router.py` | Target supports exact keyword, regex, and intent schema. |
| **RAG Retrieval** | `src/backend/rag/retriever.py` | `rag/retriever.py`, `backend/app/services/rag_service.py` | Target features FAISS cosine index, chunker, and citation formatter. |
| **LLM Streaming** | `src/backend/llm/qwen.py`, `gemini.py` | `backend/app/services/llm_service.py` | Target uses decoupled HTTP `httpx` client with circuit breaker. |
| **TTS Synthesis** | `src/backend/tts/indic_parler.py` | `backend/app/services/tts_service.py` | Target adds 23-language registry and sentence streaming. |
| **WebSocket Handler** | `src/backend/transport/websocket_fallback.py` | `backend/app/websocket/speech_socket.py` | Target uses Protocol v1 message framing. |
| **Dependencies** | `src/backend/requirements.txt` | `backend/requirements.txt`, `pyproject.toml` | Three distinct package specification files exist. |

---

## E. Missing Components (vs. Target Architecture)

Comparing the current repository layout against `docs/architecture/target-architecture.md`:

| Target Path | Status | Missing Contents / Functionality |
|---|---|---|
| `tts/` (root) | `[READ]` Missing | Target architecture specifies a top-level `tts/` directory. Currently TTS lives in `src/backend/tts/` and `backend/app/services/tts_service.py`. |
| `ai/models/` | `[READ]` Incomplete | Subdirectories `ai/models/sensevoice/`, `ai/models/indicconformer/`, `ai/models/emotion/` do not exist. |
| `ai/training/` | `[READ]` Missing | `datasets/`, `preprocessing/`, `train.py`, `evaluate.py`, `config/` are not present. |
| `ai/notebooks/` | `[READ]` Missing | Directory does not exist. |
| `backend/app/models/` | `[READ]` Missing | `user.py`, `session.py`, `prediction.py` (relational ORM schemas) are not implemented. |
| `backend/app/schemas/` | `[READ]` Incomplete | Only `errors.py` and `health.py` exist. Target schemas `speech.py`, `auth.py`, `prediction.py` are not yet in `backend/app/schemas/`. |
| `backend/app/api/history.py` | `[READ]` Missing | Conversation history REST endpoint is not implemented in `backend/app/api/`. |
| `deployment/` | `[READ]` Missing | Docker files live in `docker/` and `docker-compose.prod.yml` at root, not under `deployment/`. |
| `docs/dataset/`, `docs/training/`, `docs/deployment/` | `[READ]` Incomplete | Subdirectories under `docs/` are missing. |

---

## F. Dependencies

### 1. Active Environment Status [VERIFIED]
- **Python Version**: 3.13.14 (Windows x64).
- **Installed Key Packages**:
  - `fastapi==0.141.1`, `uvicorn==0.52.4`, `starlette==1.6.0`
  - `onnxruntime==1.30.0` (Silero VAD execution functional)
  - `numpy==2.5.3`, `soundfile==0.14.0` (Audio I/O functional)
  - `faiss-cpu==1.15.0` (Vector similarity search functional)
  - `httpx==0.28.1` (LLM communication functional)
  - `pydantic==2.13.5`, `pydantic-settings==2.15.0`
  - `pytest==9.1.1`, `pytest-asyncio==1.4.0`
  - `websockets==17.1`, `cryptography==50.0.1`
  - `pypdf==6.18.1`, `python-docx==1.2.0`
- **Missing Heavy Packages**: `torch`, `torchaudio`, `funasr`, `transformers`. Heavy model weights are not loaded; tests rely on mock modes and ONNX runtime.

### 2. Dependency Specification Inconsistencies [READ]
- `backend/requirements.txt`: 13 packages. Does not pin exact patch versions (uses `>=`). Omits `pypdf`, `python-docx`, and `faiss-cpu` (which RAG depends on).
- `src/backend/requirements.txt`: 12 packages. Comments out PyTorch, funasr, and transformers.
- `pyproject.toml`: Specifies core dependencies (`numpy`, `soundfile`, `onnxruntime`, `pydantic`) and optional groups `[project.optional-dependencies]` (`dev`, `models`). Does not include `fastapi`, `uvicorn`, `faiss-cpu`, or `httpx` in core `dependencies`.
- `frontend/package.json`: Dependencies pinned with caret (`^`): `react@^18.3.1`, `lucide-react@^1.16.0`. DevDependencies include `typescript@^5.5.3`, `vite@^5.4.2`, `vitest@^1.6.1`.

---

## G. Docker Problems

| Issue | File Location | Impact | Status |
|---|---|---|---|
| **Broken Frontend Context** | `docker/Dockerfile.frontend:12` | References `src/frontend/package*.json` and `src/frontend/`. Docker build fails immediately. | `[VERIFIED / READ]` |
| **Legacy Backend Image** | `docker/Dockerfile.backend:25,34,56` | Copies `src/backend` and runs `uvicorn src.backend.main:app`. Does not build target backend. | `[READ]` |
| **Missing Deployment Directory** | Repository Root | Target architecture expects `deployment/docker/` and `deployment/docker-compose.*.yml`. Files currently reside in `docker/` and root. | `[READ]` |
| **Database Engine Disconnect** | `docker-compose.prod.yml:37,72` | Compose provisions a PostgreSQL container (`db:5432`), but backend service passes `DATABASE_PATH=database/prod.db` (SQLite). Backend code does not use PostgreSQL. | `[READ]` |
| **Model Path Hardcoding** | `docker-compose.prod.yml:17` | Hardcoded command specifies `-m /models/qwen3-1.7b.gguf`, conflicting with docs specifying Qwen3-4B. | `[READ]` |

---

## H. Invariant Checks

| Invariant | Result | Evidence / Test Command |
|---|---|---|
| **1. SenseVoiceSmall can run inference standalone** | **PASS** `[VERIFIED]` | Executed `python -m ai.inference.sensevoice --mock --test-silence` (exited code 0, returned valid SpeechResult JSON). Executed `python -m ai.inference.sensevoice --test-silence` without mock flag (exited code 0, VAD-gated silent pass). When weights/torch are missing on non-silent audio, it raises actionable `RuntimeError` (`tests/ai/test_sensevoice_engine.py` passed). |
| **2. ASR/emotion code has no dependency on Qwen3/RAG/TTS** | **PASS** `[VERIFIED]` | `tests/backend/test_isolation.py` AST scan passed: 0 files in `ai/` and 0 lines in `speech_service.py` import `llm_service`. Ripgrep confirms zero occurrences of `rag` or `tts` in `ai/` and `backend/app/services/speech_service.py`. |
| **3. RAG is intent-gated, not run per utterance** | **PASS** `[VERIFIED]` | `tests/backend/test_rag_service.py::test_chat_utterance_makes_zero_retrieval_calls` passed with call spy proving `retrieval_counter == 0` for conversational queries. `tests/integration/test_rag_pipeline.py::test_chat_intent_never_triggers_rag` passed. |
| **4. TTS failure cannot break ASR/emotion** | **PASS** `[VERIFIED]` | In `backend/app/websocket/speech_socket.py`, `speech_result` is computed and dispatched to the client over WebSocket *before* LLM or TTS execution begins. In `tests/integration/test_failure_modes.py::test_tts_retry_and_fallback_audio`, simulated TTS failure falls back to harmonic synthesis without raising an unhandled error or corrupting transcript metadata. |
| **5. Model weights and secrets are not in Git** | **PASS** `[VERIFIED]` | `git ls-files` check for binary weights (`*.bin`, `*.safetensors`, `*.gguf`, `*.onnx`, `*.pt`, `*.pth`) returned 0 tracked files. Check for private keys (`*.key`, `*.pem`, `*.p12`) returned 0 files. Tracked `.env` files are exclusively `.env.example` templates and `backup-config.env` (non-secret). `.gitignore` covers model weights and `.env` files. |

---

## I. Keep / Move / Remove Table

| Path | Action | Reason | Label |
|---|---|---|---|
| `backend/app/` | **KEEP** | Target FastAPI modular architecture (Phases 2, 4, 6). | `[READ]` |
| `ai/` | **KEEP** | Target speech perception, VAD, language router, and inference engines. | `[READ]` |
| `frontend/` | **KEEP** | Target React 18 + Vite frontend migrated in Phase 3. | `[READ]` |
| `rag/` | **KEEP** | Vector retrieval, chunking, and embedding modules (Phase 7). | `[READ]` |
| `src/backend/` | **REMOVE** | Legacy monolith; redundant with `backend/app/` and `ai/`. Delete after remaining utility is verified. | `[READ]` |
| `docker/` | **MOVE** | Move to `deployment/docker/` to conform to target architecture. | `[READ]` |
| `docker-compose.prod.yml` | **MOVE** | Move to `deployment/docker-compose.prod.yml`. | `[READ]` |
| `tests/backend/`, `tests/ai/`, `tests/rag/` | **KEEP** | Active test suites for target architecture (all passing). | `[READ]` |
| `tests/unit/`, `tests/integration/`, `tests/api/` | **MOVE / REMOVE** | Tightly coupled to `src/backend/`. Port valuable integration assertions to `tests/integration/` (targeting `backend/app`), then delete remainder. | `[READ]` |
| `scripts/` | **KEEP / MOVE** | Keep active scripts; align structure with `scripts/setup.sh`, `download_models.py`, `health_check.py`. | `[READ]` |
| `brain/` | **KEEP** | Architecture notes, PRD, TRD, ADRs, and security specifications. | `[READ]` |
| `docs/architecture/` | **KEEP** | Target architecture and current state documentation. | `[READ]` |
| `pyproject.toml` | **KEEP** | Update with complete dependencies from `backend/requirements.txt`. | `[READ]` |

---

## J. Migration Plan

Ordered sequential steps to complete migration to target architecture:

### Step 1: Clean and Consolidate Active Working State
- **Files Touched**: `backend/app/`, `rag/`, `tests/`
- **Risk**: Low (stabilizing existing uncommitted work).
- **Verification**: Run `python -m pytest tests/backend/ tests/ai/ tests/rag/ -v`.
- **Rollback**: `git checkout -- .`

### Step 2: Fix CI Workflows and Dockerfile Paths
- **Files Touched**: `.github/workflows/ci.yml`, `docker/Dockerfile.frontend`, `docker/Dockerfile.backend`
- **Risk**: Low.
- **Verification**: Run `npm run build` from `frontend/`; test `docker compose config`.
- **Rollback**: Revert specific workflow commits via `git revert`.

### Step 3: Implement Target Schemas and Database Models
- **Files Touched**: `backend/app/schemas/` (`speech.py`, `prediction.py`, `auth.py`), `backend/app/models/` (`user.py`, `session.py`, `prediction.py`)
- **Risk**: Medium (database abstraction).
- **Verification**: Unit tests for schema validation and database session operations.
- **Rollback**: Delete newly added files; restore previous imports.

### Step 4: Finalize Phase 7 (RAG) and Phase 8 (TTS)
- **Files Touched**: `backend/app/services/rag_service.py`, `backend/app/services/tts_service.py`, `backend/app/websocket/speech_socket.py`
- **Risk**: Medium (pipeline integration).
- **Verification**: Run `tests/backend/test_rag_service.py` and end-to-end WebSocket tests.
- **Rollback**: Revert to Phase 6 commit `4473f49`.

### Step 5: Relocate Docker to `deployment/` & Establish Top-Level `tts/`
- **Files Touched**: `docker/` → `deployment/docker/`, `docker-compose.prod.yml` → `deployment/docker-compose.prod.yml`, `tts/`
- **Risk**: Low (file moves using `git mv`).
- **Verification**: Validate `docker compose -f deployment/docker-compose.prod.yml config`.
- **Rollback**: `git mv` back to original paths.

### Step 6: Deprecate and Retire Legacy `src/backend/`
- **Files Touched**: `src/backend/`, `tests/unit/`, `tests/api/`
- **Risk**: High (removing legacy code).
- **Verification**: Entire consolidated test suite (`pytest tests/`) passes with 0 references to `src.backend`.
- **Rollback**: `git revert` removal commit.

---

## K. Conflicts with Target (Existing Docs vs. target-architecture.md)

The following conflicts exist between current repository artifacts/docs and `docs/architecture/target-architecture.md` (recorded without resolving):

1. **Repository Root Directory Structure**:
   - `docs/SETUP.md`, `docs/DEPLOYMENT.md`, `brain/03_ARCHITECTURE.md`, `brain/10_SECURITY.md`, `brain/13_DEPLOYMENT.md`, `docker/Dockerfile.backend`, and `.github/workflows/ci.yml` mandate paths under `src/backend/` and `src/frontend/`.
   - `target-architecture.md` mandates top-level directories: `backend/app/`, `frontend/`, `ai/`, `rag/`, `tts/`, `data/`, `models/`, `scripts/`, `docs/`, `deployment/`.
2. **WebSocket Ingress Endpoint**:
   - `brain/07_API_CONTRACT.md`, `brain/13_DEPLOYMENT.md`, `docs/SETUP.md`, and `docs/DEPLOYMENT.md` specify `ws://127.0.0.1:8000/ws/voice`.
   - `target-architecture.md` and `backend/app/websocket/speech_socket.py` specify `ws://127.0.0.1:8000/ws/speech`.
3. **Transport Protocol Scope**:
   - `brain/13_DEPLOYMENT.md` describes a dual WebTransport (HTTP/3 QUIC) + WebSocket transport as active.
   - `AGENTS.md` and `target-architecture.md` explicitly mandate: "WebTransport is a later upgrade — do not build it before Phase 9" and diagram WebSocket only.
4. **LLM Parameter Size**:
   - `README.md` and `brain/03_ARCHITECTURE.md` state `Qwen3-4B via llama.cpp`.
   - `docs/SETUP.md`, `docs/DEPLOYMENT.md`, `brain/02_TRD.md`, and code defaults (`config.py`) specify `Qwen3-1.7B` / `qwen2.5-1.5b-instruct-q4_k_m.gguf`.
5. **Language Router Sequence**:
   - `brain/03_ARCHITECTURE.md` describes SenseVoiceSmall running first to perform Language ID (LID) and routing to IndicConformer only on Indic detection or low confidence.
   - `target-architecture.md` places the Language Router *before* both SenseVoiceSmall and IndicConformer.
6. **Database Architecture & ORM**:
   - `target-architecture.md` specifies ORM models (`backend/app/models/user.py`, `session.py`, `prediction.py`).
   - `brain/04_DATA_MODEL.md` and `src/backend/database/storage.py` specify a lightweight schema consisting exclusively of `transcripts` and `emotion_history` tables in SQLite, with no user authentication or prediction tables.
7. **Top-Level `tts/` Directory**:
   - `target-architecture.md` lists a top-level `tts/` directory.
   - Code places TTS inside `backend/app/services/tts_service.py` and `src/backend/tts/indic_parler.py`, with no root `tts/` package.
