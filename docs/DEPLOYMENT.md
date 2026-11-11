# VoiceSense AI — Deployment & Operations Guide

> For container architecture, compose files, and Docker environment tables, see [`docs/deployment/docker.md`](./deployment/docker.md). For local setup and Python environments, see [`docs/SETUP.md`](./SETUP.md).

---

## 1. Local Single-Host Deployment (Verified on Windows)

VoiceSense AI runs cleanly with all local services bound to `127.0.0.1` only:

1. **Backend Server (`backend.app.main:app`):**
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --ws-ping-interval 20 --ws-ping-timeout 20
   ```
   - `--workers 1` keeps lazy-loaded ASR engines in one worker process (multiple workers multiply ~3.75 GB IndicConformer memory per worker).
   - Default ping interval/timeout (`20 s / 20 s`) stays healthy during cold model loads thanks to the non-blocking `_message_pump` in [`backend/app/websocket/speech_socket.py`](../backend/app/websocket/speech_socket.py).

2. **Local LLM Server (`llama.cpp`, Optional):**
   - Expected at `LLM_BASE_URL=http://127.0.0.1:8080` serving `qwen3-1.7b` (`Q4_K_M`, `-ngl 24` uses ~`1,520 MiB` VRAM on RTX 2050 per [`tts-benchmark-rtx2050.md`](./deployment/tts-benchmark-rtx2050.md)).
   - If `llama-server` is stopped, `/api/health` marks `llm` degraded while speech perception (`speech_result`) continues working uninterrupted.

3. **Frontend Production Build:**
   ```powershell
   cd frontend
   npm run build
   ```
   - Build-time env vars: `VITE_API_URL`, `VITE_WS_URL`, `VITE_AUTH_REQUIRED`.

4. **Database & Migrations:**
   - Development default: `DATABASE_URL=sqlite:///./database/dev.db`.
   - Apply schema revisions: `alembic upgrade head`.
   - Production PostgreSQL runtime: **unverified** locally (SQL schema & `alembic` revisions are PostgreSQL-compatible via CI checks when `DATABASE_URL_TEST` is unset).

5. **Vector Index (Optional RAG):**
   ```powershell
   .\.venv\Scripts\python.exe -m rag.ingestion --docs data/documents --index-dir data/index
   ```
   - If `faiss` cannot load (e.g. Windows Smart App Control policy), `NumpyVectorIndex` acts as automatic fallback. Missing index files degrade gracefully to direct chat (`status: rag_fallback`).

---

## 2. Container Deployment (Docker Compose)

Container definitions live at repository root (`docker-compose.yml`) and under `deployment/`:
- Validate YAML syntax offline (`config -q`): documented in [`docs/deployment/docker.md`](./deployment/docker.md).
- Container builds and live Docker runtime stacks (`docker compose up --build`, GPU override, Nginx proxy, containerized PostgreSQL) are currently **`unverified`** (Docker daemon was stopped during authoring).

---

## 3. Production Security Checklist

Before setting `APP_ENV=production`:
1. Set `AUTH_REQUIRED=true` and configure a strong random `JWT_SECRET` (at least 32 characters; `Settings` rejects the development fallback in production).
2. Keep `LOG_TRANSCRIPTS=false` so spoken text is never written to server logs.
3. Supply `HF_TOKEN` only at runtime via environment or Docker secret (`--env-file` / `/run/secrets/hf_token`); never commit tokens or model weights.
4. Keep `TTS_ENABLED=false` on 4 GB VRAM GPUs or 16 GB RAM Windows hosts (see [`docs/deployment/tts-benchmark-rtx2050.md`](./deployment/tts-benchmark-rtx2050.md) for measured OOM and WinError 1455 commit-limit failures).
5. Verify `/api/health` shows HTTP `200` and review [`docs/LICENSES.md`](./LICENSES.md) before external redistribution.
