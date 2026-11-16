# 09 — End-to-End Integration Trace

## Workflow A — Auth ✅ VERIFIED
`AuthModal` → `POST /api/auth/{register,login}` → scrypt verify → HS256 JWT → in-memory state → `sendStart{auth_token}` on `/ws/speech` → `verify_access_token` → `user_id` → `history_service` persists per-user. History tab → `GET/DELETE /api/history/*` Bearer → user-scoped queries. **Broken link:** `/api/auth/token` bypass (see 10).

## Workflow B — Recording ✅ VERIFIED
Mic → AudioWorklet PCM16 16k → `sendAudioFrame` binary → server `incoming_queue` → `VADSpeechSegmenter` → utterance bytes. Stop → `flush` → forced utterance.

## Workflow C — Emotion prediction ✅ VERIFIED (utterance-level)
PCM → int16→float32 → `LanguageRouter` (hint only; LID dead) → SenseVoice/IndicConformer `transcribe` → VAD re-check → SpeechResult{transcript,language,emotion tag} → `speech_result` frame → EmotionBadge. **IndicConformer path NOT runtime-verified** (speculative model call).

## Workflow D — Historical analysis ✅ VERIFIED
WS turn → `history_service.record_voice_turn` (finally, threadpool) → Session/Prediction/Transcript/EmotionResult/Message rows → `GET /api/history/sessions` → ConversationHistory renders real data. Emotion metrics partially fabricated (see 05).

## Workflow E — LLM analysis ✅ VERIFIED (design; runtime depends on external llama-server)
Transcript → intent gate → RAG (if knowledge_query) → PromptBuilder → llama.cpp SSE → llm_delta/done → TTS sentences. **External dependency:** llama-server must run separately; graceful degradation to text-only + error frames verified in tests.

## Workflow F — Deployment ⚠️ PARTIAL
Dev: `docker-compose.yml` (untracked) builds `deployment/docker/Dockerfile.backend` (copies backend/,ai/,rag/,alembic) + node frontend + optional llama.cpp profile. Prod: `docker-compose.prod.yml` adds postgres:16 + nginx; `RUN_MIGRATIONS` gate. **Uncommitted**, legacy `docker/` still broken, GPU/memory-light variants present. Not built/run in this audit.

## Missing connections

- No REST endpoint to ingest RAG documents (CLI only) — DocumentManager UI is dead anyway.
- `/api/speech/upload`, `/api/predict` have no frontend caller.
- `Wav2Vec2EmotionEngine` not connected anywhere.
- `LanguageIdentifier`/VoxLingua107 not connected.
- Legacy `/ws/voice` tree fully isolated (only tests/legacy).
