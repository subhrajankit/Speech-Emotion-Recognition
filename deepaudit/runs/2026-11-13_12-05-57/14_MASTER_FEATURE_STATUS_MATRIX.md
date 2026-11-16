# 14 — Master Feature Status Matrix

Statuses: VERIFIED WORKING / IMPLEMENTED—NOT RUNTIME VERIFIED / PARTIALLY IMPLEMENTED / IMPLEMENTED BUT NOT WIRED / BROKEN / MOCK / NOT IMPLEMENTED / DUPLICATED / DEPRECATED / BLOCKED.

| Feature | FE | BE | DB | ML | Integration | Status | Evidence |
|---|---|---|---|---|---|---|---|
| Mic capture→PCM16 stream | ✅ | ✅ | — | — | ✅ | VERIFIED WORKING | useAudioCapture+speech_socket; tests |
| Server VAD segmentation | — | ✅ | — | ✅(ONNX) | ✅ | VERIFIED WORKING | vad.py+segmenter; 162 tests |
| SenseVoice ASR+SER tags | ✅ badge | ✅ | ✅ | ⚠️heavy | ✅ | IMPLEMENTED—NOT RUNTIME VERIFIED | real weights need torch/funasr absent in CI |
| IndicConformer Indic ASR | ✅ selector | ✅ | ✅ | ❓ | ⚠️ | IMPLEMENTED—NOT RUNTIME VERIFIED | speculative model call; LID dead so only hint-routed |
| Language routing | ✅ | ⚠️ | — | — | ⚠️ | PARTIALLY IMPLEMENTED | Tier2 LID dead; hint+default only |
| Intent hard-gate (chat/RAG/command) | — | ✅ | — | ✅e5 | ✅ | VERIFIED WORKING | rag_service+intent_router; tests |
| RAG retrieval (FAISS) | sources UI | ✅ | index files | ✅e5 | ✅ | VERIFIED WORKING | data/index built; retriever tests |
| RAG doc ingestion via app | dead UI | ❌ | — | — | ❌ | NOT IMPLEMENTED (CLI only) | no /api/rag endpoint; DocumentManager dead |
| Qwen3 LLM chat | ✅ stream UI | ✅ | ✅history | external | ✅ | IMPLEMENTED—NOT RUNTIME VERIFIED | needs llama-server; graceful degrade tested |
| LLM emotion conditioning | — | ✅ | — | — | ✅ | VERIFIED WORKING | prompt_builder |
| Indic Parler-TTS | ✅ player | ✅ | — | ⚠️ | ⚠️ | IMPLEMENTED—NOT RUNTIME VERIFIED | TTS_ENABLED=false default; worker path |
| Auth register/login/JWT | ✅ modal | ✅ | ✅ | — | ✅ | VERIFIED WORKING (except /token hole) | tests+code |
| `/api/auth/token` mint | — | ❌ | — | — | ❌ | BROKEN (security) | auth.py:109 |
| History sessions CRUD | ✅ | ✅ | ✅ | — | ✅ | VERIFIED WORKING | api+store+tests |
| Emotion history metrics | ✅ | ⚠️ | ⚠️ | — | ⚠️ | PARTIALLY IMPLEMENTED | fabricated confidence/valence/arousal |
| Wav2Vec2 emotion engine | — | ❌ | — | ✅research | ❌ | IMPLEMENTED BUT NOT WIRED | ai/inference/emotion.py unused |
| Emotion model training (CREMA-D) | — | — | — | ⚠️ | — | PARTIALLY IMPLEMENTED | smoke run only; pseudo features |
| WebSocket protocol v1 | ✅ | ✅ | — | — | ✅ | VERIFIED WORKING | full duplex verified |
| WebTransport | — | legacy only | — | — | — | NOT IMPLEMENTED (correctly deferred) | src/ only |
| Real-time/continuous SER | — | — | — | — | — | NOT IMPLEMENTED | utterance-batch only |
| Rate limiting | — | ✅ | — | — | ⚠️ | PARTIALLY IMPLEMENTED | in-memory, per-process, REST gaps |
| Health endpoint | ✅ card | ✅ | ✅ | — | ✅ | VERIFIED WORKING | /api/health |
| Analytics dashboard | dead | ❌ | — | — | ❌ | NOT IMPLEMENTED | AnalyticsDashboard unimported |
| Document manager UI | dead | ❌ | — | — | ❌ | NOT IMPLEMENTED | DocumentManager unimported |
| Settings page | dead | ❌ | — | — | ❌ | NOT IMPLEMENTED | SettingsPage unimported |
| Landing page | dead | ❌ | — | — | ❌ | NOT IMPLEMENTED | LandingPage unimported |
| Audio upload REST | ❌no caller | ✅ | — | ✅ | ⚠️ | IMPLEMENTED BUT NOT WIRED (FE) | /api/speech/upload, /api/predict unused by UI |
| Production deploy (PG+nginx) | — | ✅ | ⚠️ | — | ⚠️ | IMPLEMENTED—NOT RUNTIME VERIFIED | compose uncommitted, unbuilt |
| CI pipeline | — | — | — | — | ✅ | VERIFIED WORKING | ci.yml fixed; 162 tests pass |
| Legacy src/ stack | — | ⚠️ | ⚠️ | ⚠️ | ⚠️ | DEPRECATED/QUARANTINED | tests/legacy only |
