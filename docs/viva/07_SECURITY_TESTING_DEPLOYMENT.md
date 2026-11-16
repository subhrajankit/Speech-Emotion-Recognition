# 07 — Security, Testing, Deployment

## 1. Security model (what protects the app)

| Layer | Mechanism | Where |
|---|---|---|
| Passwords | `hashlib.scrypt` n=16384 r=8 p=1, 16-byte salt, constant-time verify | `core/security.py` |
| Sessions | Hand-rolled HS256 JWT (RFC 7515), alg pinned, exp/nbf + 10 s leeway | `core/security.py` |
| WS auth | JWT inside `start` frame (never URL); subject must exist in DB; close 1008 on failure | `websocket/speech_socket.py` |
| Prod hardening | Refuses boot if `production` + weak/missing JWT secret or `AUTH_REQUIRED=false` | `core/config.py` validator |
| Rate limits | 20 utt/min/session (sliding window, silence refunds), 30 s/utterance, 10 MB uploads, 10 auth/min/IP | `core/rate_limiter.py` |
| Upload safety | MIME allow-list, extension check, chunked bounded read, WAV container validation | `api/speech.py` |
| Prompt injection | RAG excerpts labeled "untrusted data, never instructions"; TTS strips citations/markdown | `prompt_builder.py`, `tts_service.py` |
| Privacy | Zero raw-audio persistence; `STORE_TRANSCRIPTS=false` → `[REDACTED_BY_POLICY]`; `DELETE /api/history` purge; anonymous sessions persist nothing | `history_service.py`, `api/history.py` |
| Network | All model servers bind `127.0.0.1` only | config defaults, llama.cpp flags |
| Secrets | `.env` gitignored; `security/secrets.example/` templates only; no weights/secrets in git (verified by audit) | repo |

See also `brain/10_SECURITY.md`, `brain/18_OWASP_MAPPING.md`,
`security/security-checklist.md`, `docs/architecture/database.md`.

## 2. Testing strategy

Pytest with `--import-mode=importlib`, markers
`unit/integration/model/slow/gpu/postgres` (`pyproject.toml`).
`tests/legacy/` is ignored by default.

| Suite | What it proves |
|---|---|
| `tests/ai/` | VAD frame math + silence/speech classification + segmenter lifecycle + thread safety; audio preprocessing; SenseVoice tag parsing; engine no-speech contracts; IndicConformer `emotion=None` invariant + missing-weight errors; 3-tier router; VoxLingua LID; emotion split/quarantine/metrics; eval baseline |
| `tests/backend/` | auth register/login/me/verify; history CRUD + isolation + purge; health aggregation; upload validation (type/size/decode); `/api/predict`; rate limiter windows + refund; WS protocol (start/stop/ping, errors, keepalive); LLM service (think-strip, circuit breaker, streaming); RAG service (chat→0 retrieval calls); TTS service; DB CRUD + FK enforcement + fault isolation; degraded pipeline; privacy (no audio persisted); production-safety config; postgres compat (skips unless `DATABASE_URL_TEST`); English-only hint rejection |
| `tests/rag/` | embeddings prefix/normalization; ingestion+index build/load/mismatch; intent gate; retriever thresholding + citation format |
| `tests/eval/` | English ASR metrics harness |
| `frontend/src/tests/` | 24 Vitest files — all `lib/` helpers, protocol codec, store, key components |
| `tests/samples/` | real WAV fixtures (en/hi/zh speech, TTS outputs, silence, empty) |

CI: `.github/workflows/ci.yml` runs the CI-lite suite (no ML weights) +
frontend build/test on `ubuntu-latest`; `scripts/ci/check_import_isolation.py`
enforces the `ai/`↔LLM/RAG/TTS boundary in CI.

Commands:
```powershell
# backend (CI-lite venv — no torch needed)
.\.venv-ci\Scripts\python.exe -m pytest -m "not model and not slow and not gpu and not postgres"
.\.venv-ci\Scripts\python.exe scripts/ci/check_import_isolation.py
# frontend
cd frontend; npm test -- --run; npx tsc --noEmit; npm run lint; npm run build
```

## 3. Deployment

- **Dev**: `docker-compose.yml` — frontend (nginx serving `dist/`) + backend
  (uvicorn) + optional `llm` profile for llama.cpp. `docker compose config -q`
  syntax-verified; **runtime unverified** (daemon wasn't running).
- **Prod variants**: `deployment/docker-compose.{prod,gpu,memory-light}.yml`
  with `deployment/docker/Dockerfile.{backend,frontend}`,
  `entrypoint-backend.sh`, `nginx.conf`.
- **DB**: SQLite file for dev; `DATABASE_URL=postgresql+psycopg://...` for prod
  (schema ready; runtime marked unverified).
- **Ops**: `runbooks/` incident guides (api/auth/db/deploy/rollback/backup),
  `scripts/database/backup*.sh/py`, `monitoring/health-checks/check_health.*`,
  `.github/workflows/backup.yml`.
- **Model weights**: never committed, never baked into images — downloaded to
  `models/` / HF cache at setup; gated models need `HF_TOKEN`.

## 4. Honest verification ledger (for viva credibility)

From `docs/architecture/status.md` + README §16 — the project's own standard is
`real-verified` vs `unverified`/`NOT YET MEASURED`:

- **Verified with real models**: VAD, audio preprocessing, language router,
  IndicConformer CPU CTC (1.2 s median on 5.28 s Hindi clip), SenseVoice on a
  synthetic English clip, LLM streaming + breaker, RAG gate 47/50, keepalive
  under 49 s cold load.
- **Automated-only**: auth/history APIs, most backend unit tests, frontend
  build + Vitest.
- **Unverified/not measured**: PostgreSQL runtime, Docker builds/runs, full
  CREMA-D SER training, SenseVoice zero-shot SER baseline, standardized
  WER/CER, code-mixed (Hinglish) speech, TTS in production (disabled).

Quoting this ledger accurately is one of the strongest things you can do in
the viva — it shows engineering honesty.
