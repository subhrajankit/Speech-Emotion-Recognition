# VoiceSense AI (SenseAI) — Comprehensive Handover & Phase 9 Blueprint

> **Handover Date**: October 27, 2026  
> **Current Git Branch**: `migration/voicesense`  
> **Current Commit**: `c15f732` (`fix(phase-8h): complete reverification, status events, benchmark corrections, and test speedups`)  
> **Test Suite**: `144 passed, 2 warnings in 131s`, **0 failures**  
> **Active OS & Architecture**: Windows 11 Build 26200, Python 3.13.14 (AMD64), PyTorch 2.14.1+cu126, NVIDIA GeForce RTX 2050 (4GB VRAM)

---

## 1. Executive Summary & Repository Identity

**VoiceSense AI** is a fully local, privacy-preserving, multilingual, emotion-aware voice assistant designed to operate within a constrained hardware budget (4GB VRAM, RTX 2050).

### Core Pipeline Flow:
```
Microphone (16kHz PCM16)
   │
   ▼
[Silero VAD] (detects speech start / end boundaries)
   │
   ▼
[Language Routing & Acoustic Perception]
   ├─► English / Multilingual: SenseVoiceSmall (ASR + SER Emotion + AED Acoustic Events)
   └─► Hindi / Indic: IndicConformer-600m (CTC mode; emotion defaults to null)
   │
   ▼
[Intent Router (Hard Gate)]
   ├─► COMMAND branch (deterministic calculator/timer/reminder; bypasses LLM & RAG)
   ├─► KNOWLEDGE branch (multilingual-e5-small + FAISS RAG retrieval; top-k injected)
   └─► CHAT branch (DEFAULT; direct Qwen3 prompt, zero RAG overhead)
   │
   ▼
[LLM Reasoning & Generation]
   └─► Qwen3-1.7B / Qwen3-4B via local llama.cpp server (http://127.0.0.1:8080)
   │
   ▼
[Speech Synthesis (Optional / Feature Gated)]
   └─► Indic Parler-TTS (ai4bharat/indic-parler-tts) via out-of-process worker
```

---

## 2. Hard Invariants & Project Rules (DO NOT BREAK)

1. **One Phase at a Time**: Never start or implement later phases early. Build one phase at a time in strict order.
2. **Localhost Binding Only**: All server processes (`uvicorn`, `llama-server`, `vite`) MUST bind to `127.0.0.1` only. Never expose on `0.0.0.0`.
3. **No Per-Request Model Loading**: Load models once at application startup or via explicit lazy singleton (`load()`). Never reload models per request.
4. **Intent Gate Hard Rule**: RAG and command handling are explicit branches. The default is ALWAYS plain chat. Never run RAG as a silent default on every turn.
5. **ASR/Emotion Isolation**: ASR and Emotion recognition must NOT import or depend on LLM, RAG, or TTS. If LLM, RAG, or TTS fail, transcript and emotion MUST still work.
6. **Zero Raw Audio Persistence**: Raw audio bytes must NEVER be written to disk beyond the immediate request memory buffer. Only transcripts, emotion trajectories, and uploaded RAG docs are persisted.
7. **Git Discipline**: Stage explicit paths only (`git add <file>`). Never run `git add -A` or `git add .`.
8. **Process Management**: Never stop processes by name (no `Stop-Process -Name python`). Only stop exact known PIDs started by the assistant.
9. **Truthfulness**: Label every observation `VERIFIED` (ran in session), `READ` (read from code), or `UNKNOWN`. Never fabricate benchmarks or claim tests pass without running them.

---

## 3. Technology Stack & Virtual Environments

- **Python Virtual Environments**:
  - `.venv`: Main environment (Python 3.13.14). Contains:
    - PyTorch `2.14.1+cu126`, torchaudio `2.11.0+cu126`
    - `funasr` 1.4.16 (SenseVoiceSmall)
    - `onnxruntime` 1.31.0 (Silero VAD)
    - `sentence-transformers` 6.2.0 (`multilingual-e5-small`)
    - `faiss-cpu` / `faiss` 1.15.1
    - `fastapi`, `uvicorn`, `pydantic` v2, `pytest`
  - `.venv-tts`: Dedicated out-of-process TTS environment (prevents dependency conflicts with FunASR). Contains:
    - `parler_tts` 0.2.2, `transformers` 4.46.1, `tokenizers` 0.20.3
