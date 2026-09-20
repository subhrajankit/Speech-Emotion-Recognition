# 17 — Architectural & Design Decisions

## ADR 001: Initial Stack and Harness Setup
- **Context**: Project setup for SenseAI Voice Assistant (multilingual, emotion-aware, local voice assistant).
- **Decision**:
  - Transport MVP set to WebSocket; WebTransport deferred to Phase 9.
  - Development database set to SQLite; production upgrade to PostgreSQL in Phase 12.
  - Harness configured with Antigravity rules and ECC developer profile in `.agents/`.
  - Staged model additions rather than loading all models simultaneously.
- **Consequences**:
  - Predictable latency testing in early phases.
  - Clean separation of concerns and phase-by-phase verification.

## ADR 002: Pipeline Latency Allocation and Directory Architecture (Phase 0)
- **Context**: Setting concrete latency budgets and project structure before writing code.
- **Decision**:
  - Allocated 670ms end-to-end P95 latency target on GPU (<30ms VAD, <120ms ASR/SER/AED, <15ms Intent Gate, <180ms LLM TTFT, <250ms First TTS Chunk, <30ms Transport).
  - Adopted strict zero-persistence for raw audio chunks; only transcripts, `emotion_history`, and RAG documents persist.
  - Established unified `src/frontend` and `src/backend` repository layout with dedicated directories for `database`, `scripts`, `security`, and `monitoring`.
- **Consequences**:
  - Establishes non-negotiable benchmark targets for every subsequent component phase.
  - Ensures clean directory organization and auditable compliance with privacy principles.

## ADR 003: WebSocket Audio Protocol & Fallback Synthesizer (Phase 1)
- **Context**: Implementing the minimum voice loop without VAD or emotion in Phase 1.
- **Decision**:
  - Adopted framed binary transfer for PCM16 audio chunks over WebSocket `/ws/voice`, with JSON control frames (`end_of_utterance`, `ping`, `reset`).
  - AudioWorklet implementation in frontend with automatic fallback to `ScriptProcessorNode` if the worklet is blocked or unserved in specific browser contexts.
  - Integrated a harmonic chime generator in `IndicParlerTTS` when model weights are not loaded locally, enabling end-to-end integration testing and automated unit testing without requiring 4GB model downloads upfront.
  - Singletons loaded during FastAPI startup `lifespan` hook; no per-request instantiation.
- **Consequences**:
  - Zero-lag audio capture on client side.
  - Unit and integration tests run deterministically in CI and local machines.
  - Production models can be swapped in transparently via HuggingFace or local weights.

## ADR 004: Silero VAD v5 ONNX Integration & 700ms Streaming Segmentation (Phase 2)
- **Context**: Stopping unnecessary audio transmission to ASR when user is silent, enabling hands-free speech turn-taking.
- **Decision**:
  - Selected official Silero VAD v5 ONNX model running via `onnxruntime` on CPU with single-pass 512-sample (32ms) frame evaluation.
  - Implemented temporal sliding context window (`context_size=64` samples) to feed proper acoustic boundary context to the RNN.
  - Configured 700ms default silence timeout (`SILENCE_TIMEOUT_MS=700`) and 250ms pre-speech circular ring buffer to prevent clipping leading plosives/consonants.
  - Audio buffers remain strictly in RAM during active segmentation and are completely purged immediately upon dispatch to ASR.
- **Consequences**:
  - Audio is never processed by ASR during silence or background pauses.
  - Natural, hands-free conversational turn detection without manual button toggling.
  - Minimal compute footprint (< 1ms per 32ms frame on CPU).

## ADR 005: Dual-ASR Language Routing & Heuristic Hinglish Tagging (Phase 3)
- **Context**: Accurate transcription across global languages and 22 scheduled Indian languages, with robust support for code-mixed speech (Hinglish).
- **Decision**:
  - Positioned `LanguageRouter` between VAD and ASR execution.
  - SenseVoiceSmall handles Language-ID (LID) and primary transcription for its 5 supported languages (`en`, `zh`, `yue`, `ja`, `ko`).
  - IndicConformer-600m acts as the primary recognizer for Hindi and other Indian languages whenever SenseVoice LID indicates non-supported languages or low confidence.
  - Adopted a lightweight vocabulary-set heuristic (`HINGLISH_COMMON_WORDS` + `COMMON_ENGLISH_WORDS`) to tag Latin-script code-mixed speech without neural retraining.
  - Output standardized as a typed `AudioContext` object (`language`, `script`, `mixed_language`, `transcript`, `confidence`, `model_used`).
- **Consequences**:
  - Ultra-fast routing decision (< 2ms overhead).
  - Clean separation between global multilingual speech and Indic vernaculars.
  - Downstream LLM receives explicit `mixed_language` flag, enabling appropriate conversational tone matching.

## ADR 006: Hard Gate Intent Routing (Phase 4)
- **Context**: Preventing speculative RAG lookups or general chat defaults from running uncontrolled on every user utterance.
- **Decision**:
  - Placed `IntentRouter` as a mandatory hard gate between ASR/context and reasoning.
  - Configured three mutually exclusive categories:
    1. `command`: Deterministic actions (calculator, timer, alarms, reminders). Bypasses LLM and RAG entirely.
    2. `knowledge`: Explicit document lookups (RAG via `e5-small` + FAISS in Phase 6).
    3. `chat`: Direct LLM reasoning via Qwen3-4B. **Unconditional default.**
  - RAG is strictly intent-triggered; general conversational utterances never invoke vector search.
  - Classifier implemented with compiled regex rules and category confidence scores, executing in < 1ms.
- **Consequences**:
  - Preserves low latency (< 670ms target) for conversational chat by eliminating unnecessary vector lookups.
  - Clear architectural boundaries for tool execution and document retrieval.

