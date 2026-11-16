# VoiceSense AI — Docker Deployment Guide (Phase 11)

## 1. Architecture & Compose Stack Layout

VoiceSense AI ships with two primary Docker Compose configurations (CPU by default) and two modular overrides:

| File | Role | Services Included | Default Ports (`127.0.0.1` only) |
| :--- | :--- | :--- | :--- |
| [`docker-compose.yml`](../../docker-compose.yml) | **Development stack** | `backend` (FastAPI + ASR/Emotion/RAG, SQLite named volume), `frontend` (Node 20 Vite dev), optional `llm` (`--profile llm`) | Backend `8000`, Frontend `5173`, LLM `8080` (profile `llm`) |
| [`deployment/docker-compose.prod.yml`](../../deployment/docker-compose.prod.yml) | **Production stack (CPU)** | `frontend` (Nginx reverse proxy), `backend` (FastAPI non-root), `postgres` (`postgres:16-alpine`), `llm` (`llama.cpp:server`) | Frontend `80` only (`postgres` and `llm` internal only) |
| [`deployment/docker-compose.gpu.yml`](../../deployment/docker-compose.gpu.yml) | **NVIDIA GPU override** | Switches `backend` to CUDA PyTorch index + GPU reservation and `llm` to `llama.cpp:server-cuda` | Inherits base stack |
| [`deployment/docker-compose.memory-light.yml`](../../deployment/docker-compose.memory-light.yml) | **Memory-light override** | Sets `backend` to `4g` cap + `PRELOAD_DEFAULT_ENGINE=false`, `SENSEVOICE_THREADS=2`, `INFERENCE_CONCURRENCY_LIMIT=1` | Inherits base stack |

> **Important Legacy Note**: The legacy `docker/` directory remains untouched in place until explicit removal approval. All new container builds use `deployment/docker/`.

---

## 2. Requirements Split & Images

- **`requirements/runtime.txt`**: API, auth, SQLAlchemy 2.x, Alembic, `psycopg[binary]`, audio decoding, ONNX Silero VAD runtime, PDF/DOCX extractors (`pypdf`, `python-docx`).
- **`requirements/ml.txt`**: `torch`, `torchaudio`, `funasr`, `transformers`, `huggingface-hub`, `modelscope`, `sentence-transformers`, `faiss-cpu`.
- **`requirements/dev.txt`**: `-r runtime.txt` + `pytest`, `pytest-asyncio`, `pytest-cov`, `requests`.
- **`requirements-ci.txt`**: Preserved untouched for the CI-lite GitHub Actions workflow (zero heavy ML frameworks).
- **Official `llama.cpp` Images**: Cited from official documentation (`https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md`, migrated from legacy `ghcr.io/ggerganov/llama.cpp` to **`ghcr.io/ggml-org/llama.cpp`**):
  - **CPU**: `ghcr.io/ggml-org/llama.cpp:server`
  - **CUDA**: `ghcr.io/ggml-org/llama.cpp:server-cuda`

---

## 3. Core Operational Invariants

1. **LLM Independence**: Neither `docker-compose.yml` nor `deployment/docker-compose.prod.yml` declares `depends_on` on `llm`. Backend starts and serves ASR + emotion perception (`speech_result`) normally even if the `llm` container is stopped, absent, or unhealthy.
2. **English-Only ASR by Default**: `ASR_ENGLISH_ONLY=true` (backend) / `VITE_ASR_ENGLISH_ONLY=true` (frontend build) is the default; only `en`/`auto`/empty/`null` hints are accepted. Hindi/Indic routing requires explicitly setting `ASR_ENGLISH_ONLY=false` on the backend **and** `VITE_ASR_ENGLISH_ONLY=false` at frontend build time. Automatic spoken language identification (LID) is **not** wired into runtime (`docs/architecture/status.md`). In multilingual mode, Hindi utterances must specify `language_hint: "hi"` in the WebSocket `"start"` message (otherwise requests default to `SenseVoiceSmall`, whose model card supports `zh`, `en`, `yue`, `ja`, `ko` only).
3. **WebSocket Keepalive & Single Worker**: Based on Phase 10b findings (`ADR 037`), `uvicorn` uses `--workers 1 --ws-ping-interval 20 --ws-ping-timeout 20`. Single-worker mode preserves in-process model singletons and rate limiters, while `_message_pump()` keeps socket reads draining during ~49s cold model loads. Nginx proxies `/ws/` with `proxy_read_timeout 3600s` and `proxy_send_timeout 3600s`.
4. **TTS Disabled in Containers**: `TTS_ENABLED=false` is hardcoded in `Dockerfile.backend` and all compose files. Indic Parler-TTS is out of scope for Phase 11 due to 4 GB VRAM / host commit exhaustion observed in Phase 8 (`docs/deployment/tts-benchmark-rtx2050.md`).
5. **No Raw Audio or Secret Persistence**: `.dockerignore` blocks `models/`, `data/`, `.env`, `tests/samples/`, `*.wav`, and database files. Zero weights, tokens, or audio fixtures enter any image.