- **Frontend**:
  - React 18, TypeScript 5.5, Vite 5.4, Lucide icons.
  - Located in `frontend/`.
- **LLM Server**:
  - `llama-server` running on `http://127.0.0.1:8080`.
  - Model: `Qwen3-1.7B-GGUF` (context: 2048, `--jinja`, `--host 127.0.0.1 --port 8080`).

---

## 4. Phase History & Current Completion Status

| Phase | Description | Status |
|---|---|---|
| **Phase 0** | Baseline audit, architecture freeze, directory alignment | **COMPLETED** |
| **Phase 1** | Client audio capture (React/Vite), WebSocket framing, Silero VAD | **COMPLETED** |
| **Phase 2** | SenseVoiceSmall ASR + SER (Valence/Arousal) + AED acoustic events | **COMPLETED** |
| **Phase 3** | IndicConformer-600m Hindi ASR, language routing heuristic | **COMPLETED** |
| **Phase 4** | Intent Router Hard Gate (Chat vs Knowledge vs Command) | **COMPLETED** |
| **Phase 5** | Prompt builder with emotion conditioning, conversational history budget | **COMPLETED** |
| **Phase 6** | Local Qwen3 streaming integration via `llama.cpp` | **COMPLETED** |
| **Phase 7** | Multilingual RAG with `multilingual-e5-small` + FAISS vectorstore | **COMPLETED** |
| **Phase 8 (a-h)** | Indic Parler-TTS evaluation, isolation worker, Windows SAC fixes, websocket status notifications, latency optimizations | **COMPLETED & VERIFIED** |
| **Phase 9** | **Transport Upgrade: WebTransport (HTTP/3) with WebSocket Fallback & Database History Sync** | **NEXT TARGET** |

---

## 5. Directory Structure & Key Files

```
D:\Capstone Project\NewSenseVoice\
├── ai/
│   ├── inference/
│   │   ├── engine.py               # Base SpeechEngine interface (with load())
│   │   ├── sensevoice.py           # SenseVoiceSmall engine (ASR + SER + AED)
│   │   └── indicconformer.py       # IndicConformer-600m engine (CTC mode)
│   ├── preprocessing/
│   │   └── vad.py                  # Silero VAD ONNX wrapper
│   └── routing/
│       └── language_router.py      # Language hint & code-switch routing
├── backend/
│   └── app/
│       ├── core/
│       │   └── config.py           # Pydantic v2 application settings
│       ├── services/
│       │   ├── speech_service.py   # SpeechService singleton & status callbacks
│       │   ├── llm_service.py      # llama.cpp client, cooldown, thinking filter
│       │   ├── prompt_builder.py   # Prompt engineering & emotion tone resolution
│       │   ├── rag_service.py      # RAG service, vector store loader, intent router
│       │   └── tts_service.py      # Out-of-process TTS client
│       ├── websocket/
│       │   └── speech_socket.py    # Canonical WebSocket endpoint (/ws/speech)
│       └── main.py                 # FastAPI application entrypoint
├── rag/
│   ├── chunking.py                 # Document chunker with overlap
│   ├── embeddings.py               # Multilingual-e5-small embedder wrapper
│   ├── ingestion.py                # CLI ingestion pipeline
│   ├── intent_router.py            # 2-Tier semantic intent gate
│   ├── retriever.py                # FAISS similarity retriever with citations
│   └── vectorstore.py              # FAISSVectorStore + pure-numpy fallback
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Main React voice assistant UI
│   │   ├── services/
│   │   │   ├── api.ts              # REST client (/api/health, /api/history seam)
│   │   │   └── protocol.ts         # WebSocket binary/JSON framing
│   │   ├── stores/
│   │   │   └── conversationStore.ts# Reactive conversation history store
│   │   └── lib/
│   │       └── env.ts              # VITE_API_URL, VITE_WS_URL
│   └── package.json                # Vite + React 18 scripts
├── src/                            # QUARANTINED LEGACY TREE (Do not delete; reference only)
│   ├── backend/
│   │   ├── database/storage.py     # Legacy SQLite storage schema
│   │   └── transport/webtransport.py # Legacy aioquic WebTransport prototype
└── tests/                          # 144 automated tests (all passing)
```

