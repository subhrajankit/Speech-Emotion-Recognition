# VoiceSense AI — System Truth Table & Component Status

> **Generated**: Phase 10 Close-Out (2026-11-03)  
> **Repository Branch**: `migration/voicesense`  
> **Verification Standard**: Strict empirical labeling (`real-verified`, `test-double only`, `not measured`, `unverified`, `known issue`).

---

## 1. Component Status Truth Table

| Component | Status | Evidence File / Commit | Last Verified | Known Limitations & Empirical Facts |
| :--- | :--- | :--- | :--- | :--- |
| **VAD** | `real-verified` | `models/silero_vad.onnx`, `ai/preprocessing/vad.py`, `docs/deployment/runs/ws_english_speech_8i.txt` | 2026-10-28 | 300ms pre-roll window; on `sample_hindi_speech.wav`, acoustic speech onset ~1.18s, segment begins ~0.96s (no VAD cut). |
| **SenseVoice** | `real-verified` | `docs/deployment/runs/cli_english_speech_8i.txt`, `docs/deployment/runs/ws_english_speech_8i.txt` | 2026-10-28 | Model card confirms zh, en, yue, ja, ko support only. Hindi is **NOT** supported. Test clip `english_speech_16k.wav` is synthetic audio transcribing to *"Voice sense A provides multilingual and emotion or air voice systems across 23 in languages."* |
| **IndicConformer** | `real-verified` | `docs/architecture/language-routing.md`, `tests/ai/test_indicconformer.py`, `docs/deployment/runs/run_phase10_e2e_real.txt` | 2026-11-03 | Tested against authentic human Hindi clip (`sample_hindi_speech.wav`). Connectionist Temporal Classification (`ctc`) configured as default decoder. Transcribes *"आज मौसम बहुत अच्छा है"*. Strictly requires `language_hint="hi"`. |
| **Language Routing** | `real-verified` | `ai/routing/language_router.py`, `docs/architecture/language-routing.md` | 2026-10-28 | Automatic spoken language identification (LID) is **NOT** wired into runtime. Hindi routing strictly requires `language_hint="hi"`. Default fallback routes to SenseVoice. |
| **Emotion Engine** | `test-double only` | `ai/inference/sensevoice.py`, `tests/ai/test_sensevoice_engine.py` | 2026-10-28 | SenseVoice extracts discrete acoustic emotion tags (`<|NEUTRAL|>`, `<|HAPPY|>`, `<|SAD|>`, `<|ANGRY|>`). Custom emotion model training results **do not exist** (none in repository). |
| **LLM Service** | `real-verified` | `backend/app/services/llm_service.py`, `tests/backend/test_llm_service.py` | 2026-10-28 | Qwen3-1.7B via local `llama-server`. Uncontrolled sampling caused Hindi repetition loops and 500 peg-native parsing crashes in Phase 8h; stabilized in Phase 8i with `repeat_penalty=1.1`, `frequency_penalty=0.2`, `max_tokens=120`, and typed `LLMBadResponse` error mapping. |
| **RAG Gate** | `real-verified` | `rag/intent_router.py`, `docs/deployment/runs/hard_gate_eval_8i.txt` | 2026-10-28 | Overall accuracy: 94.0% (47/50) on hard eval set (25 chat, 25 knowledge). **Caveat**: Evaluation datasets and gate sets were authored by the agent (indicative only, not an independent human benchmark). |
| **RAG Retrieval** | `real-verified` | `data/index/chunks.json`, `docs/deployment/runs/rag_ingestion_8i.txt` | 2026-10-28 | FAISS IndexFlatIP with `multilingual-e5-small`. Ingests 3 documents (5 chunks total: `company_policy.md`, `developer_guide.md`, `warranty_terms.txt`). Knowledge base documents are sample fixtures, not production enterprise data. |
| **TTS (Indic Parler)** | `known issue` | `docs/deployment/tts-benchmark-rtx2050.md`, `docs/deployment/runs/tts_llama_stopped.txt`, `docs/deployment/runs/tts_llama_running.txt` | 2026-10-28 | `TTS_ENABLED=false` by default. Standalone RTF is 2.65–8.3 on GPU (RTX 2050 4GB) and 17–24 on CPU. End-to-end co-residence fails with `OSError: [WinError 1455]` due to Windows commit limit exhaustion. |
| **WebSocket** | `real-verified` | `backend/app/websocket/speech_socket.py`, `tests/backend/test_websocket.py`, `docs/deployment/runs/run_phase10_e2e_real.txt` | 2026-11-03 | Real-time audio streaming and JSON events (`ready`, `vad`, `speech_result`, `llm_delta`, `llm_done`, `error`). In-frame JWT authentication (`auth_token` in `start`), buffer limits, rate limits, non-blocking DB persistence dispatch. |
| **Database (SQLite)** | `real-verified` | `backend/app/core/database.py`, `backend/app/models/`, `alembic/versions/4acca05d22ce_001_initial_schema.py`, `docs/deployment/runs/run_phase9_live_turn.txt` | 2026-11-03 | 7 declarative models (`users`, `sessions`, `predictions`, `transcripts`, `emotion_results`, `model_versions`, `messages`). Alembic upgrade/downgrade cycle verified. Cascading deletion, threadpool persistence, fault isolation verified. |
| **Database (PostgreSQL)** | `unverified` | `tests/backend/test_postgres_compatibility.py`, `docs/architecture/database.md` | 2026-11-03 | Models and Alembic migrations designed for cross-dialect PostgreSQL compatibility. PostgreSQL is NOT verified (`test_postgres_compatibility.py` skipped: `DATABASE_URL_TEST` not set). Live PostgreSQL cluster verification is unperformed. |
| **Auth & Security** | `real-verified` | `backend/app/core/security.py`, `backend/app/api/auth.py`, `tests/backend/test_auth_api.py` | 2026-11-03 | Stdlib `hashlib.scrypt` password hashing, RFC 7515 HS256 JWT management (`/api/auth/register`, `/api/auth/login`, `/api/auth/me`). `APP_ENV=production` refuses startup on default, empty, or short JWT secret. |
| **Rate Limiter** | `real-verified` | `backend/app/core/rate_limiter.py`, `tests/backend/test_rate_limiter.py` | 2026-11-03 | `IPRateLimiter` on auth REST routes (10/min); `SessionRateLimiter` on WebSocket turns (20 utterances/min, 30s max duration cap, 5MB buffer cap). |
| **History & Privacy** | `real-verified` | `backend/app/services/history_service.py`, `backend/app/api/history.py`, `docs/deployment/runs/run_phase9_live_turn.txt` | 2026-11-03 | `GET /api/history/sessions`, `GET /api/history/sessions/{id}`, `DELETE /api/history/sessions/{id}`, `DELETE /api/history` (delete-my-data). `STORE_TRANSCRIPTS=false` redacts transcripts. Zero raw audio stored ever. |
| **REST API** | `real-verified` | `backend/app/api/health.py`, `backend/app/api/auth.py`, `backend/app/api/history.py` | 2026-11-03 | `/api/health` monitors subsystem readiness (including DB status component); `/api/auth` and `/api/history` handle accounts and conversational logs. |
| **Frontend** | `real-verified` | `frontend/src/App.tsx`, `frontend/src/tests/` | 2026-11-03 | React 18 + Vite + TypeScript. Multi-segment turns, Auto/English/Hindi language selector with explicit mode disclosures, model loading banners, friendly error toasts, session history drawer with delete-my-data purge. 32 vitest tests passing. |
| **Testing & CI** | `real-verified` | `requirements-ci.txt`, `.github/workflows/ci.yml`, `scripts/ci/check_import_isolation.py`, `scripts/e2e_real.py`, `docs/deployment/runs/run_phase10_e2e_real.txt` | 2026-11-03 | CI: syntax-validated, not executed. Backend lite suite verified locally in `.venv-ci` (161 passed in 37.2s, 0 ML packages). Full suite in `.venv` (171 passed, 1 skipped). Architectural isolation static gate verified. Degraded pipeline (5 variants). Real-model E2E live script verified on Hindi and English audio. |
| **Legacy Tree** | `not measured` | `docs/architecture/legacy-src.md`, `src/` | 2026-10-28 | Unmigrated prototype code in quarantine. Not imported or executed by production backend. |
| **Legacy Tree** | `not measured` | `docs/architecture/legacy-src.md`, `src/` | 2026-10-28 | Unmigrated prototype code in quarantine. Not imported or executed by production backend. |

