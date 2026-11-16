# 17 — Verification Evidence

All commands run read-only in `D:\Capstone Project\NewSenseVoice`, 2026-11-13.

## Executed

| Command | Result |
|---|---|
| `git log --oneline -10`, `git status --short`, `git branch --show-current` | branch `migration/voicesense`, HEAD `1cc04a4`, 9 modified/untracked entries (Phase 12 uncommitted) |
| `find` file inventory (excl. venvs/node_modules/.git) | 1,437 files; 642 source/doc files; 779 under `.agents/` |
| `python -c "sqlite3 … database/dev.db"` | 10 tables incl. legacy `emotion_history`; `users`=86 rows |
| `.venv-ci/Scripts/python.exe -m pytest tests/backend tests/rag tests/ai -q -m "not model and not slow and not gpu and not postgres" --no-cov -x` | **162 passed, 11 deselected, 20.52s** |
| `grep` sweeps: `create_all|alembic`, `voxlingua|lid_detector`, `ai.models.emotion|ai.training`, `ai.inference.emotion`, `from src.|src.backend`, `mock|TODO|FIXME` (frontend), component imports | Results cited per-report |
| File reads: all of `backend/app/**` (30 files), `ai/**` core, `rag/**` core, `frontend/src` key files, `alembic` migration, `docker-compose.yml`, `ci.yml`, `deployment/docker/Dockerfile.backend`, `.env.example` (names only) | Evidence base for all findings |

## Prior-run evidence relied upon (not re-executed)

- `docs/deployment/runs/*` logs (phase 8i/9/10 live turns, WS runs, TTS benchmarks) — treated as historical claims, spot-consistent with code.
- `docs/training/runs/run_20261025_193120/` metrics — smoke run artifacts.
- `docs/architecture/current-state.md` (Oct 22) — stale; used only as prior baseline.
- `brain/16_CHANGELOG.md`, `17_DECISIONS.md` — phase completion records.

## Tool availability

Python 3.13 (.venv-ci works for tests); Node present; **no GPU model inference executed** (torch/funasr/transformers/nemo/sentence-transformers not installed in audit env); llama-server not running; Postgres not running; Docker not invoked.

## Not executed (and why)

- Full pytest incl. `model`/`gpu`/`postgres` markers — heavy deps absent.
- `tests/legacy/` — known-broken quarantined suite.
- `npm test`/`npm run build` — not re-run (time); changelog+dist artifact evidence accepted.
- Docker builds, alembic against Postgres, live WS session — services/models unavailable in audit env.