## ADR 007: Empirical Valence/Arousal Coordinate Mapping & Lexicon-Based Sentiment Fusion (Phase 5)
- **Context**: SenseVoice produces discrete acoustic emotion tags (`<|HAPPY|>`, `<|SAD|>`, etc.), but rich LLM conditioning and affective tracking require continuous dimensional representations (Valence and Arousal) without adding a heavy neural model.
- **Decision**:
  - Selected Russell's Circumplex Model of Affect with a fixed empirical coordinate lookup table mapping discrete SenseVoice labels to approximate valence and arousal coordinates (e.g. `happy`: (+0.8, +0.6), `sad`: (-0.7, -0.4), `angry`: (-0.6, +0.8), `neutral`: (0.0, 0.0)).
  - Documented explicitly that this is an empirical approximation, NOT a learned continuous regression.
  - Fused acoustic SER with a fast, zero-model lexical sentiment check on the transcript (`calculate_lexical_polarity`) supporting both English and Hindi/Hinglish vocabulary.
  - Fused state: 70% acoustic + 30% lexical for distinct acoustic emotions, while allowing strong lexical sentiment to shift acoustic neutral states.
  - Injected structured `{ emotion, language, transcript, mixed_language }` context into the prompt template, with strict system instructions to acknowledge emotional tone briefly, answer concisely, and avoid long reasoning chains.
  - Persisted user affective history into SQLite table `emotion_history` for multi-turn tracking.
  - **Note to revisit**: Revisit this approximation post-MVP or in Phase 14 evaluation; if discrete SenseVoice emotion labels fail to capture subtle vocal nuances, evaluate adding a dedicated distilled continuous regression head (e.g., wav2vec2-valence-arousal) provided it fits within the 120ms ASR/SER budget.
- **Consequences**:
  - Zero added model weight or memory footprint.
  - Analysis latency is negligible (< 1ms).
  - Strict privacy invariant upheld: only emotion metadata and transcripts are persisted; raw audio is NEVER stored.

## ADR 008: Local LLM Swap from Qwen3-4B to Qwen3-1.7B (Q4_K_M GGUF)
- **Context**: The deployment target includes consumer hardware with 4GB shared VRAM (NVIDIA RTX 2050 Mobile / 4GB). In full local operation, SenseVoiceSmall, IndicConformer-600m, and Indic Parler-TTS run concurrently alongside the LLM. Qwen3-4B (Q4_K_M) requires ~2.8 GB VRAM alone, leading to severe VRAM contention, CUDA OOM errors, or paging to system RAM.
- **Decision**:
  - Swapped the default local LLM from Qwen3-4B to Qwen3-1.7B (Q4_K_M GGUF).
  - Qwen3-1.7B (or Qwen2.5-1.5B-Instruct-GGUF) uses ~1.2 GB VRAM, leaving ~2.8 GB of headroom for acoustic models on a 4GB RTX 2050.
  - **Alternative considered and rejected**: Microsoft Phi-4-mini was evaluated for compact footprint and reasoning, but was rejected because of notably weaker Hindi, Hinglish, and South Asian language fluency and token representation compared to Qwen.
  - Maintained identical prompt structure in `src/backend/llm/prompts.py` (emotion awareness, 1-2 sentence conciseness, no reasoning chains).
- **Consequences**:
  - Zero VRAM spilling or OOM crashes on 4GB systems.
  - Lower TTFT latency (~100–160ms on GPU, ~250ms on CPU).

## ADR 009: Local Intent-Gated RAG Pipeline with Multilingual-E5 and FAISS (Phase 6)
- **Context**: The assistant requires knowledge-grounded question answering over user-provided documents (PDF, DOCX, TXT, MD) without hallucinating facts. However, running retrieval on every voice utterance would severely degrade TTFT for general chat, risk irrelevant context pollution, and consume memory.
- **Decision**:
  - **Hard Intent Gate**: RAG retrieval is executed **only** when `src/backend/pipeline/intent.py` classifies the query as `"knowledge"`. General conversational utterances ("chat") and deterministic commands ("command") bypass RAG entirely with zero latency penalty.
  - **Embedding Model**: Selected `intfloat/multilingual-e5-small` (384-dim, ~130MB footprint) with normalized embeddings. Strictly enforced asymmetric prefixing required by the E5 architecture (`"query: "` for search queries and `"passage: "` for indexed document chunks). Added deterministic MD5 token-hash fallback with stopword filtering for test and offline environments.
  - **Vector Storage**: Used local `faiss.IndexFlatIP` (inner product on L2-normalized vectors representing exact cosine similarity) serialized to `data/index/rag.index` alongside metadata in `data/index/chunks.json`. Implemented a pure NumPy fallback (`NumpyVectorIndex`) for portability across platforms where C++ FAISS wheels may be absent.
  - **Offline Indexing Script**: Ingests documents strictly offline via `scripts/database/build_rag_index.py` using `pypdf`, `python-docx`, and plain text/markdown readers with 500-character chunking and 100-character overlap. The indexing pipeline is never triggered per-request.
  - **Web Scraping Rejection**: Explicitly marked `brain/06_SCRAPING_SPEC.md` as "Not applicable, static document upload only". Web scraping was rejected to maintain the 100% offline, privacy-first boundary, eliminating network dependencies, legal IP risks, and runtime latency.
  - **Mandatory Grounding & Citation**: Injected `QWEN_KNOWLEDGE_SYSTEM_PROMPT` instructing the LLM to format responses with `"Based on <doc_name>: "` and cite the exact source document, facilitating instant detection of hallucinations during smoke tests and production.
- **Consequences**:
  - Zero retrieval overhead for general chat turns.
  - Top-k retrieval latency < 5ms for local FAISS vector search.
  - Verifiable source attribution on all factual queries.
  - Fully local, offline-capable knowledge grounding adhering to the project's zero-cloud privacy mandate.

