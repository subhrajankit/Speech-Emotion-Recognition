# 13 — Dead Code, Duplication & Technical Debt

## Confirmed dead code (no importer in active tree)

| Item | Evidence |
|---|---|
| `frontend/src/components/{AnalyticsDashboard,DocumentManager,SettingsPage,LandingPage,Header,VoiceConsole}.tsx` | grep: zero imports from App/DashboardLayout/any active file |
| `frontend/src/components/WaveformVisualizer.tsx` | 1-line `export * from './audio/WaveformVisualizer'` — redundant re-export |
| `src/backend/` entire tree (~30 files) | quarantined; only `tests/legacy/` + `scripts/legacy/` import it |
| `src/frontend/` entire tree | superseded by `frontend/` |
| `docker/` (4 files) | broken paths to `src/frontend`,`src/backend`; superseded by `deployment/docker/` |
| `models/voxlingua107/*.ckpt` | weights present; no `LanguageIdentifier` implementation exists |
| `ai/inference/emotion.py` + `ai/models/emotion/` + `ai/training/` | research pipeline; zero runtime imports |
| `database/migrations/001_create_emotion_history.py`, `database/schemas/001_emotion_history.sql` | legacy `emotion_history` table managed outside Alembic |
| `scripts/legacy/measure_stages.py` | imports `src.backend` — intentionally legacy |
| `backend/app/api/prediction.py` `include_assistant` stub | returns hardcoded "not_configured" |
| `ai/routing/language_router.py` Tier-2 LID branch | `lid_detector` never provided in production |
| `rag/eval_dataset.py`, `rag/hard_eval_dataset.py` | used by eval scripts/tests only |
| `scripts/measure_*.py` (10 files), `benchmark_*.py`, `tts_memory_experiment.py`, `fair_benchmark_ctc_rnnt.py`, `test_*.py` ad-hoc | one-off research/benchmark scripts; several import `src.backend` (broken) |
| `tests/legacy/` (23 files) | excluded from CI; contains known failures (hang, attr/signature mismatches per prior audit) |
| `src/backend/mcp_server/` | MCP server, not in MVP path |

## Duplication

- Two full stacks: `backend/ai/rag/frontend` vs `src/backend/src/frontend`.
- Two auth implementations: canonical `core/security.py` vs legacy `src/backend/security/auth.py`.
- Two rate limiters, two VADs, two language routers, two intent routers, two RAG retrievers, two LLM clients (qwen+gemini legacy vs httpx canonical), two TTS impls, two WS endpoints (`/ws/speech` vs `/ws/voice`), two storage layers (SQLAlchemy vs raw sqlite3 `storage.py`).
- `database/migrations` + `database/schemas` manual SQL vs Alembic canonical.
- Requirements: 5 files.

## Technical debt

- `history_service` fabricates emotion confidence/valence/arousal (data-integrity debt).
- `IndicConformerSpeechEngine` speculative call signatures with fallback chain — fragile.
- `extract_features` pseudo-random features in emotion engine — research-invalid.
- Sync SQLAlchemy in async endpoints.
- Per-process rate limiting.
- Committed `frontend/dist/`, `.coverage`, `tests/samples/*.wav`, `scripts/*.wav` bench outputs.
- `docs/api/openapi.json` may be stale vs current routes.
- `docs/architecture/current-state.md` (Oct 22) is itself stale — predates Phases 9-12.
