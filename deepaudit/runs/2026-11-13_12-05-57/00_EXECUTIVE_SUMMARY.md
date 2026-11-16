# 00 — Executive Summary

**Audit run:** 2026-11-13 · branch `migration/voicesense` · HEAD `1cc04a4`

## Overall condition

The repository is a **mid-migration, largely working voice-assistant platform** —
not the Wav2Vec2 SER product described in the audit brief. The canonical stack is:

- **Frontend:** React 18 + TS + Vite (`frontend/`), WebSocket client, real mic capture via AudioWorklet.
- **Backend:** FastAPI (`backend/app/main.py`), WebSocket `/ws/speech` + REST `/api/*`.
- **ASR:** SenseVoiceSmall (funasr) + IndicConformer-600m (transformers `AutoModel`, `trust_remote_code=True`), routed by `ai/routing/language_router.py`.
- **VAD:** Silero VAD v5 ONNX (`models/silero_vad.onnx` present).
- **Intent/RAG:** hard-gate `rag/intent_router.py` (regex + e5 exemplar similarity) → FAISS retrieval → Qwen3 LLM.
- **LLM:** Qwen3-1.7B via external llama.cpp server (HTTP, `LLM_BASE_URL`).
- **TTS:** Indic Parler-TTS, disabled by default (`TTS_ENABLED=false`), subprocess worker in `.venv-tts`.
- **DB:** SQLAlchemy 2.x + Alembic, SQLite dev (`database/dev.db`, 86 users present), 7 tables.
- **Legacy:** `src/backend/` + `src/frontend/` quarantined; only referenced by `tests/legacy/` and `scripts/legacy/`.

## Top 10 critical/high findings

1. **`POST /api/auth/token` mints JWTs for arbitrary `user_id`/`username` with no credential check** (`backend/app/api/auth.py:109-133`). Anyone can forge a token for any existing username → full impersonation on all authenticated endpoints and the WS session. **Critical.**
2. **"Fine-tuned Wav2Vec 2.0" SER is not in the runtime.** `Wav2Vec2EmotionEngine` (`ai/inference/emotion.py`) is never imported by `backend/app` or `speech_service`; production emotion = SenseVoice discrete tags with `confidence=None`. **High (claim vs reality).**
3. **History persists fabricated emotion metrics.** `history_service.py:190` hardcodes `confidence=1.0/0.8` and `_map_emotion_coords` (lines 228-239) invents valence/arousal — stored in DB as if measured. **High (data integrity).**
4. **Language routing Tier-2 (spoken LID) is dead code.** `speech_service.py:93-97` constructs `LanguageRouter` without `lid_detector`; `models/voxlingua107/` weights exist but no `LanguageIdentifier` implementation exists. Non-hinted Hindi audio routes to SenseVoice, which cannot transcribe it. **High.**
5. **`AUTH_REQUIRED` defaults to `False`** and `JWT_SECRET` ships an insecure default (`config.py:38-41`); only `APP_ENV=production` triggers the validator. Dev compose sets a weak default secret. **High (config-dependent).**
6. **IndicConformer loading path is unverified/likely broken.** `ai/inference/indicconformer.py:131` calls `transformers.AutoModel.from_pretrained("ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True)` while the module docstring describes a NeMo checkpoint (`indicconformer_stt_indic_hybrid_ctc_large`) and a different calling convention (`model(wav, target_lang, decoder_type)` — speculative, wrapped in try/except fallbacks). No evidence it ever ran successfully. **High.**
7. **Dead frontend components:** `AnalyticsDashboard`, `DocumentManager`, `SettingsPage`, `LandingPage`, `Header`, `VoiceConsole`, top-level `WaveformVisualizer` re-export, and `components/ui/*` partially unused — none are imported by `App.tsx`/`DashboardLayout`. Dashboard/document/settings features described in README do not exist in the active UI. **Medium-High.**
8. **Deployment is mid-flight and uncommitted.** `git status` shows modified `.env.example`, `backend/requirements.txt`, deleted `docker-compose.prod.yml`, and **untracked** `deployment/`, `docker-compose.yml`, `requirements/`, `docs/deployment/docker.md`. Old `docker/` Dockerfiles still reference `src/frontend`/`src/backend` (broken). **Medium.**
9. **No true real-time SER.** Pipeline is VAD-segmented utterance → batch ASR+SER per utterance. No streaming inference, no emotion smoothing, no continuous classification. "Real-time" = utterance latency only. **Medium (expectation gap).**
10. **In-memory rate limiter is per-process** (`core/rate_limiter.py`); multi-worker uvicorn would bypass it. Single-worker is currently enforced in compose, but nothing prevents `--workers 2`. **Medium.**

## What genuinely works (evidence-backed)

- WebSocket `/ws/speech` protocol: start/stop/ping, binary PCM16 frames, VAD segmentation, `speech_result` → `llm_delta`/`llm_done` → `tts_chunk`/`tts_done` streaming, in-frame JWT auth, buffer/duration/utterance rate limits. (`speech_socket.py`)
- REST: `/api/health` (per-component), `/api/speech/upload`, `/api/predict`, `/api/auth/*`, `/api/history/*` with user isolation and cascade delete.
- RAG hard gate: chat queries never touch FAISS (verified by tests); regex + embedding exemplar router; FAISS index exists at `data/index/`.
- Persistence: 7 SQLAlchemy models, Alembic migration verified upgrade/downgrade, fault-isolated threadpool writes, zero-audio-retention invariant, `STORE_TRANSCRIPTS` redaction.
- Tests: **162 passed** in CI-lite run this audit (`pytest tests/backend tests/rag tests/ai -m "not model and not slow and not gpu and not postgres"`); 17 Vitest frontend tests; production `vite build` previously verified.
- Auth crypto: stdlib scrypt hashing + hand-rolled HS256 JWT with constant-time compare — correct implementations.

## What is partially implemented / not verified

- SenseVoice/IndicConformer real-model inference: code paths exist; heavy deps (`torch`, `funasr`, `transformers`, `nemo`) absent from CI env; **not runtime-verified in this audit**.
- TTS: fully implemented but disabled by default; `.venv-tts` worker path unverified here.
- PostgreSQL prod path: schema is portable; no live PG verification.
- WebTransport: only a legacy `/wt` descriptor endpoint; not implemented per roadmap (correctly deferred).

## Scores (methodology in §15 of findings register / report 00 detail)

| Category | Score /100 | Confidence |
|---|---|---|
| Frontend | 72 | Medium-High |
| Backend | 78 | High |
| Database | 82 | High |
| ML (runtime ASR/SER) | 55 | Medium |
| Wav2Vec2 emotion research pipeline | 40 | Medium |
| Audio/real-time | 70 | High |
| LLM integration | 80 | Medium |
| FE↔BE integration | 85 | High |
| BE↔DB integration | 85 | High |
| BE↔ML integration | 60 | Medium |
| Security | 55 | High |
| Testing | 75 | High |
| Deployment readiness | 55 | Medium |
| Documentation | 80 | High |

**Overall implementation completeness: ~68%. Integration completeness: ~72%.**
The gap between "documented architecture" and "verified runtime" is the dominant risk: several headline features (IndicConformer Indic ASR, emotion model, TTS, prod deploy) are implemented-but-unverified.