---

## 4. Model Weights, Data & Runtime `HF_TOKEN` Secret

- **Bind Mounts**:
  - `./models:/app/models:ro` — supplies `silero_vad.onnx` and (for `llm`) GGUF weights such as `qwen3-1.7b.gguf`.
  - `./data:/app/data` — supplies RAG documents (`data/documents/`) and FAISS index (`data/index/`).
- **Named Volumes**:
  - `voicesense_hf_cache` (`/cache/huggingface`) and `voicesense_modelscope_cache` (`/cache/modelscope`) persist downloaded weights across container recreation.
  - `voicesense_sqlite_dev_data` (dev) and `voicesense_postgres_data` (prod, port `5432` never published to host).
- **Gated Hugging Face Models (`ai4bharat/indic-conformer-600m-multilingual`)**:
  - Never bake `HF_TOKEN` into Dockerfiles or commit it to `.env.example` / `.env`.
  - **Development**: Export `HF_TOKEN` in your shell before running `docker compose --profile llm up`:
    ```powershell
    $env:HF_TOKEN = "hf_..."
    docker compose up --build
    ```
  - **Production**: `deployment/docker-compose.prod.yml` uses Docker Compose `secrets:` (`hf_token` backed by host environment `HF_TOKEN` -> mounted read-only at `/run/secrets/hf_token` and exported by `entrypoint-backend.sh` inside container runtime PID memory only). If operating purely offline with pre-mounted models, leave `HF_TOKEN=` empty in your host environment / untracked `.env`.

---

## 5. Memory Limits, WSL2 `.wslconfig` & Memory-Light Mode

- **Observed Baseline**: Dual-engine backend residence reached **~11.8 GB private memory** (IndicConformer working set ~3,749–3,750 MB alongside SenseVoiceSmall + PyTorch runtime + RAG).
- **Host / WSL2 Reality**: Windows Docker Desktop WSL2 defaults to ~50% of physical RAM (~7.85 GiB on a 16 GB machine) when `%USERPROFILE%\.wslconfig` is absent.
- **Proposed `%USERPROFILE%\.wslconfig` (Not Applied Automatically)**:
  Before running full dual-engine ASR + local `llama.cpp` concurrently on a 16 GB Windows host, consider creating `%USERPROFILE%\.wslconfig` manually:
  ```ini
  [wsl2]
  memory=12GB
  swap=8GB
  ```
  *(Leaves ~4 GB for Windows; restart WSL afterward with `wsl --shutdown`.)*
- **Memory-Light Single-Engine Lazy Mode**:
  Use `deployment/docker-compose.memory-light.yml` on ~8 GB WSL2 systems when running Auto/English only:
  ```powershell
  docker compose -f docker-compose.yml -f deployment/docker-compose.memory-light.yml up --build
  ```
  This sets `backend` `mem_limit: 4g`, `LAZY_LOAD_MODELS=true`, `PRELOAD_DEFAULT_ENGINE=false`, `SENSEVOICE_THREADS=2`, and `INFERENCE_CONCURRENCY_LIMIT=1`, keeping IndicConformer (`~3.75 GB`) unloaded unless a client in multilingual mode (`ASR_ENGLISH_ONLY=false`) requests `language_hint="hi"`.
- **Reported App-Code Gaps (Out of Scope for Phase 11)**:
  1. **No hard single-engine disable toggle**: `SpeechService.initialize()` always prepares both engines; in multilingual mode (`ASR_ENGLISH_ONLY=false`) any `language_hint="hi"` request triggers IndicConformer loading. In the default English-only MVP, non-English hints are rejected before routing.
  2. **No `idle-unload` mechanism**: Neither `docs/architecture/status.md` nor `backend/app/` currently implements inactivity-based model unloading.
  3. **Frontend Nginx `VITE_*` behavior**: `frontend/src/lib/env.ts` treats empty `VITE_API_URL` as falsy (`||`), so production builds bake `VITE_API_URL=http://127.0.0.1` and `VITE_WS_URL=ws://127.0.0.1/ws/speech` alongside `CORS_ORIGINS=http://127.0.0.1,http://localhost`.
  4. **RAG configuration defaults**: `backend/app/main.py` initializes `RAGService()` with default `"data/index"` and `"intfloat/multilingual-e5-small"`, ignoring `.env.example` path/model overrides (`FAISS_INDEX_PATH`, `DOCUMENTS_STORE_PATH`, `EMBEDDING_MODEL`); mount `./data:/app/data` at the canonical location.

---