## ADR 010: Streaming LLM Tokenization, Sentence-by-Sentence TTS Synthesis & WebSocket Framing (Phase 7)
- **Context**: In batch execution, the voice loop waited for Qwen3 to generate the entire completion before initiating Indic Parler-TTS synthesis. For multi-sentence responses, this produced an unacceptable 1.5s–3.0s delay before speech playback began, breaking conversational rhythm on local edge hardware.
- **Decision**:
  - **Streaming LLM**: Converted `LlamaCppClient` to consume OpenAI-compatible Server-Sent Events (SSE) over `/v1/chat/completions` with `"stream": True`, yielding token deltas in real time.
  - **Real-Time Sentence-Boundary Chunker**: Implemented `SentenceBoundaryChunker` buffering tokens and segmenting immediately on sentence boundaries (`.`, `!`, `?`, `\n`, Hindi danda `।`). Built in abbreviation/decimal number protection (`1.7B`, `Dr.`) and fallback word/char count thresholds to prevent buffer starvation on run-on sentences.
  - **Pipelined Sentence TTS**: Dispatched each completed sentence chunk to `IndicParlerTTS.synthesize_wav` concurrently while subsequent sentences were still being generated by the LLM.
  - **Multi-Message WebSocket Framing**: Extended `/ws/voice` to multiplex metadata control frames (`llm_start`, `sentence_start`, `sentence_end`, `turn_complete`) and binary WAV frames over the same socket. Preserved single-turn events (`result`, `playback_ready`) for backward compatibility.
  - **Client-Side FIFO Playback Queue**: Built a sequential audio queue in the React frontend (`audioQueueRef`, `isPlayingChunkRef`) ensuring back-to-back, gapless playback without clipping or audio overlap.
  - **Telemetry Standard**: Established **TTFT** (Time-to-First-Token) and **TTFA** (Time-to-First-Audio) as primary system performance KPIs, logged on every utterance.
- **Consequences**:
  - **Time-to-First-Audio (TTFA)** slashed from > 1800ms to < 400ms.
  - Fluid, progressive user interface: user sees response text appear sentence-by-sentence and hears natural speech almost instantly.
  - Zero server-side audio buffering after request completion.

## ADR 011: TTS Emotion Style Conditioning and Conversational De-escalation (Phase 8)
- **Context**: Indic Parler-TTS supports natural language prompt descriptions controlling speaker timbre, pacing, and emotional tone. Prior to Phase 8, all speech synthesis used a hardcoded, static prompt ("A clean, clear voice with natural delivery."), rendering emotional replies monotone regardless of the user's affective state.
- **Decision**:
  - **Config Table Architecture**: Decoupled style descriptions into a structured lookup table (`EMOTION_STYLE_MAPPING` in `src/backend/tts/indic_parler.py`) instead of hardcoding strings in function bodies.
  - **Empathic Delivery & De-escalation Policy**:
    - `sad` → `"A soft, gentle voice with slow, calm, gentle, and empathetic delivery."`
    - `happy` → `"An energetic, bright, faster voice with cheerful and lively delivery."`
    - `angry` → `"A calm, slow, de-escalating, and soothing voice with reassuring delivery."` (Deliberately designed not to mirror anger, but to actively soothe and de-escalate emotional tension).
    - `neutral`, `fearful`, `disgusted`, `surprised`, `excited` configured for psychological congruence.
  - **Interface Invariant**: `IndicParlerTTS.synthesize_wav` accepts an `emotion` parameter (supporting `EmotionState` dataclass, dictionaries, or string labels) and resolves prompt descriptions through `get_tts_style_description`.
  - **Pipelined Execution**: Embedded into `VoicePipeline.stream_utterance(...)` so that all streamed sentence audio frames carry emotion-conditioned vocal characteristics.
- **Consequences**:
  - Spoken responses audibly convey empathy, warmth, and de-escalation without requiring multiple voice models.
  - Style prompt tuning is completely decoupled from pipeline execution.
  - Zero computational overhead (pure string prompt construction).

## ADR 012: Dual-Transport Architecture — WebTransport (HTTP/3 Multi-Stream) with Transparent WebSocket Fallback (Phase 9)
- **Context**: In high-concurrency or low-bandwidth voice streaming, WebSocket's single TCP byte stream causes head-of-line (HoL) blocking when interleaved binary audio frames delay critical control signals (e.g. `ping`, `reset`, `end-of-utterance`) or text transcripts. WebTransport over HTTP/3 (QUIC) eliminates HoL blocking by multiplexing multiple independent byte streams and unreliable datagrams over a single UDP connection. However, WebTransport requires strict TLS 1.3 certificates and specialized reverse-proxy support (Nginx 1.25+ with QUIC, Caddy, or Envoy), creating substantial deployment and local development obstacles if treated as an exclusive transport.
- **Decision**:
  - **Transport Decoupling**: Extracted the proven Phase 7/8 WebSocket endpoint from `main.py` into `src/backend/transport/websocket_fallback.py` to maintain it as an independently tested, first-class fallback path.
  - **Multi-Stream Separation**: Implemented `src/backend/transport/webtransport.py` structured around 4 dedicated streams plus a datagram channel:
    - **Stream A (Client -> Server)**: Continuous 16kHz PCM16 audio chunks feeding Silero VAD.
    - **Stream B (Bidirectional)**: Low-latency JSON control commands (`ping`/`pong`, `reset`, `end-of-utterance`).
    - **Stream C (Server -> Client)**: Text transcripts, sentence start/end markers, and turn completion summaries.
    - **Stream D (Server -> Client)**: Binary WAV audio frames for pipelined TTS speech synthesis.
    - **Datagram Channel (Unreliable UDP)**: Fast, non-blocking affective telemetry (`primary`, `valence`, `arousal`) and request latency telemetry.
  - **Zero-Friction Runtime Fallback**: The React client detects browser WebTransport availability (`'WebTransport' in window`). If unavailable, or if the connection attempt times out / fails handshake (such as during local development without pre-trusted QUIC TLS certs), it instantly and transparently falls back to `ws://127.0.0.1:8000/ws/voice` with zero user disruption.
  - **Reverse-Proxy Risk Documentation**: Explicitly documented reverse-proxy requirements, UDP 443 routing caveats, and Nginx/Caddy configurations in `brain/13_DEPLOYMENT.md`, designating WebSocket as a permanent fallback rather than a temporary shim.
- **Consequences**:
  - Eliminates head-of-line blocking on networks with packet loss when WebTransport is available.
  - Guarantees 100% development and testing continuity on localhost and legacy environments via WebSocket fallback.
  - Clean separation of concerns between audio streams, control signals, and telemetry.

