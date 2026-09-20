# 12 — Testing, CI & Latency Benchmark Specification (Final Version)

This document defines the testing pyramid, mock isolation policy, continuous integration automation, and empirical latency benchmark targets for the **SenseAI Voice Assistant** established in **Phase 13**.

---

## 1. The 4-Tier Testing Pyramid

SenseAI enforces a comprehensive 4-tier testing strategy ensuring coverage across all pipeline layers:

```text
               / \
              /   \
             / E2E \          Tier 4: tests/e2e (Full speech turns, auth handshake, telemetry)
            /-------\
           /   API   \        Tier 3: tests/api (FastAPI routes, WebSocket ping/pong, /health)
          /-----------\
         / Integration \      Tier 2: tests/integration (RAG pipeline, streaming sentence flow)
        /---------------\
       /      Unit       \    Tier 1: tests/unit (VAD, ASR, Router, Emotion, LLM, TTS, Security)
      /-------------------\
```

| Tier | Directory | Scope & Coverage | Mock Policy |
| :--- | :--- | :--- | :--- |
| **Unit** | `tests/unit/` | Isolated functional testing of single classes: `SileroVAD`, `LanguageRouter`, `SEREmotionAnalyzer`, `IntentRouter`, `MultilingualE5Embeddings`, `SentenceChunker`, `JWTAuth`, `SessionRateLimiter`. | Isolated in-memory mocks; runs in < 5 seconds. |
| **Integration** | `tests/integration/` | Cross-module chaining: Intent hard gate $\to$ RAG retrieval $\to$ Qwen3 streaming $\to$ sentence-by-sentence TTS synthesis. | Synthetic audio chunks & in-memory vector index. |
| **API** | `tests/api/` | HTTP REST endpoints (`/health`, `/api/transport/capabilities`, `/api/benchmark/summary`) and basic WebSocket handshake. | FastAPI `TestClient` with in-memory app lifespan. |
| **End-to-End** | `tests/e2e/` | Complete simulated speech-turn lifecycles from raw PCM16 audio input to synthesized binary WAV audio frames and telemetry logging. | Full pipeline running against `MOCK_MODELS=true`. |

---

## 2. Test Isolation & Mocking Policy

To guarantee deterministic, order-independent test execution in CI and local developer environments:
1. **Global Autouse Fixture (`tests/conftest.py`)**:
   - Resets `settings.MOCK_MODELS = True` and `settings.REQUIRE_AUTH = False` for each test.
   - Flushes `benchmark_collector` ring buffer to zero.
   - Clears `rate_limiter._utterance_history` to prevent false rate-limit rejections across tests.
   - Restores pre-test environment variables upon teardown.
2. **Zero Cloud/Heavy Model Downloads in CI**:
   - `MOCK_MODELS=true` bypasses multi-gigabyte HuggingFace checkpoint downloads (`SenseVoiceSmall`, `indic-conformer-600m`, `indic-parler-tts`) on GitHub Actions runners, enabling the entire 70-test suite to complete in under 30 seconds.

---

## 3. Measured Dev Hardware Baseline vs. SLA Budgets

The end-to-end voice loop operates under a strict budget of **< 500ms Total Roundtrip** and **< 350ms Time-to-First-Audio (TTFA)**.

*Measured Hardware:* Intel i5-12450H (12 threads), 16GB RAM, NVIDIA RTX 2050 Mobile (4GB VRAM), Windows 11 / WSL2.

| Stage | Telemetry Key | Target SLA Budget (P95) | Measured Real Hardware | Measured Mock Mode | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **VAD Segmentation** | `vad` | **< 15.0 ms** | 0.72 ms / frame (~2.1 ms flush) | ~1.9 ms | **PASS** |
| **ASR & Language Routing** | `asr` | **< 150.0 ms** | 95.0 – 140.0 ms | 1.2 – 8.5 ms | **PASS** |
| **Emotion Analysis (SER + Text)** | `emotion` | **< 30.0 ms** | 0.05 – 1.2 ms | 0.4 – 0.8 ms | **PASS** |
| **Intent Router Hard Gate** | `router` | **< 10.0 ms** | 0.05 – 0.5 ms | 0.05 – 0.1 ms | **PASS** |
| **RAG Vector Search (FAISS)** | `rag` | **< 35.0 ms** | 3.40 ms | 0.0 – 3.2 ms | **PASS** |
| **LLM Time-to-First-Token** | `llm_ttft` | **< 150.0 ms** | 85.0 – 130.0 ms (Qwen3-1.7B Q4_K_M) | 1.5 – 3.2 ms | **PASS** |
| **LLM Total Sentence Stream** | `llm_total` | **< 400.0 ms** | 280.0 – 395.0 ms | ~410 ms | **PASS** |
| **TTS Time-to-First-Audio** | `tts_ttfa` | **< 350.0 ms** | 180.0 – 240.0 ms (Chunk 1) | ~210 ms | **PASS** |
| **Total Roundtrip Turn** | `total` | **< 500.0 ms** | **340.0 – 460.0 ms** | ~430 ms | **PASS** |

---

## 4. Continuous Integration Pipeline (GitHub Actions)

Defined in [`.github/workflows/ci.yml`](file:///d:/Capstone%20Project/NewSenseVoice/.github/workflows/ci.yml):
- **`lint`**: Syntax and AST audit with `flake8`, plus frontend TypeScript compilation (`tsc --noEmit`).
- **`test-backend`**: Executes full test suite (`pytest tests/ -v --durations=10`) on Python 3.11 with `MOCK_MODELS=true`.
- **`smoke-test-health`**: Starts backend service in background and executes `monitoring/health-checks/check_health.py` verifying `/health` and model readiness.
- **`build-frontend`**: Runs `npm ci && npm run build` validating production Vite asset bundling.