## 6. Complete Environment Variable Reference (`Env Var × Service × Required/Optional × Default`)

| Variable | Service(s) | Req / Opt | Default | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `APP_ENV` / `ENVIRONMENT` | `backend` | Optional (`Required` `"production"` in prod) | `"development"` | `APP_ENV=production` refuses startup on weak/default `JWT_SECRET`. |
| `HOST` / `PORT` | `backend` | Optional | `"127.0.0.1"` / `8000` | Containers bind `0.0.0.0:8000` internally; host binds `127.0.0.1` only. |
| `DEBUG` | `backend` | Optional | `false` (`true` in dev compose) | FastAPI debug flag. |
| `CORS_ORIGINS` | `backend` | Optional | Localhost `5173`/`3000` origins | Prod compose adds `http://127.0.0.1,http://localhost`. |
| `LOG_LEVEL` / `LOG_TRANSCRIPTS` | `backend` | Optional | `"INFO"` / `false` | Transcript logging suppressed by default. |
| `STORE_TRANSCRIPTS` | `backend` | Optional | `true` | `false` redacts stored transcripts; raw audio never persisted. |
| `AUTH_REQUIRED` | `backend`, `frontend` build | Optional (`true` in prod compose) | `false` | Gates REST routes and WebSocket `start.auth_token`. |
| `JWT_SECRET` | `backend` | **Required in prod** (`>=32` chars) | Dev insecure placeholder | Prod compose fails fast on missing `JWT_SECRET`. |
| `SESSION_TIMEOUT_MINUTES` | `backend` | Optional | `60` | JWT TTL in minutes. |
| `DATABASE_URL` | `backend` (+ Alembic) | Optional dev / **Required prod** | `sqlite:///./database/dev.db` | Prod injects `postgresql+psycopg://...@postgres:5432/...`. |
| `POSTGRES_USER` / `POSTGRES_DB` | `postgres`, `backend` | Required in prod | `voicesense` | Official Postgres init user and DB name. |
| `POSTGRES_PASSWORD` | `postgres`, `backend` | **Required in prod** (`:?`) | None (fail-fast) | Compose exits non-zero if unset; port `5432` never published. |
| `RUN_MIGRATIONS` | `backend` entrypoint | Optional | `false` (`true` in compose) | Runs `alembic upgrade head` on startup before `uvicorn`. |
| `RATE_LIMIT_UTTERANCES_PER_MINUTE` / `RATE_LIMIT_AUTH_PER_MINUTE` | `backend` | Optional | `20` / `10` | Per-session WS & per-IP auth limits. |
| `MAX_UTTERANCE_DURATION_SECONDS` / `WS_MAX_BUFFER_BYTES` | `backend` | Optional | `30.0` / `5242880` | Per-turn duration & WS buffer caps. |
| `MAX_RAG_UPLOAD_SIZE_BYTES` / `MAX_UPLOAD_SIZE_BYTES` | `backend` | Optional | `10485760` | 10 MB upload cap (Nginx allows `15m`). |
| `INFERENCE_CONCURRENCY_LIMIT` | `backend` | Optional | `2` (`1` in memory-light) | Asyncio semaphore around worker-thread ASR. |
| `VAD_THRESHOLD` / `SILERO_VAD_MODEL_PATH` / `SILERO_VAD_THRESHOLD` | `backend`, `ai` | Optional | `0.5` / `models/silero_vad.onnx` / `0.5` | `SILERO_VAD_*` read via `os.getenv` in `ai/preprocessing/vad.py`. |
| `SENSEVOICE_MODEL_DIR` / `SENSEVOICE_DEVICE` / `SENSEVOICE_THREADS` | `backend`, `ai` | Optional | `iic/SenseVoiceSmall` / `cpu` / `4` | Primary English/CJK ASR + emotion engine (`2` threads in memory-light). |
| `INDICCONFORMER_MODEL_DIR` / `INDICCONFORMER_REVISION` | `backend`, `ai` | Optional | `ai4bharat/indic-conformer-600m-multilingual` / pinned SHA | Hindi ASR engine, used only in multilingual mode (`ASR_ENGLISH_ONLY=false` + `language_hint="hi"`). |
| `INDICCONFORMER_DEVICE` / `INDICCONFORMER_DECODER_TYPE` / `LID_CONFIDENCE_THRESHOLD` | `backend`, `ai` | Optional | `cpu` / `ctc` / `0.6` | IndicConformer config; stays CPU in GPU compose by default to save 4 GB VRAM. |
| `LAZY_LOAD_MODELS` / `PRELOAD_DEFAULT_ENGINE` | `backend` | Optional | `true` / `false` | Defers ~3.75 GB IndicConformer load until Hindi requested (multilingual mode only). |
| `LLM_BASE_URL` / `LLM_MODEL_NAME` | `backend` | Optional | `http://127.0.0.1:8080` / `qwen3-1.7b` | Compose sets `http://llm:8080`. |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` | `backend` | Optional | `30.0` / `120` / `0.7` | Qwen3 inference bounds. |
| `LLM_REPEAT_PENALTY` / `LLM_FREQUENCY_PENALTY` / `LLM_PRESENCE_PENALTY` | `backend` | Optional | `1.1` / `0.2` / `0.0` | Phase 8i repetition safeguards. |
| `LLM_ENABLE_THINKING` / `LLM_HEALTH_CACHE_SECONDS` / `LLM_FAILURE_THRESHOLD` / `LLM_COOLDOWN_SECONDS` | `backend` | Optional | `false` / `5.0` / `3` / `15.0` | `<think>` filtering & circuit-breaker config. |
| `TTS_ENABLED` | `backend` | Optional (`false` in containers) | `false` | Hard-disabled in containers; Phase 11 excludes TTS. |
| `HF_TOKEN` | `backend` (runtime secret) | Conditional (gated HF downloads) | Unset / empty | Passed via runtime secret (`/run/secrets/hf_token` in prod; host env in dev). |
| `HF_HOME` / `MODELSCOPE_CACHE` | `backend` | Optional | `/cache/huggingface` / `/cache/modelscope` | Backed by persistent Docker named volumes. |
| `VITE_API_URL` / `VITE_WS_URL` / `VITE_AUTH_REQUIRED` | `frontend` build | Optional | `http://127.0.0.1:8000` / `ws://.../ws/speech` / `false` | Baked at `vite build`; prod sets `http://127.0.0.1` & `ws://127.0.0.1/ws/speech`. |
| `LLM_MODEL_FILE` / `LLM_CTX_SIZE` / `LLM_GPU_LAYERS` | `llm` | Optional | `qwen3-1.7b.gguf` / `4096` / `24` | `llama-server` container CLI arguments (`-ngl` in GPU override). |
| `BACKEND_MEM_LIMIT` / `MEMORY_LIGHT_BACKEND_MEM_LIMIT` / `LLM_MEM_LIMIT` | Compose limits | Optional | `12g` / `4g` / `3g` | Explicit container RAM caps. |
| `DATABASE_URL_TEST` | Test runner only | Optional | None | Skips `test_postgres_compatibility.py` if unset. |
| `USE_CUDA` / `TORCH_INDEX_URL` | `backend` build arg | Optional | `false` / CPU wheel index | Selects CPU vs CUDA PyTorch wheels at `docker build`. |

