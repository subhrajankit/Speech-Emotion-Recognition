# 03 — System Architecture & Component Pipeline

## Project: SenseAI Voice Assistant

---

## 1. End-to-End Pipeline Diagram

```text
+-----------------------------------------------------------------------------------------+
|                                    CLIENT LAYER                                         |
|                                                                                         |
|   +--------------------------+                         +----------------------------+   |
|   |  Microphone & Audio Node |                         | Web Audio API / Speaker    |   |
|   |  (PCM16, 16kHz / 24kHz)  |                         | (Audio Queue & Playback)   |   |
|   +-------------+------------+                         +-------------▲--------------+   |
+-----------------|----------------------------------------------------|------------------+
                  |                                                    |
                  | [Bi-directional WebSocket (MVP) / WebTransport]   | [Audio Stream Chunks]
                  ▼                                                    |
+-----------------------------------------------------------------------------------------+
|                               FASTAPI BACKEND RUNTIME                                   |
|                                                                                         |
|   +------------------------------------------------------------------+                  |
|   | 1. Ingestion & VAD Stage                                         |                  |
|   |    Silero VAD: Detects speech boundary frames & silence trigger  |                  |
|   +-----------------------------+------------------------------------+                  |
|                                 | [Audio Chunk Segment]                                 |
|                                 ▼                                                       |
|   +-----------------------------------------------------------------------------------------+
| 2. Speech Perception & Acoustic Modeling                                                |
|    SenseVoiceSmall: Global ASR (EN, ZH, JA, KO, YUE) + SER + AED                        |
|    IndicConformer-600m: Indic ASR (Hindi & 21 scheduled langs)                          |
|    Hinglish Heuristic: Acoustic & lexical code-switch router                            |
+-------------------------------------------+---------------------------------------------+
                                            | [Transcript & AudioContext]
                                            ▼
+-----------------------------------------------------------------------------------------+
| 3. INTENT ROUTER (HARD GATE — NEVER SILENT RAG, DEFAULT = CHAT)                         |
|    Evaluates explicit rules and triggers EXACTLY ONE branch:                            |
+--------------------+-----------------------------+--------------------------------------+
                     |                             |                                      |
                     | [BRANCH: COMMAND]           | [BRANCH: KNOWLEDGE]                  | [BRANCH: CHAT] (DEFAULT)
                     ▼                             ▼                                      ▼
+-------------------------+  +--------------------------------+  +------------------------+
| 4A. Command Engine      |  | 4B. Knowledge Retrieval (RAG)  |  | 4C. Direct LLM Path    |
|     (Deterministic      |  |     (multilingual-e5-small     |  |     (Qwen3-4B via      |
|      calculator/timer/  |  |      + FAISS vector search)    |  |      llama.cpp server; |
|      reminder handler)  |  |     Top-k doc chunk injection  |  |      warm prompt cache;|
|     * Bypasses LLM/RAG  |  |     * Bypasses plain chat      |  |      zero RAG overhead)|
+------------+------------+  +-------------+------------------+  +-----------+------------+
             |                             |                                 |
             | [Command Text Output]       | [Contextual Prompt + Chunks]    | [Direct Chat Prompt]
             |                             ▼                                 |
             |                   +------------------------------------+      |
             |                   | 5. Reasoning & Generation          |      |
             |                   |    Qwen3-4B via llama.cpp          |      |
             |                   +-----------------+------------------+      |
             |                                     |                         |
             |                                     | [LLM Response Text]     |
             ▼                                     ▼                         ▼
+-----------------------------------------------------------------------------------------+
| 6. Expressive Speech Synthesis                                                          |
|    Indic Parler-TTS: Synthesizes emotion-conditioned audio from branch response         |
                                            | [Audio Stream Chunks]
                                            ▼
```

---

## 2. Component Responsibilities (One-Line Descriptions)

1. **Client Audio Capture (React/Vite)**: Captures raw microphone input, converts it to 16kHz PCM16, and streams it to the server over WebSocket.
2. **Silero VAD**: Filters background noise and identifies exact speech start and end boundaries with low latency.
3. **SenseVoiceSmall**: Transcribes multilingual speech (EN, ZH, JA, KO, YUE) while detecting emotional valence (SER) and acoustic events (AED) in a single pass.
4. **IndicConformer-600m**: Provides high-accuracy transcription for Hindi and all 21 scheduled Indian languages.
5. **Hinglish Heuristic Router**: Dispatches incoming audio between SenseVoiceSmall and IndicConformer based on acoustic and phonetic code-switching cues.
6. **Intent Router**: Enforces an explicit hard gate routing queries to plain conversation, document search, or commands without speculative overhead.
7. **`multilingual-e5-small` Embedder**: Generates dense semantic embeddings for local documents and user queries within RAG flows.
8. **FAISS Vector Index**: Performs sub-millisecond local similarity searches over embedded document chunks.
9. **`llama.cpp` Engine (Qwen3-4B)**: Executes local, low-latency, streaming autoregressive reasoning conditioned on conversation and emotion history.
10. **Indic Parler-TTS**: Synthesizes natural, low-latency audio conditioned on prompt emotion, speaker style, and detected acoustic context.
11. **Session & Emotion Store (SQLite / PostgreSQL)**: Persists session metadata, conversation transcripts, and emotion trajectories with zero audio retention.
12. **Audio Streaming Manager**: Fragments synthesized TTS audio into lightweight binary frames and streams them continuously to the frontend player.
