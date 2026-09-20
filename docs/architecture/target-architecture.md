# VoiceSense AI — Target Architecture

This document describes the **target** design, not the current state.
Adapt it to the existing code. Do not blindly recreate it, and do not delete
working code just to match this layout. The audit of what actually exists
lives in `docs/architecture/current-state.md`.

## Target architecture

```text
Frontend
    ↓
WebSocket
    ↓
FastAPI
    ↓
Audio Pipeline
    ↓
Silero VAD
    ↓
Language Router
    ↓
 ┌─────────────────────────────┐
 │                             │
SenseVoiceSmall          IndicConformer
 │                       │
Global languages         Hindi/Indic ASR
 │                       │
 └──────────────┬──────────────┘
                ↓
        Unified Speech Result
                ↓
       ┌────────┼────────┐
       ↓        ↓        ↓
   Transcript Emotion Language
                ↓
          Intent Router
                ↓
      ┌─────────┴─────────┐
      ↓                   ↓
   Plain Chat             RAG
      │                   │
      └─────────┬─────────┘
                ↓
             Qwen3
                ↓
      Indic Parler-TTS
                ↓
        Browser Audio
```

### Architecture rules

- ASR and speech emotion recognition must NOT depend on Qwen3.
  If Qwen3 fails, ASR, emotion detection, and the transcript must still work.
- RAG is intent-gated. Do NOT perform RAG for every user utterance.
- TTS failure must not break ASR/SER.
- Cloud Gemini is optional. The primary architecture must work locally.
- Hindi ASR and Hindi emotion recognition are separate concerns.
- Keep the system modular so models can be replaced independently.

## Target repository structure

```text
frontend/
    public/
    src/
        app/
        components/
            audio/
            emotion/
            transcript/
            dashboard/
            ui/
        hooks/
        lib/
        services/
        types/
        stores/
    package.json

backend/
    app/
        main.py

        api/
            auth.py
            speech.py
            prediction.py
            history.py
            health.py

        core/
            config.py
            security.py
            logging.py

        models/
            user.py
            session.py
            prediction.py

        schemas/
            auth.py
            speech.py
            prediction.py

        services/
            speech_service.py
            emotion_service.py
            llm_service.py
            rag_service.py
            tts_service.py

        websocket/
            speech_socket.py

    tests/
    requirements.txt

ai/
    models/
        sensevoice/
        indicconformer/
        emotion/

    preprocessing/
        audio.py
        vad.py
        normalization.py

    routing/
        language_router.py

    inference/
        sensevoice.py
        indicconformer.py
        emotion.py

    training/
        datasets/
        preprocessing/
        train.py
        evaluate.py
        config/

    notebooks/

rag/
    documents/
    ingestion/
    embeddings/
    retrieval/
    vectorstore/

tts/

data/
    raw/
    processed/
    metadata/

models/
    checkpoints/
    quantized/

scripts/
    setup.sh
    download_models.py
    prepare_dataset.py
    health_check.py

tests/
    backend/
    ai/
    integration/

docs/
    architecture/
    api/
    dataset/
    training/
    deployment/

deployment/
    docker/
    docker-compose.dev.yml
    docker-compose.prod.yml

.env.example
.gitignore
LICENSE
README.md
docker-compose.yml
```