---

## 6. What Phase 9 Is & Exactly What Needs to Be Built

According to `brain/03_ARCHITECTURE.md`, `brain/16_CHANGELOG.md`, `brain/17_DECISIONS.md` (ADR 012), and `frontend/src/stores/conversationStore.ts`, Phase 9 consists of:

### 1. Transport Upgrade: WebTransport (HTTP/3) with Transparent WebSocket Fallback
- **Problem**: On lossy networks or high-throughput audio streaming, TCP Head-of-Line (HoL) blocking can delay control messages (`ping`/`reset`/`barge-in`) and live text tokens.
- **Solution**:
  - Implement WebTransport multi-stream protocol over HTTP/3 (QUIC):
    - **Stream A (Client -> Server)**: Unidirectional 16kHz PCM16 audio chunks feeding Silero VAD segmenter.
    - **Stream B (Bidirectional)**: Low-latency JSON control command stream (`ping`/`pong`, `start`, `stop`, `barge-in`).
    - **Stream C (Server -> Client)**: Unidirectional real-time transcript events, sentence tokens, status updates.
    - **Stream D (Server -> Client)**: Unidirectional binary TTS speech chunks.
    - **Datagrams**: Unreliable, low-overhead UDP datagram channel transmitting real-time affective telemetry (`emotion`, `valence`, `arousal`).
  - **Zero-Friction Fallback**:
    - WebTransport requires TLS 1.3 / QUIC certificates. On `localhost`, browser WebTransport handshakes fail unless custom certificate hashes are provided.
    - The client MUST automatically race/check WebTransport and transparently fallback to `/ws/speech` WebSocket with zero disruption.
  - **Endpoint**:
    - Mount `/api/transport/capabilities` returning supported transports (`websocket`, `webtransport`).
    - Dedicated WebTransport handler (`/wt`).

### 2. Conversation & Emotion History Database Persistence (`/api/history`)
- **Current State**:
  - `frontend/src/stores/conversationStore.ts` and `frontend/src/services/api.ts` have explicit seams: `fetchRemoteHistory()` calling `GET /api/history`.
  - In `brain/04_DATA_MODEL.md` and `docs/architecture/legacy-src.md`:
    - SQLite schema stores: `sessions`, `transcripts` (role, text, language, confidence), and `emotion_history` (primary emotion, valence, arousal, acoustic tags).
    - Raw audio is **NEVER** persisted.
- **Deliverables**:
  - Async SQLite database storage module (`backend/app/database/` using `aiosqlite`).
  - Tables: `sessions`, `utterances`, `emotion_trajectories`.
  - Endpoints:
    - `GET /api/history`: List recent conversation sessions and turns.
    - `GET /api/history/{session_id}`: Detailed turn history with emotion trajectory.
    - `DELETE /api/history/{session_id}`: Clean user data purge.
  - Wire WebSocket turns to asynchronously record transcripts and emotion metadata into the database.
  - Wire frontend `conversationStore` to sync with `/api/history` on mount.

---

## 7. How to Continue Immediately in the Next Claude Session

Provide the other Claude account with this prompt:

```markdown
I am continuing VoiceSense AI from Phase 8h into Phase 9 on branch `migration/voicesense`.
Read `docs/architecture/phase-9-handover.md` and `brain/03_ARCHITECTURE.md`.

Current System State:
- Git branch: `migration/voicesense` at commit `c15f732`.
- All 144 automated tests pass (`pytest`).
- llama-server is running on port 8080 (PID 29280).
- Backend runs on port 8000, Frontend runs on port 5173.
- SAC was turned off by the user on build 26200.9711; whether it can be re-enabled depends on the build; check Windows Security settings.

Follow project rules:
- Stage explicit git paths only.
- Never stop processes by name (only stop specific known PIDs).
- Never persist raw audio.
- Label all findings VERIFIED / READ / UNKNOWN.
- Build Phase 9: Database History Persistence (`/api/history`) and WebTransport multi-stream negotiation with WebSocket fallback.
```
