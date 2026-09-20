# 14 — Production Readiness Checklist

This document is the literal, comprehensive production readiness checklist for the **SenseAI Voice Assistant**, synthesized from all architectural requirements implemented across Phases 1 through 12. Every item must be verified prior to deploying to a production environment.

---

## 1. Speech Perception & Acoustic Modeling
- [ ] **Silero VAD ONNX**: `models/silero_vad.onnx` loaded once at startup; processes 16kHz audio in 512-sample (32ms) frames with silence timeout at 700ms.
- [ ] **SenseVoiceSmall ASR**: Loaded once at startup; provides ASR for supported global languages (EN, ZH, JA, KO, YUE) plus initial SER/AED tags.
- [ ] **IndicConformer-600m**: Loaded once at startup; fallback router activates when SenseVoice confidence is low or language is an Indic tongue (e.g. Hindi).
- [ ] **Hinglish Heuristic**: Code-switch heuristic detects Latin-script Hindi common words with low dual-ASR confidence, tagging `language = "hinglish"`, `script = "latin"`, and `mixed_language = true`.
- [ ] **Zero Model Reloads**: Models are module singletons (`src/backend/models/manager.py`) initialized during application lifespan; zero per-request loading.

---

## 2. Emotion Intelligence & Intent Routing
- [ ] **SER Coordinate Mapping**: Emotion labels mapped to normalized `{ primary, confidence, valence, arousal }` coordinates via structured config lookup.
- [ ] **Lexical Sentiment Fusion**: Fast text polarity check blended with acoustic SER scores to prevent false tone assessments.
- [ ] **Hard Gate Intent Router**: Hard gate in `src/backend/pipeline/intent.py` strictly routes requests to:
  - `"command"`: Deterministic local utility bypass.
  - `"knowledge"`: Dedicated RAG retrieval pass.
  - `"chat"`: Plain Qwen3 generation (explicit default — RAG is NEVER a silent default).
- [ ] **Emotion Storage**: Utterance emotion history persisted to local database (`emotion_history` table) for context tracking.

---

## 3. RAG & Knowledge Grounding
- [ ] **multilingual-e5-small Embeddings**: Initialized once at startup for 384-dimensional vector encoding.
- [ ] **FAISS Vector Index**: Pre-built offline via `scripts/database/build_rag_index.py`; loaded into memory for top-k nearest neighbor search.
- [ ] **Citation & Grounding Enforcement**: Responses originating from the `"knowledge"` branch include explicit doc source citations (`[based on <doc_name>]`).
- [ ] **Offline Indexing Rule**: Vector indexing never runs dynamically during user voice requests.

---

## 4. Streaming Inference & Emotion-Conditioned Speech Synthesis
- [ ] **LLM Streaming Mode**: Qwen3-1.7B called in streaming mode against llama.cpp OpenAI-compatible endpoint.
- [ ] **Sentence Boundary Chunker**: Token stream split on punctuation (`.`, `!`, `?`, and Indic danda `।`) and 25-word max fallback.
- [ ] **Indic Parler-TTS Emotion Styling**: Style descriptions dynamically selected from `EMOTION_STYLE_MAPPING` (e.g. `sad` $\to$ slow, gentle; `angry` $\to$ calm, de-escalating) and synthesized sentence-by-sentence.
- [ ] **Pipelined Audio Stream**: Audio chunks streamed to client immediately as sentences finish, achieving TTFA < 350ms.

---

## 5. Dual-Transport Network Layer
- [ ] **WebTransport (HTTP/3 over QUIC)**: Multi-stream separation active (Stream A audio in, Stream B control, Stream C transcript, Stream D TTS audio, datagrams for telemetry).
- [ ] **Transparent WebSocket Fallback**: Seamless fallback to `ws://127.0.0.1:8000/ws/voice` if WebTransport handshake fails or QUIC UDP 443 is blocked.
- [ ] **Reverse-Proxy Readiness**: TLS 1.3 configured; WebSocket proxy timeouts set to 3600s in reverse proxy.
- [ ] **Handshake Status**: `/api/transport/capabilities` returns supported transport descriptor.

---

## 6. Security & Privacy Hardening
- [ ] **Zero Raw Audio Persistence**: Raw audio PCM bytes are NEVER written to disk; discarded immediately after processing in `finally` blocks.
- [ ] **JWT Handshake Authentication**: HS256 JWT required on `/ws/voice?token=...` and `/wt?token=...` when `REQUIRE_AUTH=true`.
- [ ] **Close Code 1008 Rejection**: Handshakes without valid token rejected with RFC 6455 code 1008 (Policy Violation).
- [ ] **Algorithm Downgrade Protection**: Token verification enforces `alg: "HS256"`; rejects `alg: "none"` attacks.
- [ ] **Session Rate Limiting**:
  - Max 20 utterances per minute per session.
  - Max 30.0 seconds audio duration per utterance (960,000 bytes PCM16).
  - Max 10 MB document upload size.
- [ ] **RAG Document Validation**: Directory traversal blocked (`os.path.realpath`); extensions whitelisted (`.pdf`, `.docx`, `.txt`, `.md`); magic bytes verified.
- [ ] **Interface Binding**: All internal model services and FastAPI processes bind to `127.0.0.1` only. `0.0.0.0` wildcard interfaces forbidden.
- [ ] **Secrets Externalization**: Zero secrets in source code; production secrets stored in `.env` (`chmod 600`).

---

## 7. Observability & Performance Budgets
- [ ] **Structured JSON Telemetry**: Every voice request emits single `"event": "stage_timing"` log line with exact millisecond timings for all 10 stages.
- [ ] **Latency SLA Conformance**: Verified on target hardware (P95 < 500ms total, TTFT < 150ms, TTFA < 350ms).
- [ ] **In-Memory Ring Buffer**: `BenchmarkCollector` active and accessible via `GET /api/benchmark/metrics` and `/api/benchmark/summary`.
- [ ] **Dev Benchmark Dashboard**: Frontend observability tab renders real-time KPI cards, stage latency bars, and request table.
- [ ] **Operational Health Scripts**: `python monitoring/health-checks/check_health.py` reports `ALL SYSTEMS OPERATIONAL (EXIT 0)`.

---

## 8. Docker & Infrastructure Packaging
- [ ] **Backend Dockerfile**: `docker/Dockerfile.backend` builds clean non-root image (`senseai:senseai`) with `libsndfile1` and `ffmpeg`.
- [ ] **Frontend Dockerfile**: `docker/Dockerfile.frontend` uses multi-stage Node build $\to$ hardened Nginx Alpine runtime.
- [ ] **Model Server Decoupling**: `llm-server` service separated in Docker Compose, enabling independent deployment to a dedicated GPU host.
- [ ] **Production Compose Stack**: `docker-compose.prod.yml` defines `llm-server` (CUDA), `backend`, `frontend` (Nginx), and `db` (PostgreSQL 16).
- [ ] **GPU Cloud Cost Accounting**: Operator has reviewed `docs/DEPLOYMENT.md` and budgeted for continuous cloud GPU hosting costs ($150–$1,000+/mo).
- [ ] **Incident Runbooks**:
  - `runbooks/authentication-failure.md` available for auth errors.
  - `runbooks/api-failure.md` available for model/pipeline crashes.
  - `runbooks/deployment-failure.md` available for container/startup errors.
  - `runbooks/rollback.md` available for emergency version rollbacks.