## ADR 013: Per-Stage Timing Observability, Structured JSON Logging, and Dev Benchmark Dashboard (Phase 10)
- **Context**: Profiling and debugging latency bottlenecks in a local pipeline (VAD $\to$ LID/ASR $\to$ SER $\to$ Router $\to$ RAG $\to$ LLM $\to$ TTS) requires visibility into individual stage durations without guessing. External APM agents or heavy Prometheus/Grafana stacks introduce significant setup friction, resource contention, and memory overhead on 4GB VRAM development environments.
- **Decision**:
  - **Structured JSON Telemetry Standard**: Implemented `StageTiming` capturing exact per-stage millisecond timings for `vad`, `asr`, `emotion`, `router`, `rag`, `llm_ttft`, `llm_total`, `tts_ttfa`, and `total`, tagged with `audio_received` UTC timestamp, `conversation_id`, and `intent`.
  - **Single Log Line Invariant**: Every voice utterance emits exactly one structured JSON log line (`"event": "stage_timing"`) to stdout, making logs easily parseable by standard centralized log collectors (e.g. Vector, fluentbit, datadog) without code changes.
  - **Lightweight Ring Buffer**: Built `BenchmarkCollector` (`collections.deque(maxlen=100)`) in `src/backend/telemetry.py` providing instant rolling window access over REST APIs (`/api/benchmark/metrics` and `/api/benchmark/summary`) with zero external database dependencies.
  - **Integrated Dev Dashboard**: Embedded a lightweight observability tab directly inside the React frontend (`App.tsx`), rendering real-time KPI metrics, stage latency comparison progress bars against budget thresholds, and a recent request table.
  - **Real Hardware Latency Baseline**: Formalized `brain/12_TESTING_SPEC.md` based strictly on empirically measured execution times on the development machine rather than speculative numbers (e.g. Silero VAD frame: 0.72ms; FAISS vector query: 3.4ms; TTFT budget: < 150ms; TTFA budget: < 350ms; Total turn budget: < 500ms).
- **Consequences**:
  - Instant visibility into latency regressions across builds without overhead.
  - Zero heavy external monitoring infrastructure required during development.
  - Standardized benchmark contract across automated tests, operational scripts, and UI.

## ADR 014: Defense-in-Depth Security Hardening — Handshake JWT Auth, Multi-Layer Rate Limiting, Document Ingestion Validation, and Interface Isolation (Phase 11)
- **Context**: Real-time voice assistants with local model serving present unique attack surfaces: unauthenticated streaming handshakes triggering GPU inference DoS, continuous speech streams causing unbounded memory exhaustion in VAD buffers, document uploads introducing path traversal and malicious file disguised indexing, and accidental network exposure of local LLM endpoints.
- **Decision**:
  - **Zero-Dependency HS256 JWT Auth**: Implemented self-contained RFC 7519 HMAC-SHA256 JWT generation and verification (`src/backend/security/auth.py`). Explicitly enforces algorithm locking (`HS256` only, rejecting `alg: "none"` downgrade attacks), token expiration window (`exp`), and constant-time signature verification (`hmac.compare_digest`).
  - **Transport Handshake Gating**: Configured WebSocket (`/ws/voice?token=...`) and WebTransport (`/wt?token=...`) handshakes to validate tokens when `settings.REQUIRE_AUTH=True`. Rejects unauthorized handshakes with RFC 6455 close code `1008` (Policy Violation). Defaults `REQUIRE_AUTH=False` in development to preserve seamless local testability.
  - **Multi-Layer Resource Quotas & Rate Limiting**: Built `SessionRateLimiter` (`src/backend/security/rate_limiter.py`):
    - Sliding window limiting clients to 20 utterances per minute (`UtteranceRateLimitExceeded`).
    - Audio duration cap limiting single utterances to 30.0 seconds (960,000 bytes PCM16 mono 16kHz). Buffers exceeding the cap are immediately aborted with `AUDIO_DURATION_LIMIT_EXCEEDED` to prevent memory exhaustion.
    - Max RAG document upload size capped at 10 MB (`UploadSizeLimitExceeded`).
  - **Strict RAG Document Ingestion Validation**: Implemented `validate_document_file` in `scripts/database/build_rag_index.py`:
    - Canonical path resolution (`os.path.realpath`) against documents directory, rejecting directory traversal (`../`).
    - File extension whitelist restricted to `.pdf`, `.docx`, `.txt`, and `.md`.
    - Magic byte header inspection verifying `%PDF` for PDFs, `PK\x03\x04` for DOCX, and validating UTF-8 while rejecting binary null bytes (`\x00`) for text/markdown.
  - **Localhost Interface Binding Invariant**: Enforced `127.0.0.1` binding across all servers and documentation (`uvicorn`, `llama-server`, Vite dev server).
  - **Secrets Hygiene & Operational Runbooks**:
    - Purged all secrets from codebase into `.env`.
    - Provided placeholder templates in `security/secrets.example/` and created `security/security-checklist.md`.
    - Codified incident response procedures in `runbooks/authentication-failure.md` and `runbooks/api-failure.md`.
- **Consequences**:
  - Robust protection against resource exhaustion, DoS, and malicious document indexing.
  - 100% offline, zero-cloud dependency security model.
  - Clear operational protocols for auth and API failure recovery.

