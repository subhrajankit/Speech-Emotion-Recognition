# 18 — Audit Limitations & Unverified Items

## Could not verify (blocked)

1. **Real ASR inference** — `torch`, `funasr`, `transformers`, `nemo`, `sentence-transformers`, `faiss` native not installed in the audit Python env. SenseVoice/IndicConformer/e5/FAISS paths verified by code+unit tests only, not live inference.
2. **IndicConformer correctness** — `AutoModel.from_pretrained(..., trust_remote_code=True)` call signature is speculative; whether `ai4bharat/indic-conformer-600m-multilingual` exists on HF hub with that remote code and accepts `(wav, target_lang, decoder_type)` is **unverified** — highest-risk unverified component.
3. **TTS** — `TTS_ENABLED=false`; `.venv-tts` worker and Parler-TTS load path not executed.
4. **LLM** — llama-server not running; SSE/cooldown paths unit-tested only.
5. **PostgreSQL** — no live PG; schema portability inferred from SQLAlchemy/alembic batch mode + compat test.
6. **Docker** — no image builds run; Dockerfile correctness by inspection only.
7. **Frontend runtime** — no browser session; component wiring verified statically (imports/call graph).
8. **WebTransport** — not implemented (correctly deferred); legacy `/wt` is descriptor-only.
9. **`frontend/public/audio-processor.js`** — worklet internals not read; resample correctness inside worklet unverified.
10. **`config/production/backup-config.env`, `backup.cron`** — contents not fully inspected for secrets (names only).
11. **`docs/api/openapi.json`** — freshness vs current routes unverified.
12. **`database/dev.db` git-tracking status** — file exists in worktree; whether committed not checked.
13. **HF gated-model access** — `HF_TOKEN` provisioning for IndicConformer/Parler-TTS unverified.
14. **Legacy `tests/legacy/` failures** — carried over from Oct-22 audit; not re-run.
15. **`.agents/` tree (779 files)** — out of scope (agent tooling, not application code).

## Claims treated as unverified

- README/changelog performance numbers (latency, RTF, WER) — documentation claims, not reproduced.
- "Phase 12 complete" — deployment files exist but are uncommitted and unbuilt.
- Emotion "confidence" anywhere downstream of `history_service` — fabricated (finding VS-HIGH-002).
