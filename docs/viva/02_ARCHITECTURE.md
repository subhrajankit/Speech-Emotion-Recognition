# 02 — System Architecture

## Big picture

VoiceSense AI is a **three-tier local web application**:

```text
┌─────────────────────────────────────────────────────────────────┐
│ CLIENT  — React 18 + TypeScript + Vite (frontend/)              │
│   Microphone → AudioWorklet → PCM16 16kHz → WebSocket binary    │
│   Receives: speech_result, llm_delta, tts_chunk, history, etc.  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ ws://127.0.0.1:8000/ws/speech
                               │ + REST /api/* on same port
┌──────────────────────────────▼──────────────────────────────────┐
│ BACKEND — FastAPI (backend/app/)                                │
│   api/ routers · websocket/speech_socket.py · services/ ·       │
│   core/ (config, db, security, rate_limiter) · models/ (ORM)    │
└───────┬──────────────┬──────────────┬──────────────┬────────────┘
        │              │              │              │
   ┌────▼────┐   ┌─────▼─────┐  ┌─────▼──────┐  ┌────▼─────────┐
   │ ai/     │   │ rag/      │  │ LLM        │  │ TTS          │
   │ VAD +   │   │ e5-small  │  │ Qwen3-1.7B │  │ Indic Parler │
   │ ASR +   │   │ + FAISS   │  │ via        │  │ (disabled)   │
   │ router  │   │           │  │ llama.cpp  │  │              │
   └─────────┘   └───────────┘  │ :8080      │  └──────────────┘
                                └────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ DATA — SQLite dev.db (dev) → PostgreSQL (prod target)           │
│   users, sessions, predictions, transcripts, emotion_results,   │
│   messages, model_versions  — NO raw audio, ever                │
└─────────────────────────────────────────────────────────────────┘
```

## The per-utterance pipeline (the heart of the project)

This is what happens for **one spoken turn**, in exact order:

```text
1. CAPTURE     Browser mic → AudioWorklet resamples to 16kHz PCM16
               → binary WebSocket frames

2. VAD SEGMENT ai/preprocessing/vad.py — VADSpeechSegmenter
               Silero VAD scores each 512-sample (32ms) frame.
               speech_start → keep frames → 700ms silence →
               emit ONE complete utterance (with 250ms pre-padding
               so the first consonant isn't clipped).

3. ROUTE       backend/app/services/speech_service.py
               English-only MVP (default): everything → SenseVoice.
               Multilingual mode: LanguageRouter 3 tiers —
               explicit language_hint → spoken LID (if enabled) →
               default SenseVoice.

4. PERCEIVE    ai/inference/sensevoice.py OR indicconformer.py
               SenseVoiceSmall returns ONE rich string with tags:
               <|en|><|HAPPY|><|Laughter|> actual words ...
               parse_sensevoice_output() splits it into
               SpeechResult{transcript, language, emotion,
               audio_events, confidence=null}.
               IndicConformer returns text only, emotion=null
               (it has no SER capability — by design).

5. EMIT FIRST  speech_result JSON is sent to the client BEFORE
               any LLM/RAG/DB work. If everything downstream dies,
               the user still sees their transcript+emotion.
               (This is the project's key reliability invariant.)

6. INTENT GATE rag/intent_router.py — runs on the transcript
               Tier1: ~20 regex rules (EN/Devanagari/Hinglish)
               Tier2: cosine similarity vs knowledge/chat exemplars
               Tier3: default = chat  (RAG NEVER runs on chat)

7. REASON      Two paths converge on the same LLM call:
               chat        → plain conversation history
               knowledge   → top-3 FAISS chunks injected as
                             "grounded context" + citation rules
               → Qwen3-1.7B on llama.cpp :8080, SSE streaming,
               <think> tags stripped, emotion-conditioned system
               prompt from prompt_builder.py.

8. STREAM OUT  llm_delta frames (token-by-token) → llm_done{text}
               → optional rag_sources citations shown as badges.

9. TTS (opt.)  If TTS_ENABLED=true: clean_tts_text() strips
               markdown/emoji/citations, split_sentences() chunks
               on .!?, each sentence synthesized by Indic Parler-TTS
               → tts_chunk header + binary WAV → tts_done.

10. PERSIST    history_service.record_voice_turn() in a background
               thread AFTER llm_done: session + prediction +
               transcript + emotion_result + messages rows.
               Anonymous users (no JWT) persist NOTHING.
               DB failure is logged and swallowed — never breaks
               the voice path.
```

## Why this order matters (viva talking points)

- **Perception-first isolation**: `speech_result` is emitted before LLM/RAG/TTS.
  Proven by test `test_tts_failure_cannot_break_asr` style isolation checks and
  the `test_isolation.py` AST scan (0 imports of llm/rag/tts inside `ai/`).
- **Hard intent gate**: chat queries make **zero** FAISS calls — verified by a
  call-spy test. RAG is opt-in by semantic evidence, not a silent default.
- **No fabricated confidence**: SenseVoice emits greedy tokens, not calibrated
  probabilities, so `confidence` stays `null` rather than inventing a number.
- **No fabricated emotion for Hindi**: IndicConformer outputs `emotion: null`
  because it genuinely has no emotion head.
- **In-frame auth**: JWT travels inside the `start` message, never in the URL
  (avoids token leakage into logs/history).

## Module boundaries (the "clean architecture" story)

| Layer | Folder | May import | Must NOT import |
|---|---|---|---|
| Perception | `ai/` | numpy, soundfile, onnxruntime, torch/funasr/nemo | LLM, RAG, TTS, FastAPI |
| Retrieval | `rag/` | sentence-transformers, faiss/numpy | FastAPI, LLM, TTS |
| Orchestration | `backend/app/` | everything above + sqlalchemy | — |
| UI | `frontend/` | React, WebSocket API | anything server-side |

Enforced by `scripts/ci/check_import_isolation.py` in CI.

## Legacy code (`src/`)

`src/backend/` + `src/frontend/` are the **original Phase 1–3 monolith**
(`/ws/voice` endpoint, `model_manager`, direct SQLite). It still exists in the
repo for history but is **quarantined**: nothing in `backend/app/` imports it,
tests under `tests/legacy/` are excluded by default (`--ignore=tests/legacy`
in `pyproject.toml`), and it is scheduled for removal. If asked "why two
backends?": the project migrated to a modular architecture mid-capstone; the
old tree was kept until the new one was fully verified, then frozen.
