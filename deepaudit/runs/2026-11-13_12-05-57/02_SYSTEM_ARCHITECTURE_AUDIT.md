# 02 — System Architecture Audit

## Actual architecture (verified from source)

```mermaid
flowchart LR
  subgraph Client["React 18 + Vite (frontend/)"]
    MIC[useAudioCapture<br/>AudioWorklet→PCM16 16kHz]
    WS[useWebSocket<br/>protocol v1]
    REST[services/api.ts<br/>auth+history+health]
    STORE[conversationStore]
  end

  subgraph BE["FastAPI backend/app/main.py :8000"]
    WSS["/ws/speech<br/>speech_socket.py"]
    API["/api/health /api/speech/upload<br/>/api/predict /api/auth/* /api/history/*"]
    VAD["SileroVAD + VADSpeechSegmenter<br/>ai/preprocessing/vad.py"]
    SVC["SpeechService<br/>services/speech_service.py"]
    ROUTER["LanguageRouter<br/>ai/routing (hint→LID→default)"]
    ENG1["SenseVoiceSmall<br/>funasr AutoModel"]
    ENG2["IndicConformer-600m<br/>transformers AutoModel trust_remote_code"]
    RGATE["rag/intent_router.py<br/>regex+e5 exemplars"]
    FAISS[("FAISS index<br/>data/index")]
    LLM["llm_service.py<br/>→ llama.cpp :8080 (external)"]
    TTS["tts_service.py<br/>Parler-TTS / .venv-tts worker"]
    HIST["history_service.py<br/>threadpool → SQLAlchemy"]
  end

  subgraph EXT["External processes/models"]
    LLMSRV["llama-server<br/>Qwen3-1.7B GGUF"]
    HF[("HF/ModelScope cache<br/>SenseVoice, IndicConformer, e5-small")]
  end

  subgraph DB[("SQLite dev.db / PG prod")]
    T1[(users sessions predictions<br/>transcripts emotion_results<br/>messages model_versions)]
  end

  MIC -->|binary PCM16 frames| WS
  WS --> VAD --> SVC --> ROUTER
  ROUTER --> ENG1 & ENG2
  ENG1 & ENG2 -->|SpeechResult| WSS
  WSS --> RGATE -->|knowledge_query| FAISS
  WSS --> LLM --> LLMSRV
  LLM --> TTS
  WSS --> HIST --> DB
  API --> DB
  REST --> API
```

## Intended vs actual

`brain/03_ARCHITECTURE.md` and `docs/architecture/target-architecture.md` describe this same pipeline — the canonical tree **does** implement it. Deltas:

| Intended | Actual | Status |
|---|---|---|
| LID tier routes Hindi→IndicConformer automatically | `lid_detector=None` always; VoxLingua107 weights present but no detector class | MISSING COMPONENT |
| Emotion engine (Wav2Vec2 fine-tune) | SenseVoice `<|EMO|>` tags only; `ai/inference/emotion.py` unwired | NOT WIRED |
| WebTransport Phase 9 | Deferred; only legacy `/wt` descriptor in `src/` | CORRECTLY DEFERRED |
| `tts/` top-level dir | TTS inside `backend/app/services/` | COSMETIC |
| Production PostgreSQL | Compose provisions PG; `DATABASE_URL` supports it; unverified live | PARTIAL |

## Architectural problems

1. **Duplicate trees.** `src/backend`+`src/frontend` remain fully populated. Isolation is enforced by convention (`scripts/ci/check_import_isolation.py`) and tests, not by deletion. Risk: contributors/imports accidentally revive legacy paths; two `requirements.txt`, two Docker dirs.
2. **Speculative IndicConformer adapter.** `indicconformer.py` guesses at the HF remote-code call signature with nested try/except fallbacks (`model(wav, target_lang, decoder_type)` → `transcribe(...)` → `model(tensor)`). If the real signature differs, inference silently produces wrong/empty output — needs runtime verification.
3. **Per-process state.** Rate limiters, LLM cooldown, model-version cache are in-memory singletons — fine for `--workers 1` (enforced in compose) but silently incorrect otherwise.
4. **Circular-risk avoided:** `history_service` imports settings+models only; `speech_socket` imports services; services don't import the socket — clean DAG.
5. **Unnecessary complexity:** `src/` legacy tree (~60 files) + duplicate `database/migrations|schemas` SQL + `docker/` legacy Dockerfiles + `src/frontend` — all dead weight.

## Missing components

- `LanguageIdentifier` implementation (VoxLingua107 weights already on disk).
- Wiring of `Wav2Vec2EmotionEngine` into `SpeechService`/`speech_socket` (or explicit decision that SenseVoice tags are the production SER).
- Frontend consumers for `AnalyticsDashboard`, `DocumentManager`, `SettingsPage`, `LandingPage`, `Header`, `VoiceConsole` (or deletion).
- API endpoint for RAG document upload/management — `DocumentManager.tsx` exists but **no `/api/rag` or documents endpoint exists** in `backend/app/api/`. Ingestion is CLI-only (`python -m rag.ingestion`). **RAG documents cannot be added via the app.**
