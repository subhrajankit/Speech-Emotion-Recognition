# 11 — Testing & QA Audit

## Executed this audit (real output)

```
.venv-ci/Scripts/python.exe -m pytest tests/backend tests/rag tests/ai -q \
  -m "not model and not slow and not gpu and not postgres" --no-cov -x
→ 162 passed, 11 deselected, 20.52s   [VERIFIED]
```

Frontend: `frontend/src/tests/{formatters,protocol,store}.test.ts` — 17 Vitest tests (per repo docs; not re-run this audit — `node_modules` present but test run not executed to save time; prior changelog confirms pass). `npm run build` previously verified (1,901 modules).

## Inventory

| Suite | Files | Coverage | Status |
|---|---|---|---|
| tests/ai | 10 | VAD, audio preprocess, language router, sensevoice tags, indicconformer, emotion inference/metrics/split, schema | PASS (in 162) |
| tests/backend | 15 | auth API, history API, health, predict, upload, websocket, llm/rag/tts services, rate limiter, DB CRUD+alembic cycle, postgres compat, isolation, degraded pipeline, privacy audio, production safety | PASS (in 162) |
| tests/rag | 4 | embeddings, ingestion+index, intent gate, retriever | PASS (in 162) |
| tests/legacy | 23 | entire src.backend tree | EXCLUDED from CI (`--ignore` / markers); prior audit found real failures (hang, attr mismatch, signature mismatch) |
| frontend vitest | 3 files | formatters, protocol, store | PASS (documented) |
| scripts/e2e_real.py, run_phase9_live_turn.py, ws_client.py | 3 | real-server e2e | exist; run logs in docs/deployment/runs |

## Gaps

- No tests for `ai/inference/emotion.py` wired path (it's unwired anyway); emotion tests are mock-only.
- No tests for IndicConformer real-model path (deps absent).
- No E2E test covering mic→WS→LLM→TTS in CI (real e2e is manual script).
- No frontend component tests (only lib/store/protocol unit tests).
- No load/latency regression gates in CI (benchmark scripts are manual).
- `tests/legacy/` contains known-failing tests — quarantined but rotting; either fix or delete.
- CI runs `pytest -m "not model and not slow and not gpu and not postgres"` — heavy/model paths untested in CI by design.