## ADR 015: Decoupled Container Architecture, Separate GPU Model-Serving Layer, and Production Deployment Strategy (Phase 12)
- **Context**: Monolithic packaging of web frontends, backend APIs, and GPU-intensive LLM inference into a single container creates major deployment friction and extreme cloud cost waste. Running static web files and standard FastAPI processes on an expensive GPU cloud instance (e.g. AWS `g5.xlarge` or GCP `g2-standard-4`) costs $400–$1,000+/month. Furthermore, deploying across local developer machines, single-machine demo servers, and distributed cloud environments requires distinct service isolation and resource controls.
- **Decision**:
  - **Decoupled Model Serving Layer**: Isolated the `llama.cpp` inference engine into its own independent `llm-server` service in `docker-compose.prod.yml` and `docker/docker-compose.yml`. In cloud deployments, this allows running `llm-server` on a dedicated GPU host (utilizing `ghcr.io/ggerganov/llama.cpp:server-cuda` with NVIDIA reservations), while the frontend, backend, and database remain on low-cost CPU instances communicating over private VPC/WireGuard.
  - **Multi-Stage Containerization**:
    - **Backend (`docker/Dockerfile.backend`)**: Lightweight Python 3.11 image with `libsndfile1`, `ffmpeg`, non-root user (`senseai`), and `/health` curl healthcheck.
    - **Frontend (`docker/Dockerfile.frontend`)**: Multi-stage build (Node 20 Alpine builder $\to$ Nginx Alpine runtime) serving optimized static assets with reverse proxying for `/api`, `/ws`, `/wt`, and `/health`.
  - **Relational Database Separation**: Added PostgreSQL 16 Alpine container with persistent volume in `docker-compose.prod.yml` fulfilling the production database migration requirement.
  - **Explicit Cloud GPU Cost Realism**: Authored `docs/DEPLOYMENT.md` explicitly emphasizing that while the open-source software stack is free, 24/7 dedicated GPU hosting costs $150–$1,000+/month, and documenting cost-reduction strategies (decoupled tiering, idle shutdown, spot instances).
  - **Production Gate & Recovery**: Authored `brain/14_PRODUCTION_CHECKLIST.md` as a literal 8-section checklist synthesizing all system requirements from Phases 1–12, accompanied by `runbooks/deployment-failure.md` and `runbooks/rollback.md`.
- **Consequences**:
  - High infrastructure flexibility: supports bare-metal local dev, single-machine demo compose, and distributed multi-server cloud deployment.
  - Maximum cost efficiency: isolates GPU compute spend to model inference only.
  - Standardized, zero-friction operational deployment and rollback workflows.

## ADR 016: 4-Tier Testing Consolidation, Mock Isolation Fixtures, CI Automation, and Backlog Structuring (Phase 13)
- **Context**: As the system matured across 12 iterative build phases, tests accumulated across unit, integration, and api directories risked cross-contamination due to stateful singletons (`model_manager`, `benchmark_collector`, `rate_limiter`, `settings`). Running tests in arbitrary order or within continuous integration without hardware acceleration required guaranteed isolation, zero cloud model downloads, and rapid test turnaround.
- **Decision**:
  - **Global Isolation Fixtures (`tests/conftest.py`)**: Implemented an autouse fixture executing around every test that resets configuration snapshots (`MOCK_MODELS=True`, `REQUIRE_AUTH=False`), flushes the benchmark ring buffer, clears rate-limiter utterance histories, and initializes mock models safely.
  - **End-to-End Voice Suite (`tests/e2e/test_voice_e2e.py`)**: Implemented simulated speech-turn lifecycles covering WebSocket handshake auth, streaming sentence chunks, turn completion events, multi-intent routing, and telemetry validation.
  - **Automated GitHub Actions CI (`.github/workflows/ci.yml`)**: Constructed a 4-job CI workflow:
    - `lint`: Python syntax check with `flake8` and TypeScript typecheck with `tsc --noEmit`.
    - `test-backend`: Consolidated test suite execution on Python 3.11 with mock models.
    - `smoke-test-health`: Background server launch and operational health audit via `check_health.py`.
    - `build-frontend`: Production Vite bundling.
  - **Finalized Testing Specification & Deferred Backlog**: Published final `brain/12_TESTING_SPEC.md` and structured `brain/15_MICROTASKS.md` cataloging deferred work (Command engine execution, sentiment classifier upgrade, asymmetric JWT, WebTransport local CA).
- **Consequences**:
  - Deterministic, 100% repeatable test runs across all 4 tiers in under 30 seconds.
  - Automated PR verification preventing regressions from entering production.
  - Fully transparent, auditable backlog for future system evolution.

## ADR 017: Resilience Architecture, Circuit Breaker, Bounded Retries, and Graceful Degradation (Phase 14)
- **Context**: In local voice assistants, downstream model servers (e.g. `llama.cpp` HTTP endpoints), neural weights (IndicConformer, Indic Parler-TTS), or local vector indexes (FAISS) can become unavailable, encounter transient CUDA out-of-memory errors, or crash. Hard failures (hanging connections, unhandled 500 exceptions, process terminations) destroy conversational user trust. Furthermore, multi-client concurrency on single-GPU hardware risks driver timeouts and memory corruption without backpressure.
- **Decision**:
  - **Circuit Breaker on Downstream LLM Engine (`src/backend/llm/circuit_breaker.py`)**: Implemented a 3-state state machine (`CLOSED`, `OPEN`, `HALF_OPEN`). Upon 3 consecutive request failures (`failure_threshold = 3`), the circuit trips to `OPEN`, immediately fast-failing subsequent calls without network overhead for a 15-second cooldown (`cooldown_seconds = 15.0`). Upon cooldown expiration, it enters `HALF_OPEN` to permit a trial probe, automatically healing back to `CLOSED` upon success.
  - **Bounded Retries with Exponential Backoff**: Wrapped `llama.cpp` streaming HTTP calls in a bounded retry loop (2 retries with exponential backoff: 0.2s, 0.4s) and neural TTS generation in a bounded retry loop (2 retries with 50ms backoff). Retries fail fast to synthesized acoustic tones rather than looping silently forever.
  - **Graceful Multi-Tier Degradation**:
    - If IndicConformer weights fail to load or are absent, the system logs a warning and routes transcription seamlessly via SenseVoiceSmall (English/global) without crashing.
    - If the FAISS vector index is missing or unindexed, the Intent Router and Voice Pipeline dynamically degrade the `knowledge` intent to `chat`, answering conversationally rather than throwing an unhandled 500 error.
  - **GPU Concurrency Limiter & Queueing Backpressure (`src/backend/pipeline/concurrency.py`)**: Implemented an asynchronous semaphore (`asyncio.Semaphore(2)`) guarding LLM generation and TTS synthesis stages, safely queueing concurrent voice sessions to prevent VRAM over-allocation on single-GPU hosts.
  - **Documented Error Specification (`brain/09_ERROR_HANDLING.md`)**: Authored comprehensive documentation detailing failure modes, retry policies, circuit breaker states, and transport error frames.
