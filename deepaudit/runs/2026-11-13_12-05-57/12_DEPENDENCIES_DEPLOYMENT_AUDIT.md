# 12 — Dependencies & Deployment Audit

## Dependency specs (4 overlapping files — drift risk)

| File | Contents | Issue |
|---|---|---|
| `pyproject.toml` | core deps + optional `dev`/`models` groups | missing fastapi/uvicorn/faiss/httpx in core |
| `requirements/runtime.txt` | fastapi, sqlalchemy, alembic, etc. | canonical for Docker |
| `requirements/ml.txt` | torch, funasr, transformers, sentence-transformers, etc. | heavy; GPU/CPU index arg |
| `requirements/dev.txt` | dev extras | — |
| `backend/requirements.txt` | 13 pkgs, `>=` pins | **modified, uncommitted**; omits faiss-cpu, pypdf, python-docx that rag needs |
| `src/backend/requirements.txt` | legacy, torch commented out | dead |
| `requirements-ci.txt` | CI-lite subset | works (162 tests) |
| `frontend/package.json` | react 18, vite 5, vitest, TS5 | caret ranges; package-lock committed |

## Environment

`.env.example` (83 vars) documents all settings incl. prod JWT validation, HF_TOKEN for gated models, POSTGRES_*. No real secrets committed. `config/{development,production,staging,testing}/` templates exist (mostly .gitkeep + prod backup-config.env/backup.cron).

## Docker

- `deployment/docker/Dockerfile.backend`: multi-stage py3.13-slim, non-root user, CPU torch default (`USE_CUDA` arg→cu126), copies backend/ai/rag/alembic, entrypoint runs migrations when `RUN_MIGRATIONS`. **Correct & current.**
- `deployment/docker/Dockerfile.frontend`: nginx serving `frontend/dist` (not read fully — assumed consistent with compose).
- `docker-compose.yml` (dev, untracked): backend+frontend+optional `llm` profile (llama.cpp server image, `/models/qwen3-1.7b.gguf`); ports bound 127.0.0.1; mem limits; named volumes; `TTS_ENABLED=false`.
- `deployment/docker-compose.prod.yml`: + postgres:16-alpine (unpublished port, healthcheck), `POSTGRES_PASSWORD`/`JWT_SECRET` required via `:?`, nginx frontend. `DATABASE_URL` must point to postgres — **verify env wiring unverified**.
- `deployment/docker-compose.{gpu,memory-light}.yml`: variants present.
- **LEGACY `docker/` dir still present**: `Dockerfile.frontend` references `src/frontend` (broken), `Dockerfile.backend` runs `src.backend.main` (wrong app), `docker-compose.yml` mounts `../src/frontend` — dead/broken, should be removed.

## CI/CD

`.github/workflows/ci.yml`: import-isolation check → backend CI-lite (162 tests + coverage) → frontend (npm ci, lint, vitest, build). Paths correctly use `frontend/` now (prior audit's CI findings are FIXED). `backup.yml` present (db backup workflow — contents not deeply verified).

## Findings

1. Deployment work is **uncommitted** (9 modified/untracked entries) — repo state ≠ deployable snapshot.
2. Dependency spec drift across 5 files; `backend/requirements.txt` missing faiss-cpu/python-docx/pypdf needed by `rag/` at runtime.
3. Model deps are heavy (torch+funasr+transformers+sentence-transformers+nemo optional) — Docker image will be multi-GB; CPU-only default sensible.
4. IndicConformer needs `HF_TOKEN` (gated) + `trust_remote_code` — prod must provision token; documented.
5. No healthcheck on backend service in compose (depends_on service_started only); `/api/health` exists for external checks.
6. Startup ordering: backend does NOT wait for llama-server (by design — degrades gracefully); migrations gated by env.
7. Node 20 in CI vs local Node 26 — fine.