---

## 7. Usage Commands

> **Compose Path Note**: Because `deployment/docker-compose.prod.yml` resides under `deployment/`, always invoke it from the repository root with `--env-file .env` (if using a root `.env`) so variable interpolation reads `./.env` cleanly.

### Validation (Safe Without Starting Daemon / Pulling Weights)
```powershell
# Dev stacks
docker compose -f docker-compose.yml config -q
docker compose -f docker-compose.yml --profile llm config -q

# Production & overrides (pass --env-file .env when .env exists at repo root)
docker compose -f deployment/docker-compose.prod.yml --env-file .env config -q
docker compose -f deployment/docker-compose.prod.yml -f deployment/docker-compose.gpu.yml --env-file .env config -q
docker compose -f docker-compose.yml -f deployment/docker-compose.memory-light.yml config -q
```

### Runtime Execution (After Docker Desktop Is Running & Build Approved)
```powershell
# 1. Dev (CPU backend + Vite frontend, SQLite volume; no LLM container)
docker compose up --build

# 2. Dev with local Qwen3 CPU LLM
docker compose --profile llm up --build

# 3. Prod (CPU default; fails fast if POSTGRES_PASSWORD or JWT_SECRET is missing)
docker compose -f deployment/docker-compose.prod.yml --env-file .env up -d --build

# 4. Prod with NVIDIA GPU override (note 4 GB RTX 2050 VRAM contention: IndicConformer stays CPU by default)
docker compose -f deployment/docker-compose.prod.yml -f deployment/docker-compose.gpu.yml --env-file .env up -d --build
```

### Verification Commands (Run After Stack Starts)
```powershell
# Health from inside backend container and through Nginx frontend
docker compose -f deployment/docker-compose.prod.yml exec backend curl -sf http://127.0.0.1:8000/api/health
curl.exe -sf http://127.0.0.1/api/health

# Live memory measurement after engines load
docker stats --no-stream

# Image size & clean-image hygiene check (verify zero weights/tokens/audio inside image)
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
docker compose -f deployment/docker-compose.prod.yml exec backend sh -c "ls -la /app/models /app/data /app"

# LLM-down resilience test (ASR/emotion must still succeed)
docker compose -f deployment/docker-compose.prod.yml stop llm
```