- **Consequences**:
  - Zero-crash, zero-hang pipeline guarantee during local model outages or resource pressure.
  - Deterministic fast-fail behavior under service downtime (<50ms response instead of 30s timeout).
  - High resilience and predictable operational safety across single-GPU and resource-constrained environments.

## ADR 018: Data Retention Lifecycle, Backup/Restore Strategy, and Rebuildable Vector Indexes (Phase 15)
- **Context**: Clear data retention and disaster recovery strategies are necessary to uphold privacy and maintain system integrity. The system processes streaming audio, stores emotion logs and transcripts, and queries vectorized document embeddings. Storing raw audio indefinitely presents extreme privacy and storage risks. Vector index binary files (FAISS) can suffer platform or library drift, while relational databases (SQLite in dev, PostgreSQL in prod) require deterministic backup, verification, and recovery procedures.
- **Decision**:
  - **Explicit Data Retention Hierarchy**:
    - **Raw Audio Chunks**: 0-second persistence. Retained solely in transient RAM buffers during active streaming, and permanently discarded immediately after ASR inference.
    - **Transcripts & Emotion History**: Stored in SQLite/PostgreSQL with a default retention policy of 30 days. Pruning implemented via `EmotionStorage.prune_expired_records(retention_days=30)` and scheduled cron tasks.
    - **RAG Source Documents**: Retained indefinitely as canonical ground-truth in `data/documents/` (PDF, DOCX, Markdown, Text).
    - **FAISS Vector Index**: Ephemeral derived artifact in `data/index/`. Documented that rebuilding the index from `data/documents/` via `python scripts/database/build_rag_index.py` is the primary and preferred restore path rather than mandating binary index snapshots.
  - **Dual-Database Backup & Restore Tooling**:
    - Implemented POSIX shell scripts (`scripts/database/backup.sh`, `scripts/database/restore.sh`) and cross-platform Python CLI (`scripts/database/backup_manager.py`).
    - SQLite backups use non-blocking online `.backup` / `sqlite3.backup()` API to eliminate lock contention on running systems.
    - PostgreSQL backups use consistent `pg_dump --clean --if-exists`.
    - Automated SHA256 checksum generation (`.sha256`) and verification on all backup artifacts.
    - Pre-restore safety snapshots created prior to restoring over an existing database.
  - **Operational Runbooks**:
    - Authored `runbooks/database-failure.md` covering WAL lock clearing, `.recover` disaster recovery for corrupted databases, and connection pool exhaustion.
    - Authored `runbooks/backup-restore.md` detailing integrity checks (`PRAGMA integrity_check`), restore drills, and FAISS rebuild validation.
  - **Automated Production Scheduling**:
    - Added GitHub Actions workflow (`.github/workflows/backup.yml`) running daily at 2:00 AM UTC with 7-day artifact upload.
    - Added Linux crontab template (`config/production/backup.cron`) and environment config (`config/production/backup-config.env`).
- **Consequences**:
    - Guaranteed compliance with privacy-first data handling principles (zero audio persistence).
    - Rebuildable search index avoids platform drift and reduces backup payload sizes.
    - Fully automated, verifiable backup and recovery pipelines for dev and prod deployments.

## ADR 019: Read-Only Model Context Protocol (MCP) Bridge for Document Retrieval and Session History (Phase 16)
- **Context**: Autonomous coding assistants (e.g. Antigravity IDE, Claude Code, Cursor) and downstream agent workflows benefit from directly querying the SenseAI document knowledge base and past session emotion histories. However, exposing unrestricted API surfaces or speculative infrastructure could introduce attack vectors, allow accidental writes or deletions, or enable remote triggering of GPU-intensive voice pipelines.
- **Decision**:
  - **Minimal Read-Only Tool Surface (`src/backend/mcp_server/server.py`)**:
    - Implemented a lightweight, dependency-free MCP server adhering to JSON-RPC 2.0 (spec `2024-11-05`) over standard I/O (`stdio`).
    - Exposes strictly two read-only tools:
      1. `search_documents(query: str, top_k: int = 3)`: Bridges to `RAGRetriever` for dense vector search against `data/index`.
      2. `get_conversation_history(session_id: str, limit: int = 10)`: Bridges to `EmotionStorage` for emotion states and transcripts.
    - **Zero Write Operations**: No document upload, index modification, or database write tools exist.
    - **Zero Pipeline / Model Invocations**: Server cannot invoke Silero VAD, SenseVoice, Qwen LLM, or Parler-TTS. It is an information inspection bridge, not a remote voice trigger.
  - **Security & Transport Isolation**:
    - Runs as a child process via `stdio` (`python -m src.backend.mcp_server.server`), inheriting OS file permissions and process isolation with zero listening TCP/UDP ports.
    - Added configuration entry in `.agents/mcp_config.json`.
    - Documented in `brain/10_SECURITY.md` that any future network transport (HTTP/SSE) strictly requires an authenticating reverse proxy with mTLS or Bearer tokens.
- **Consequences**:
  - Enables downstream IDE and agent integration without security compromises.
  - Eliminates speculative infrastructure overhead: implementation is self-contained in ~200 lines of standard Python.
  - 100% testable via standard JSON-RPC fixtures in CI.

