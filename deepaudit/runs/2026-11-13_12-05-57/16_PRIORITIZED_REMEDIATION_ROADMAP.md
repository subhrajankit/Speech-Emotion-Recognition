# 16 — Prioritized Remediation Roadmap

## P0 — Critical blockers

1. **VS-CRIT-001** Remove/gate `POST /api/auth/token`. *Accept:* forged token rejected; register/login/me unaffected. *Risk:* test harnesses using it break — update them to use login. *Deps:* none.
2. **VS-HIGH-005** Enforce strong `JWT_SECRET` at startup in ALL envs (or at least non-dev); remove insecure defaults from compose. *Accept:* app refuses default secret outside explicit dev flag.

## P1 — Essential functional fixes

3. **VS-HIGH-003** Implement `VoxLingua107LanguageIdentifier` (weights already in `models/voxlingua107/`) and inject into `LanguageRouter` in `speech_service.initialize`. *Accept:* unhinted Hindi routes to IndicConformer.
4. **VS-HIGH-004** Verify/fix IndicConformer loading against real model card; add a live smoke test (`scripts/test_indicconformer_direct.py` exists — run it). *Accept:* known Hindi wav → transcript.
5. **VS-HIGH-002** Stop fabricating emotion metrics: store NULL confidence/valence/arousal (or real scores) in `emotion_results`; keep raw_tags. *Accept:* no invented floats in DB.
6. **VS-MED-004** Commit Phase 12 deployment; delete legacy `docker/` dir. *Accept:* clean `git status`; `docker compose build` works.
7. **VS-HIGH-001 decision** Either wire `Wav2Vec2EmotionEngine` (after fixing `extract_features` to use real embeddings — VS-MED-007) or update README/brain to state SenseVoice-tag SER is production. *Accept:* docs match runtime.

## P2 — Integration & reliability

8. **VS-MED-001/005/006** Resolve dead frontend: either implement dashboard/document/settings/landing or remove files; wire or remove `/api/speech/upload`,`/api/predict` (add upload UI or delete endpoints); implement `include_assistant` or return 501.
9. **VS-MED-002/003** Add IP rate limit to upload/predict; document/enforce single-worker or shared limiter.
10. **VS-MED-008** Move DB calls off event loop (threadpool like history_service, or aiosqlite).
11. Consolidate requirements files; add missing faiss-cpu/python-docx/pypdf to runtime reqs.

## P3 — Performance & optimization

12. Real Wav2Vec2 feature extraction + full CREMA-D training run (only after P1.7 decision); benchmark SER head honestly.
13. Polyphase resampling; skip double-VAD on WS path; adaptive max_tokens.
14. Async SQLAlchemy sessions; connection pooling for PG.

## P4 — Enhancements & debt

15. Remove `src/` legacy tree + `tests/legacy/` after porting needed pieces (auth/rate-limiter already ported; liveness/webtransport/audit/gemini remain candidates).
16. RAG document-management API + working DocumentManager UI.
17. Token revocation, refresh flow, structured logging of security events.
18. Refresh stale docs (`current-state.md`), commit or gitignore build artifacts.

## Suggested order

P0.1→P0.2 (security) → P1.3/1.4 (make Indic path real) → P1.5 (data honesty) → P1.6 (deployable repo) → P1.7 (SER claim decision) → P2.* → P3/P4.
