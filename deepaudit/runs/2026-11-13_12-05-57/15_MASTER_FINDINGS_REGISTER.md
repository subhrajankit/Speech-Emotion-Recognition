# 15 — Master Findings Register

| ID | Title | Sev | Category | Files | Root cause | Impact | Fix | Verify |
|---|---|---|---|---|---|---|---|---|
| VS-CRIT-001 | Unauthenticated JWT minting endpoint | Critical | Security | api/auth.py:109-133 | "backwards-compat" token endpoint kept from test harness | Account takeover of any user | Remove endpoint or require admin/auth; gate behind settings flag | Attempt forged token → 401/403 |
| VS-HIGH-001 | Wav2Vec2 SER not in runtime | High | ML/claims | ai/inference/emotion.py | Engine built but never wired | Title/README overstate capability | Wire engine or descope claim | EmotionResult from engine in /ws/speech |
| VS-HIGH-002 | Fabricated emotion metrics persisted | High | Data integrity | history_service.py:185-195,228-239 | Static confidence + valence/arousal map | DB/history show invented numbers as measured | Store NULL/real scores; derive valence only if model provides | Inspect emotion_results rows |
| VS-HIGH-003 | LID tier dead; Indic routing hint-only | High | ML/routing | speech_service.py:93-97, language_router.py:197 | No LanguageIdentifier impl; VoxLingua107 weights unused | Unhinted Hindi → SenseVoice (can't transcribe) | Implement VoxLingua107 detector, inject into router | Hindi audio no-hint → indicconformer |
| VS-HIGH-004 | IndicConformer call path unverified | High | ML | ai/inference/indicconformer.py:221-235 | Speculative signature + fallbacks; docstring says NeMo but code uses transformers | Indic ASR may silently fail/garbage | Verify real model card API; run live inference | Transcribe known Hindi wav |
| VS-HIGH-005 | Weak/default secrets outside prod validator | High | Security | config.py:38-41,121-135 | Validator only on APP_ENV=production | Dev/staging forgeable JWTs | Require JWT_SECRET always; fail on default | Boot with default → refuse |
| VS-MED-001 | Dead frontend feature set | Med | FE | 6 unimported components | Migration leftovers | Dashboard/docs/settings/landing absent | Wire or delete components | grep imports; UI routes |
| VS-MED-002 | No REST rate limit on inference endpoints | Med | Security | api/speech.py, prediction.py | Only auth endpoints limited | DoS via uploads | Add IPRateLimiter to upload/predict | Hammer endpoint → 429 |
| VS-MED-003 | Per-process rate limiter | Med | Backend | core/rate_limiter.py | In-memory singletons | Limits multiply with workers | Redis/shared store or enforce workers=1 | workers=2 test |
| VS-MED-004 | Deployment uncommitted; legacy docker/ broken | Med | DevOps | git status; docker/* | Phase 12 in flight | Repo ≠ deployable | Commit phase 12; delete docker/ | docker compose build |
| VS-MED-005 | REST predict/upload orphaned (no FE caller) | Med | Integration | api/speech.py, prediction.py | WS is primary path | Dead endpoints; untested surface | Add upload UI or remove | FE call exists |
| VS-MED-006 | `include_assistant` returns stub | Med | API | api/prediction.py:29-34 | Phase-2 placeholder kept | Misleading flag | Implement or remove flag | Real LLM call or 501 |
| VS-MED-007 | Emotion engine pseudo-features | Med | ML/research | ai/inference/emotion.py:123-140 | extract_features is RNG projection | "Training" meaningless | Real Wav2Vec2 embeddings | Feature dim from model |
| VS-MED-008 | Sync DB calls in async handlers | Med | Backend | api/auth.py, history.py | SQLAlchemy sync sessions | Event-loop blocking | aiosqlite/async session | Profile under load |
| VS-LOW-001 | Error detail leakage | Low | Security | api/speech.py:83,101,109 | str(e) in response | Info disclosure | Generic messages + logged detail | Inspect 400/500 body |
| VS-LOW-002 | `encoding`/`sample_rate` start fields unvalidated | Low | Protocol | speech_socket.py:252,401-402 | Trusted client values | Wrong-rate audio misprocessed | Validate against allowlist | Send bad rate → error |
| VS-LOW-003 | WS history task may drop on shutdown | Low | Backend | speech_socket.py:217-226 | create_task in finally | Lost last turn on disconnect | Await or shield | Kill mid-turn, check DB |
| VS-LOW-004 | Committed artifacts (dist/, .coverage, wavs) | Low | Hygiene | frontend/dist, .coverage, tests/samples | Build outputs in repo | Repo bloat | gitignore + clean | git ls-files |
| VS-LOW-005 | Stale docs (current-state.md Oct 22) | Low | Docs | docs/architecture/current-state.md | Pre-Phase-9 snapshot | Misleading "missing" lists | Refresh or mark superseded | Compare vs code |
| VS-INFO-001 | Linear resampling for uploads | Info | Audio | ai/preprocessing/audio.py:30-47 | np.interp | Slight quality loss | polyphase resampler | SNR test |
| VS-INFO-002 | Double VAD (segmenter + engine) | Info | Audio | speech_socket + sensevoice.py:208 | Redundant gate | Minor CPU waste | Skip engine VAD for WS path | Profile |
| VS-INFO-003 | No token revocation/refresh | Info | Security | security.py | Stateless JWT | 60-min exposure window | jti denylist or shorter TTL | Replay old token |
| VS-INFO-004 | max_tokens=120 truncates long answers | Info | LLM/UX | config.py:88 | Voice-latency tuning | Mid-sentence TTS cuts | Adaptive limit or sentence-boundary stop | Long RAG answer |