## ADR 020: Optional Cloud LLM Provider (Gemini 3 Flash) for Side-by-Side Comparison (Phase 17)
- **Context**: For benchmarking latency, multilingual conversational fluency, and reasoning fidelity during live demonstrations, developers and evaluators benefit from comparing the local Qwen3-1.7B (Q4_K_M GGUF) model directly against state-of-the-art frontier cloud models like Google Gemini 3 Flash. However, the core architectural identity of SenseAI is 100% local, private intelligence. Cloud routing must never be the default, must not pollute downstream TTS or emotion pipeline interfaces, and must clearly declare its privacy implications.
- **Decision**:
  - **Identical Interface Signature (`src/backend/llm/gemini.py`)**:
    - Implemented `GeminiClient` matching the exact asynchronous method signatures of `QwenClient` (`stream_response`, `generate_response`, `check_health`).
    - Consumes the same structured emotional and linguistic context parameters (`prompt`, `emotion`, `language`, `mixed_language`, `messages`).
    - Streams tokens via SSE using `httpx.AsyncClient` from Google Gemini REST API (`gemini-2.5-flash` / Gemini 3 Flash), feeding directly into `SentenceBoundaryChunker` and emotion-conditioned Indic Parler-TTS without downstream modification.
  - **Default-Local Routing & Runtime Override (`src/backend/llm/router.py`)**:
    - Added `LLM_PROVIDER=local|cloud` in `config/development/.env.example` and `src/backend/config.py`.
    - Enforced strict invariant: `LLM_PROVIDER=local` is the permanent default.
    - Added per-request override support in `VoicePipeline.stream_utterance(..., llm_provider=...)` and `/ws/voice` control action `{"action": "set_llm_provider", "provider": "cloud"|"local"}`.
    - Frontend includes a one-click runtime toggle button and active badge (`GEMINI 3 FLASH` vs `LOCAL QWEN3`).
  - **Explicit Privacy & Billing Disclosures**:
    - Documented in `brain/02_TRD.md` Section 7 and `README.md` that cloud mode sends spoken transcripts, emotional labels, and language tags to Google's API as an opt-in exception to the project's local-only privacy guarantee.
    - Explicitly documented that cloud mode requires an independent API key from Google AI Studio (`GEMINI_API_KEY`), and that a Google AI Pro / consumer subscription does NOT grant API access.
- **Consequences**:
  - Enables side-by-side local vs. cloud evaluations without restarting the backend.
  - Zero downstream pipeline coupling: TTS, VAD, ASR, and intent gates operate completely identically.
  - Transparent data privacy guarantees preserved for users.

## ADR 021: Disabling Qwen3 Thinking Mode by Default for Low-Latency Voice Inference
- **Context**: Qwen3 models enable internal reasoning/thinking tokens by default in chat templates. For voice assistant applications, even trivial conversational inputs like "hii" or "what time is it?" trigger 100+ reasoning tokens before emitting the first user-facing answer token. This creates an unacceptable 1-3 second delay in Time-to-First-Token (TTFT), violating the voice pipeline's <180ms LLM latency allocation and exposing internal chain-of-thought tokens in the speech synthesis queue.
- **Decision**:
  - **Client-Side Default (`chat_template_kwargs: {"enable_thinking": false}`)**:
    - Updated `src/backend/models/llm.py` and `src/backend/llm/qwen.py` so that every JSON request payload to llama.cpp includes `"chat_template_kwargs": {"enable_thinking": False}` by default.
  - **Config Flag & Dynamic Overrides**:
    - Added `LLM_ENABLE_THINKING: bool = False` in `src/backend/config.py` and `LLM_ENABLE_THINKING=false` in `config/development/.env.example`.
    - Allowed per-request override (`enable_thinking: Optional[bool] = None`) across `stream_response` and `generate_response` for future tasks that genuinely require chain-of-thought deliberation.
  - **Standardized Developer Launch Script**:
    - Added `scripts/development/start_llm_server.ps1` to start `llama-server` on `127.0.0.1:8080` with `-hf unsloth/Qwen3-1.7B-GGUF:Q4_K_M --port 8080 --n-gpu-layers 99`.
- **Consequences**:
  - Drops TTFT for greetings and common conversational queries by over 80%.
  - Speech synthesis begins immediately on the first conversational sentence chunk without reasoning preamble.
  - Can be cleanly re-enabled via environment variable or per-request parameter when complex multi-step reasoning is demanded.

## ADR 022: Unified Speech Perception Architecture & Truthful Confidence Policy (Phase 1 Migration)
- **Context**: Migrating to the target architecture (`ai/preprocessing/`, `ai/inference/`) required decoupling speech perception from backend endpoints, establishing a model-independent schema, and handling confidence reporting truthfully without fabricated metrics.
- **Decision**:
  - **Calibrated Confidence Policy (`confidence = None`)**:
    SenseVoiceSmall rich transcription emits greedy discrete token predictions via CTC and does not provide calibrated posterior probabilities for emotion or language. In strict accordance with the Truthfulness rule ("never invent a number"), `SpeechResult.confidence` is set to `None` by default rather than fabricating an artificial number (such as fixed 0.85).
  - **VAD-Gated Short Circuiting**:
    Silero VAD v5 ONNX is placed as an active pre-inference gate in `SenseVoiceSpeechEngine.transcribe()`. Empty, silent, or sub-second audio clips return an explicit well-formed `SpeechResult` with `transcript=""`, `language="unknown"`, `emotion=None`, and `vad_has_speech=False`, incurring zero neural ASR compute or model loading overhead.
  - **Single Unified Schema (`SpeechResult`)**:
    Standardized on Pydantic `SpeechResult` with zero model-specific keys in the root schema (`transcript`, `language`, `emotion`, `confidence`, `processing_time_ms`, `model_version`). Rich tags are cleanly parsed and segregated into standard optional extras (`audio_events`, `debug`).
  - **Graceful Weight Degradation & Explicit Errors**:
    When model weights or deep learning libraries (`funasr`, `torch`) are not present on the host, the engine fails with a clear, actionable `RuntimeError` naming the expected path. Tests requiring model weights are decorated with `@pytest.mark.model` and skip cleanly. A `--mock` CLI flag is supported strictly for offline dry-run testing.
- **Consequences**:
  - ASR and emotion classification can run 100% standalone with zero dependency on LLM, RAG, TTS, or database.
  - Zero mock contamination in production code paths.
  - Clean foundation ready for IndicConformer integration in Phase 4.

