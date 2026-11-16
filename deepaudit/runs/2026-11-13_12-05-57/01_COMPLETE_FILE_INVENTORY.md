# 01 — Complete File Inventory

**Scope:** all files excluding `.git/`, `.venv*/`, `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.aider-desk/`, `logs/`, `data/` payloads, `models/` weights. ~1,437 total files; ~642 text/source files inventoried; 779 files under `.agents/` are skill/agent definitions (not application code). `deepaudit/` itself excluded.

## Top-level layout

```
AGENTS.md README.md LICENSE pyproject.toml requirements-ci.txt alembic.ini
.env.example .dockerignore .gitignore .coverage skills-lock.json
docker-compose.yml            # NEW (untracked) dev compose
docker/                       # LEGACY broken Dockerfiles (src/frontend refs)
deployment/                   # NEW (untracked) prod Dockerfiles/compose/nginx
backend/app/                  # CANONICAL FastAPI backend
ai/                           # CANONICAL ML package (inference, preprocessing, routing, emotion model, training)
rag/                          # CANONICAL RAG package
frontend/                     # CANONICAL React app
src/backend/ src/frontend/    # LEGACY quarantined tree (tests/legacy only)
tests/                        # canonical tests + tests/legacy (excluded from CI)
scripts/                      # benchmark/measurement/e2e utilities
alembic/                      # 1 migration: 4acca05d22ce_001_initial_schema.py
database/                     # dev.db (SQLite, populated), migrations/, schemas/ (manual SQL dupes)
models/                       # silero_vad.onnx + voxlingua107 weights (unused)
data/                         # documents/ (3 files), index/ (built FAISS), metadata/ (crema_d csvs)
brain/                        # 17 canonical docs (PRD→decisions/changelog)
docs/                         # architecture, api, training runs, deployment runs
config/ security/ monitoring/ runbooks/ assets/ docker/ requirements/
.github/workflows/ci.yml backup.yml
```

## Canonical backend (`backend/app/`) — 30 source files

| Path | Purpose | Status |
|---|---|---|
| `main.py` | App factory, lifespan (speech+rag init), CORS, error handlers, router mounts | ACTIVE |
| `api/health.py` | GET /api/health | ACTIVE |
| `api/speech.py` | POST /api/speech/upload (+shared `process_audio_upload`) | ACTIVE |
| `api/prediction.py` | POST /api/predict | ACTIVE |
| `api/auth.py` | register/login/me + `/token` `/verify` compat endpoints | ACTIVE — `/token` is a security hole |
| `api/history.py` | sessions list/detail/delete/purge | ACTIVE |
| `websocket/speech_socket.py` | /ws/speech protocol v1, VAD segmentation, LLM+TTS streaming | ACTIVE |
| `core/config.py` | pydantic-settings, prod JWT validator | ACTIVE |
| `core/database.py` | SQLAlchemy engine/session, health check | ACTIVE |
| `core/security.py` | scrypt, HS256 JWT, FastAPI deps | ACTIVE |
| `core/rate_limiter.py` | in-memory session+IP limiters | ACTIVE (per-process) |
| `core/logging.py` | logging setup | ACTIVE |
| `models/{user,session,prediction,transcript,emotion,message,model_version}.py` | 7 ORM models | ACTIVE |
| `schemas/{auth,errors,history,prediction,speech}.py` | Pydantic DTOs | ACTIVE |
| `services/speech_service.py` | engine routing, threadpool inference, health | ACTIVE |
| `services/llm_service.py` | llama.cpp HTTP client, circuit breaker, think-filter | ACTIVE |
| `services/rag_service.py` | intent gate + retrieval orchestration | ACTIVE |
| `services/prompt_builder.py` | system prompt, history budget, RAG grounding | ACTIVE |
| `services/history_service.py` | threadpool persistence, model_versions, redaction | ACTIVE — fabricates emotion metrics |
| `services/tts_service.py` | Parler-TTS lazy loader, sentence streaming, worker fallback | ACTIVE but disabled by default |
| `services/tts_worker.py` | subprocess TTS worker for `.venv-tts` | ACTIVE (conditional) |

## Canonical AI package (`ai/`)

| Path | Purpose | Status |
|---|---|---|
| `inference/types.py` | SpeechResult schema | ACTIVE |
| `inference/engine.py` | SpeechEngine ABC | ACTIVE |
| `inference/sensevoice.py` | SenseVoiceSmall engine + tag parser + CLI | ACTIVE (heavy deps) |
| `inference/indicconformer.py` | IndicConformer engine | IMPLEMENTED — NOT RUNTIME VERIFIED |
| `inference/emotion.py` | Wav2Vec2EmotionEngine | IMPLEMENTED BUT NOT WIRED |
| `preprocessing/{audio,vad}.py` | decode/mono/resample/normalize; Silero VAD + segmenter | ACTIVE (VAD verified by tests) |
| `routing/language_router.py` | 3-tier router; LID tier dead (no detector) | PARTIAL |
| `models/emotion/{config,model}.py` | emotion head config + NumPy/PyTorch classifier | RESEARCH ONLY |
| `training/{dataset,train,evaluate,metrics}.py` + `config/*.yaml` | CREMA-D smoke training pipeline | RESEARCH ONLY |

