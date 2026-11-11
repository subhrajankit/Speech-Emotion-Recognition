# VoiceSense AI — Local Setup Guide

Verified on Windows 11 (`Python 3.13.14`, `Node.js` frontend toolchain); Linux/WSL CI steps match [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (`Ubuntu` CI-lite verified; full local Linux ML runtime unverified on a live Linux workstation).

---

## 1. Python Environments

VoiceSense AI keeps two virtual environments separated by dependency weight:

1. **CI-Lite Environment (`.venv-ci` — Fast, No ML Weights/Torch):**
   Used for API, auth, SQLite database, WebSocket protocol, and mocked/double tests.
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv-ci
     .\.venv-ci\Scripts\python.exe -m pip install --upgrade pip
     .\.venv-ci\Scripts\python.exe -m pip install -r requirements-ci.txt
     ```
   - **Linux / WSL *(local Linux runtime unverified; matches CI)*:**
     ```bash
     python3 -m venv .venv-ci
     .venv-ci/bin/python -m pip install --upgrade pip
     .venv-ci/bin/python -m pip install -r requirements-ci.txt
     ```

2. **Full ML Environment (`.venv` — ASR, RAG Embeddings, Training):**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\python.exe -m pip install -r requirements/runtime.txt -r requirements/ml.txt -r requirements/dev.txt
     ```
   - **Linux / WSL *(unverified locally)*:**
     Install OS libs (`ffmpeg`, `libsndfile1`) if `soundfile`/`torchaudio` requires them, then install `requirements/runtime.txt`, `requirements/ml.txt`, and `requirements/dev.txt`.

> [!NOTE]
> **Windows Smart App Control (Build `26200.9711`) Note:** On hardened Windows hosts, SAC can block unsigned native DLLs such as `onnxruntime_providers_cuda.dll` or native `faiss` binaries. The backend automatically degrades to CPU execution and `NumpyVectorIndex` without crashing.

---

## 2. Environment Configuration

Copy the environment template and adjust only what you need:
```powershell
Copy-Item .env.example .env
```
Key defaults for local development:
- `HOST=127.0.0.1`, `PORT=8000`
- `DATABASE_URL=sqlite:///./database/dev.db`
- `LAZY_LOAD_MODELS=true`, `PRELOAD_DEFAULT_ENGINE=false`
- `AUTH_REQUIRED=false` (set `AUTH_REQUIRED=true` + strong `JWT_SECRET` for authenticated mode)
- `TTS_ENABLED=false` (recommended off; see [`docs/deployment/tts-benchmark-rtx2050.md`](./deployment/tts-benchmark-rtx2050.md))
- `HF_TOKEN=` (set in environment at runtime only if downloading gated `ai4bharat/indic-conformer-600m-multilingual`)

---

## 3. Database Initialization (SQLite Dev)

Ensure local database migrations are applied using Alembic:
```powershell
.\.venv-ci\Scripts\alembic.exe upgrade head
```

---

## 4. Optional Local LLM (`llama.cpp`) & RAG Index

1. **Local LLM Server (Optional):** Run `llama-server` serving `Qwen3-1.7B` (`Q4_K_M` GGUF) on `127.0.0.1:8080`. If omitted, speech perception and emotion tags still work while assistant generation reports `llm_unavailable`.
2. **Vector Index (Optional):** Build the local sample RAG index (`data/documents` -> `data/index`):
   ```powershell
   .\.venv\Scripts\python.exe -m rag.ingestion --docs data/documents --index-dir data/index
   ```

---

## 5. Start Backend & Frontend

1. **Start Backend** (single worker + explicit default keepalive flags recommended for lazy cold loading):
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --ws-ping-interval 20 --ws-ping-timeout 20
   ```
2. **Install & Start Frontend:**
   ```powershell
   cd frontend
   npm ci
   npm run dev
   ```
3. **Verify Health:** Open `http://127.0.0.1:8000/api/health` (REST) and `http://127.0.0.1:5173` (UI).
4. **Walkthrough:** Follow the step-by-step live demo in [`docs/DEMO.md`](./DEMO.md).