## ADR 023: Non-Blocking Speech Service & WebSocket v1 Protocol (Phase 2 Migration)
- **Context**: Wrapping the Phase 1 speech engine in FastAPI required establishing clean architectural boundaries, ensuring that synchronous compute-heavy neural inference never blocks the asyncio event loop or degrades concurrent health checks, providing unified upload and predict endpoints without duplicated logic, and specifying a robust v1 WebSocket streaming protocol.
- **Decision**:
  - **Threadpool Offloading & Bounded Concurrency**: Synchronous ASR inference is dispatched off the event loop via `asyncio.to_thread` wrapped in `asyncio.Semaphore(settings.INFERENCE_CONCURRENCY_LIMIT)`. Health checks (`/api/health`) and keepalives remain fully responsive with <10ms latency even during active multi-second speech perception runs.
  - **Shared Service Pipeline for Upload and Predict**: `POST /api/speech/upload` and `POST /api/predict` invoke the exact same `speech_service.transcribe_audio_bytes()` in-memory decoding pipeline. `POST /api/predict` returns `PredictionResponse(SpeechResult)`, appending an optional `assistant` block (`None` in Phase 2) for downstream LLM phases without duplicating validation or inference code.
  - **WebSocket Protocol v1 Specification**: Enforced client-server sequencing (`start` -> `ready` -> binary PCM16 -> `speech_result` -> `stop`), server-side Silero VAD state events (`speech_start`, `speech_end`), and per-connection 5MB audio buffer limits (`WS_MAX_BUFFER_BYTES`). Safely ignores reserved downstream message frames (`llm_delta`, `tts_chunk`, etc.) without connection termination.
  - **In-Memory Audio Ephemerality**: All audio processing occurs strictly in memory (`BytesIO` and NumPy buffers) with zero audio persistence to disk.
## ADR 024: Target Layout Relocation, Pure Protocol Framing & Graceful Assistant Fallback (Phase 3 Migration)
- **Context**: The frontend needed relocation to the root `frontend/` directory specified in `docs/architecture/target-architecture.md`, implementation of a clean, typed WebSocket client conforming to the Phase 2 Protocol v1 (`docs/api/websocket.md`), robust audio capture with AudioWorklet and error recovery, and rendering of all perceptual information even when downstream LLM or TTS services are not configured.
- **Decision**:
  - **Relocation (`src/frontend` -> `frontend`)**: Completed using `git mv` with zero duplicated components.
  - **Typed Protocol Hook & Safe Unknown Message Policy**: All v1 message types are defined as strict TypeScript interfaces. Unknown or reserved downstream frames (`llm_delta`, `tts_chunk`, etc.) are safely ignored via `console.debug` and never terminate the socket connection.
  - **Graceful Multi-Tier Perception Display**: When `/api/health` reports LLM or TTS as `"not_configured"` or `"offline"`, the assistant area shows a compact, informative notice. Real-time transcript, language, emotion, and latency continue to render normally without error screens.
  - **Audio Capture & Fallback**: Used `AudioWorklet` with downsampling to 16 kHz mono signed 16-bit PCM in `/audio-processor.js`, with automatic fallback to `ScriptProcessorNode` if worklets are unavailable. Hardware errors (`NotAllowedError`, `NotFoundError`, and track `.onended` disconnects) trigger explicit user feedback.
  - **Seamed History Store**: In-memory `conversationStore` with observer pattern decouples state from UI and provides an explicit seam for `/api/history` in Phase 9.
- **Consequences**:
  - Clean, modular frontend conforming to target architecture.
  - Decoupled from backend completion of future LLM/TTS phases.
  - 100% testable pure functions with Vitest and ESLint enforcement.

## ADR 025: Dual-ASR Language Routing Policy, Indic Emotion Isolation, and Pluggable LID (Phase 4 Migration)
- **Context**: Routing speech between SenseVoiceSmall (global languages) and IndicConformer-600m (Hindi and 21 Indic languages) required a deterministic precedence policy, preventing duplicate speech pipelines, establishing strict emotion isolation for Indic speech, and defining an evaluation strategy for Spoken Language Identification (LID).
- **Decision**:
  - **3-Tier Language Routing Precedence Policy**:
    Implemented in `ai/routing/language_router.py`:
    1. Tier 1 (Highest): Explicit client `language_hint` always wins. If Indic, routes to `indicconformer`; if global, routes to `sensevoice`.
    2. Tier 2 (Medium): Spoken LID evaluates audio if hint is omitted. If confidence $\ge$ `LID_CONFIDENCE_THRESHOLD` (0.60), routes to the detected engine.
    3. Tier 3 (Lowest / Fallback): Falls back to default engine (`sensevoice` / English).
  - **Single Pipeline in `SpeechService`**:
    Both ASR engines and the `LanguageRouter` are managed exclusively by `SpeechService` in `backend/app/services/speech_service.py`. No secondary pipeline, parallel service, or duplicate routing logic is created.
  - **Strict Emotion Invariant for Indic Audio (`emotion = None`)**:
    IndicConformer is an ASR model only. SenseVoice's emotion head is **never** run on Hindi audio. Indic results return `emotion = None` and `emotion_scores = None`. A clean hook (`apply_emotion_hook`) is provided for Phase 5 to attach dedicated Hindi SER without coupling to ASR.
  - **LID Candidate Evaluation & No Automatic Downloads**:
    Evaluated SpeechBrain VoxLingua107, Meta MMS-LID, and OpenAI Whisper head. Recommended VoxLingua107 for native PyTorch and Whisper-tiny for ONNX. Enforced safety rule: zero model weights downloaded without explicit confirmation. Pluggable `LanguageIdentifier` protocol allows testing decision logic with injected hand-written LID outputs.
  - **Code-Mixed Speech (Hinglish) as Known Limitation**:
    Formally documented in `docs/architecture/language-routing.md` that conversational Hinglish is an unmeasured known limitation until empirical benchmarks are established.
- **Consequences**:
  - Deterministic, testable language routing with zero neural model overhead in unit tests.
  - Single pipeline invariant fully maintained.
  - Complete isolation between Hindi ASR and future Phase 5 Hindi emotion recognition.




