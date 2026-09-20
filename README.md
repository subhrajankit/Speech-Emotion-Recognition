# SenseAI Voice Assistant

SenseAI is an open-source, multilingual, emotion-aware, and 100% locally executed voice assistant designed for private, low-latency, conversational voice intelligence.

---

## Key Features

- **100% Local Inference**: Zero dependency on third-party cloud APIs (OpenAI, Google Cloud, Azure, ElevenLabs). Private by design.
- **Multilingual & Indic Language Coverage**:
  - Global languages (English, Mandarin, Cantonese, Japanese, Korean) via SenseVoiceSmall.
  - Hindi + 21 official Indian languages via AI4Bharat IndicConformer-600m with Hinglish heuristic routing.
- **Emotion & Acoustic Event Awareness**: Real-time speech emotion recognition (SER) and audio event detection (AED) inform the LLM and shape expressive vocal feedback.
- **Expressive Emotion-Styled TTS**: Indic Parler-TTS synthesizes natural speech conditioned on detected and generated emotional nuance.
- **Intent-Gated RAG**: Hard-gated routing ensures RAG (multilingual-e5-small + FAISS) and tool execution only trigger on explicit intent, keeping plain chat ultra-responsive.
- **Real-Time Streaming**: Low-latency bi-directional streaming over WebSocket (MVP) with planned WebTransport / HTTP/3 migration.

---

## Architecture Pipeline

```text
[ Microphone Audio ]
         │
         ▼
  [ Silero VAD ]
         │ (speech segments)
         ▼
[ ASR + SER + AED ] ──► SenseVoiceSmall (Global + SER + AED)
         │          ──► IndicConformer-600m (Indic/Hindi + Hinglish heuristic)
         ▼
 [ Intent Router ]  ──► (Hard Gate: Plain Chat | RAG | Command)
         │
         ├── Plain Chat ──────────────────────────┐
         ├── RAG (multilingual-e5-small + FAISS) ──┤
         └── Command Engine ──────────────────────┤
                                                  │
                                                  ▼
                                      [ Qwen3-4B via llama.cpp ] (Streaming)
                                                  │
                                                  ▼
                                    [ Indic Parler-TTS ] (Emotion-Styled)
                                                  │
                                                  ▼
                                      [ Browser Audio Stream ]
```

---

## Tech Stack

- **Frontend**: React 18+, TypeScript, Vite
- **Backend**: Python 3.11+, FastAPI, Uvicorn, WebSockets
- **Speech & Audio**: Silero VAD, SenseVoiceSmall, AI4Bharat IndicConformer-600m, Indic Parler-TTS
- **Language Model**: Qwen3-4B via llama.cpp server (bound to `127.0.0.1`)
- **Embeddings & Vector Search**: `intfloat/multilingual-e5-small`, FAISS
- **Storage**: SQLite (Dev) → PostgreSQL (Prod)
- **Containerization**: Docker, Docker Compose

---

## Documentation

Project documentation and design specifications are maintained in the [`brain/`](./brain/) directory:
- [01_PRD.md](./brain/01_PRD.md) - Product Requirements Document
- [02_TRD.md](./brain/02_TRD.md) - Technical Requirements Document
- [03_ARCHITECTURE.md](./brain/03_ARCHITECTURE.md) - System Architecture & Component Responsibilities
- [10_SECURITY.md](./brain/10_SECURITY.md) - Security & Privacy Constraints
- [16_CHANGELOG.md](./brain/16_CHANGELOG.md) - Phase Development Log
- [17_DECISIONS.md](./brain/17_DECISIONS.md) - Architectural Decision Records (ADR)

---

## Optional Cloud LLM Comparison (Gemini 3 Flash)

SenseAI includes an **optional, opt-in** cloud LLM provider for comparison and benchmarking purposes:
- **Default (Local)**: Local Qwen3-1.7B via `llama.cpp` — 100% offline, private, zero external API calls.
- **Optional Cloud Mode**: Google Gemini 3 Flash (`LLM_PROVIDER=cloud`) via Google AI Studio API.

> [!WARNING]
> **Explicit Privacy Exception**: Enabling cloud mode sends spoken transcripts, emotional state, and linguistic metadata to Google's Gemini API. This is an explicit, opt-in feature for side-by-side demo evaluation and requires a separate `GEMINI_API_KEY` from Google AI Studio.

---

## License

MIT License. See [LICENSE](./LICENSE) for details.

