# 01 — Project Overview

## What is VoiceSense AI?

VoiceSense AI is a **fully local, real-time voice assistant**. You speak into
your microphone, the app transcribes what you said, detects the emotion in your
voice, optionally searches your own uploaded documents, generates a spoken-style
answer with a local AI model, and shows everything on a live dashboard.

The important word is **local**. No audio, transcript, or query ever leaves the
machine. Every model runs on `127.0.0.1` on the user's own computer. This is the
project's main selling point for privacy.

## The problem it solves

1. **Privacy.** Cloud voice assistants (Siri, Alexa, Google Assistant) send your
   voice to a server. VoiceSense keeps everything on-device.
2. **Multilingual + Indian languages.** Most local assistants are English-only.
   VoiceSense is built around Indian-language support (Hindi + 21 scheduled
   languages via IndicConformer, and Indic Parler-TTS for 23 languages).
3. **Emotion awareness.** The assistant detects the emotion in your voice and
   conditions both its text response style and (optionally) its voice on it.
4. **Grounded answers.** A hard-gated RAG pipeline lets the assistant answer
   questions from documents *you* upload — without ever hijacking normal chat.

## What it actually does today (verified against the code)

| Capability | Status | Evidence |
|---|---|---|
| Real-time mic capture → PCM16 16 kHz streaming over WebSocket | **Working** | `frontend/src/hooks/useAudioCapture.ts`, `useWebSocket.ts`, `backend/app/websocket/speech_socket.py` |
| Voice Activity Detection (Silero VAD ONNX) | **Working** | `ai/preprocessing/vad.py` — 512-sample frames, 700 ms silence split |
| English/CJK ASR + emotion + audio events (SenseVoiceSmall) | **Working** | `ai/inference/sensevoice.py` — emits transcript, language, emotion tag, events |
| Hindi/Indic ASR (IndicConformer-600m) | **Working, but disabled by default** | `ai/inference/indicconformer.py` — only when `ASR_ENGLISH_ONLY=false` |
| Intent-gated RAG (multilingual-e5-small + FAISS) | **Working** | `rag/` + `backend/app/services/rag_service.py` — 94% on the project's own 50-example gate eval |
| Local LLM chat (Qwen3-1.7B GGUF via llama.cpp) | **Working** | `backend/app/services/llm_service.py` — streaming, circuit breaker, `<think>` filter |
| JWT auth + user accounts + conversation history | **Working** | `backend/app/api/auth.py`, `api/history.py`, `services/history_service.py` |
| Emotion-conditioned TTS (Indic Parler-TTS) | **Implemented but OFF by default** | `backend/app/services/tts_service.py` — `TTS_ENABLED=false`; benchmarks showed RTF > 1 on the dev GPU |
| Wav2Vec2 SER model (fine-tuned on CREMA-D) | **Scaffold only — NOT a trained model** | `ai/training/train.py` literally saves *random* init weights; `ai/inference/emotion.py` is a placeholder |
| PostgreSQL | **Schema-ready, runtime unverified** | `backend/app/core/database.py` supports it via `DATABASE_URL`; tested only in CI marker `postgres` |
| Docker deployment | **Configs exist, runtime unverified** | `docker-compose.yml`, `deployment/*.yml`; daemon wasn't running during verification |

## Important honesty note for your viva

The repository contains a **speech emotion recognition (SER) training pipeline**
(`ai/training/`, `ai/models/emotion/`) that was designed around a fine-tuned
`facebook/wav2vec2-base` + MLP classifier on the CREMA-D dataset. However, the
code is explicitly marked as a **scaffold**: it generates manifests, splits by
speaker, computes class weights, and saves *untrained random initialization*
weights. The project's *live* emotion detection actually comes from
**SenseVoiceSmall's built-in emotion tags** (`<|HAPPY|>`, `<|SAD|>`, etc.),
not from the wav2vec2 model. If your examiner asks "where is the fine-tuned
Wav2Vec2?", the truthful answer is: "the pipeline and evaluation harness are
built; real CREMA-D training has not yet been run — the checkpoint is marked
`UNTRAINED_RANDOM_INITIALIZATION` in `run_metadata.json`."

## Project journey (from `brain/16_CHANGELOG.md`)

- **Phase 0–1** (Sep 2026): repo scaffolding + minimum voice loop in `src/`
- **Phase 2–3**: Silero VAD streaming, intent router, Hindi routing, Hinglish heuristic
- **Phases 4–8**: migration to the modular `backend/app/` + `ai/` + `rag/`
  architecture; SenseVoice + IndicConformer engines; intent-gated RAG; Qwen3 LLM;
  Indic Parler-TTS integration (disabled); hardening
- **Phase 9**: database, auth, history, rate limiting
- **Phase 10**: frontend integration + real end-to-end verification
- **Phase 11–12**: Docker/deployment configs, documentation and claims audit,
  English-only ASR eval tooling

## Feature list for your viva slide

1. Browser-based microphone capture with AudioWorklet downsampling to 16 kHz PCM16
2. Server-side VAD segmentation (speech start → 700 ms silence → utterance complete)
3. Unified ASR abstraction (`SpeechEngine`) with two real implementations
4. Three-tier language routing: explicit hint → spoken LID → default engine
5. SenseVoiceSmall rich transcription: text + language + discrete emotion + acoustic events in one pass
6. IndicConformer-600m for Hindi and 21 Indic languages (multilingual mode)
7. Hard-gated intent router: chat / knowledge_query / (command branch reserved)
8. RAG: multilingual-e5-small embeddings, FAISS IndexFlatIP, chunk-level citations
9. Local LLM: Qwen3-1.7B Q4_K_M on llama.cpp, SSE streaming, `<think>` stripping, circuit breaker
10. Emotion-aware prompting: detected emotion conditions the system prompt
11. Optional Indic Parler-TTS: sentence-level WAV streaming (disabled by default)
12. Auth (scrypt + HS256 JWT), per-session rate limits, user-isolated history, delete-my-data
13. Privacy: zero raw-audio persistence, transcripts redactable via `STORE_TRANSCRIPTS`
14. React dashboard: voice stage, waveform, transcript/emotion badges, RAG source badges, history panel, settings, a11y live region
15. Honest engineering: typed errors everywhere, fault-isolated persistence, degraded-mode health reporting