## RAG package (`rag/`)

`chunking.py`, `embeddings.py` (e5-small, sentence-transformers), `vectorstore.py` (FAISS + NumPy fallback), `retriever.py`, `intent_router.py`, `ingestion.py` (CLI), `eval_dataset.py`, `hard_eval_dataset.py` — all ACTIVE; eval datasets used by scripts/tests.

## Frontend (`frontend/src/`)

ACTIVE: `App.tsx`, `main.tsx`, `index.css`, `lib/{env,audio-utils,formatters}.ts`, `services/{api,protocol}.ts`, `stores/conversationStore.ts`, `hooks/{useWebSocket,useAudioCapture,useAudioPlayback,useHealthStatus}.ts`, `types/*`, components: `dashboard/{DashboardLayout,LatencyCard,ServiceStatusCard}`, `audio/{MicrophoneControl,WaveformVisualizer,AudioPlayer}`, `emotion/EmotionBadge`, `transcript/{TranscriptView,ResponseView}`, `ui/{Alert,Badge,StatusDot}`, `ConversationHistory`, `LanguageSelector`, `StatusBanner`, `AuthModal`, `MultiSegmentTurns`, tests (`formatters/protocol/store`).

DEAD (no importer): `AnalyticsDashboard.tsx`, `DocumentManager.tsx`, `SettingsPage.tsx`, `LandingPage.tsx`, `Header.tsx`, `VoiceConsole.tsx`, `components/WaveformVisualizer.tsx` (1-line re-export only), `SettingsPage` Gemini-key field. Also `src/frontend/` full legacy duplicate.

## Legacy tree (`src/`)

`src/backend/` (~30 files: main, config, asr, audio, emotion, llm{qwen,gemini,router,circuit_breaker,prompts}, pipeline{orchestrator,intent,chunker,concurrency}, rag, tts, transport{websocket_fallback,webtransport}, security{auth,rate_limiter,audit}, database/storage, models/{manager,asr,llm,tts}, mcp_server, telemetry) and `src/frontend/` (older React app). Quarantined per `docs/architecture/legacy-src.md`; referenced only by `tests/legacy/` (excluded from CI) and `scripts/legacy/measure_stages.py`.

## Tests (`tests/`)

`tests/ai/` (10 files), `tests/backend/` (15 files + conftest), `tests/rag/` (4), `tests/fixtures/`, `tests/samples/*.wav`, `tests/test_doubles.py`, `tests/conftest.py`, `tests/legacy/` (23 files, excluded). Root `tests/speech_sample.wav`.

## Scripts (`scripts/`) — 30+ utilities

Active-ish: `e2e_real.py`, `run_phase9_live_turn.py`, `ws_client.py`, `evaluate_gate.py`, `evaluate_hard_gate.py`, `ci/check_import_isolation.py`, `database/{backup_manager,build_rag_index}.py`, `backups/`. Benchmark/measurement: `benchmark_phase1.py`, `benchmark_tts_standalone.py`, `measure_*.py` (10 files), `test_*.py` ad-hoc, `tts_memory_experiment.py`, `fair_benchmark_ctc_rnnt.py`. `legacy/measure_stages.py` imports `src.backend` (broken-by-design legacy). 8 `.wav` bench outputs committed.

## Config/deploy/docs

- `requirements/{runtime,ml,dev}.txt`, `backend/requirements.txt` (modified, uncommitted), `src/backend/requirements.txt` (legacy), `requirements-ci.txt`, `pyproject.toml`.
- `deployment/docker/{Dockerfile.backend,Dockerfile.frontend,entrypoint-backend.sh,nginx.conf}` + 3 compose files — NEW/untracked.
- `docker/{Dockerfile.backend,Dockerfile.frontend,docker-compose.yml,nginx.conf}` — LEGACY, broken paths.
- `.github/workflows/{ci.yml,backup.yml}` — CI fixed to `frontend/`; backup workflow present.
- `docs/` — architecture (8), api (openapi.json, rest.md, websocket.md), dataset, training runs (1 run), deployment runs (9 logs), DEMO/DEPLOYMENT/SETUP/LICENSES.
- `database/migrations/001_create_emotion_history.py` + `schemas/001_emotion_history.sql` — manual SQL duplicates of legacy `emotion_history` table (present in dev.db).
- `config/{development,production,staging,testing}/` env templates; `security/` checklist + examples; `monitoring/health-checks/`; `runbooks/` (6).

## Skipped / not inspected

- `.agents/` (779 files): agent/skill definitions, not app code.
- `models/voxlingua107/*.ckpt`, `models/silero_vad.onnx`: binary weights — metadata/size inspected only; VAD ONNX verified loadable via tests.
- `frontend/dist/`, `frontend/package-lock.json` (large generated), `.coverage`, `*.pyc`, `tests/samples/*.wav`, `scripts/*.wav`, `data/index/*` binary index (existence + metadata verified).
- `database/dev.db`: queried read-only via sqlite3 (table list + user count).