---

## 2. Invariants & Ground Truth Summary

1. **Synthetic vs Authentic Audio**:
   - `tests/samples/english_speech_16k.wav` is a **synthetic** audio clip (generated via TTS, 8.23s). It transcribes to *"Voice sense A provides multilingual and emotion or air voice systems across 23 in languages."*
   - `tests/samples/sample_hindi_speech.wav` is the **only authentic human acoustic Hindi recording** in the repository (5.28s). Spoken prompt confirmed by speaker: *"आज मौसम बहुत अच्छा है।"* (Speaker confirmed they **DID NOT** say *"नमस्ते"*).
2. **Language Gating**:
   - No automatic spoken LID is active.
   - Hindi speech requires explicit client specification: `{"type": "start", "language_hint": "hi"}`.
3. **RAG Gating Invariant**:
   - Conversational utterances make **zero** calls to retrieval or FAISS.
   - Evaluated on agent-authored test sets (50 examples: 25 chat, 25 knowledge).
4. **TTS Memory & Co-Residence Invariant**:
   - RTX 2050 Mobile (4GB VRAM) cannot support concurrent resident GPU execution of Qwen3-1.7B and Indic Parler-TTS without paging/OOM.
   - Windows commit limit (32,176 MB) is exhausted when backend (+ SenseVoice + IndicConformer + RAG = 30,279 MB commit) attempts to spawn a 3.8GB Parler-TTS worker process. `TTS_ENABLED=false` is enforced.
5. **Persistence Invariant**:
   - Zero raw audio is persisted in the database, on disk, or in temporary directories.
   - Speech results and LLM streams are delivered first; background database writes run off the event loop via threadpools and swallow errors, guaranteeing zero voice pipeline disruption.
   - PostgreSQL is unverified on live infrastructure in this phase.
