# 15 — Microtasks & Deferred Backlog

This document maintains a technical backlog of all features, enhancements, and optimizations that were deliberately stubbed, deferred, or scoped out during Phases 1 through 12 to maintain architectural simplicity.

---

## 1. Intent Router: Command Engine Handlers (Deferred from Phase 4)
- **Current State**: `src/backend/pipeline/intent.py` routes queries matching `COMMAND_PATTERNS` to `IntentCategory.COMMAND`. The pipeline currently returns a stub response (`"Command execution is not implemented yet."`).
- **Target Task**:
  1. Build `src/backend/pipeline/commands/`:
     - **Calculator**: Safe AST-evaluated arithmetic (`25 * 4`, `what is 15 percent of 80`).
     - **Timer / Stopwatch**: Async background timer with audio alarm trigger.
     - **Reminder Engine**: SQLite-persisted reminders with scheduled notification events.
     - **Device Controls**: System volume control, audio device switcher via OS hooks.
  2. Wire command execution directly into `VoicePipeline.stream_utterance(...)` bypassing LLM inference.
- **Priority**: Medium | **Estimated Effort**: 4 hours.

---

## 2. SER & Sentiment: Lexicon Sentiment Upgrade (Deferred from Phase 5)
- **Current State**: Emotion detection blends SenseVoiceSmall acoustic SER output (`primary`, `confidence`, `valence`, `arousal`) with a fast, hardcoded dictionary-based text polarity check (`src/backend/emotion/emotion.py`).
- **Target Task**:
  1. Replace the static keyword dictionary with a fast quantized ONNX sentiment model (e.g. `multilingual-sentiment-onnx` ~25MB) or expanded Hindi/Hinglish valence-arousal lexicon (e.g. Hindi SentiWordNet).
  2. Benchmark to ensure emotion analysis remains under the **< 30.0ms** latency budget.
- **Priority**: Low | **Estimated Effort**: 3 hours.

---

## 3. Security: Asymmetric JWT Signing & JWKS Endpoint (Deferred from Phase 11)
- **Current State**: Phase 11 implemented zero-dependency HS256 (HMAC-SHA256) JWT authentication with a shared secret key in `.env`.
- **Target Task**:
  1. Support RS256 / ES256 asymmetric signing where the backend private key signs tokens and a public `GET /.well-known/jwks.json` endpoint allows microservices and edge proxies to verify signatures without holding the signing key.
  2. Add automated token refresh endpoint (`POST /api/auth/refresh`).
- **Priority**: Medium | **Estimated Effort**: 2 hours.

---

## 4. Transport: Automated WebTransport Local CA & Cert Hash CLI (Deferred from Phase 9)
- **Current State**: WebTransport requires TLS 1.3. On localhost without a valid CA, modern browsers reject self-signed certificates, triggering automatic fallback to WebSocket.
- **Target Task**:
  1. Author `scripts/setup_local_cert.py` using `cryptography` to generate self-signed ECDSA certificates valid for 14 days (Chromium limit).
  2. Calculate the SHA-256 certificate fingerprint (`serverCertificateHashes`) and inject it into frontend `vite.config.ts` so developers can test WebTransport locally out of the box without special browser launch flags.
- **Priority**: Low | **Estimated Effort**: 2 hours.

---

## 5. Speech Synthesis: Indic Parler-TTS Prompt Expansion (Deferred from Phase 8)
- **Current State**: Emotion style mapping table (`EMOTION_STYLE_MAPPING`) is configured with descriptive prompts tailored for Hindi and English.
- **Target Task**:
  1. Expand style descriptions and speaker prompts across remaining scheduled Indic languages: Bengali, Tamil, Telugu, Marathi, Kannada, Malayalam, and Gujarati.
  2. Test naturalness and emotion delivery per language on real speaker samples.
- **Priority**: Medium | **Estimated Effort**: 5 hours.

---

## 6. Infrastructure: Distributed Multi-Node Cluster Adapters (Deferred from Phase 12)
- **Current State**: `BenchmarkCollector` ring buffers and `SessionRateLimiter` are held in-memory within a single backend process.
- **Target Task**:
  1. Provide optional Redis / PostgreSQL adapters for `SessionRateLimiter` and `BenchmarkCollector` when running multi-worker Uvicorn (`--workers 4`) or multi-node container clusters.
  2. Add Prometheus metrics exporter endpoint (`GET /metrics`) as an alternative to the in-memory benchmark buffer.
- **Priority**: Low | **Estimated Effort**: 4 hours.

---

## 7. Security: Enterprise Key Management Service (KMS) & Envelope Encryption (Deferred from Phase 18)
- **Current State**: Phase 18 field-level database encryption at rest uses symmetric Fernet (AES-128-CBC) with a base64 key loaded from environment configuration (`DATABASE_ENCRYPTION_KEY`).
- **Target Task**:
  1. Integrate cloud KMS / HSM provider (AWS KMS, Google Cloud KMS, Azure Key Vault, or HashiCorp Vault) using an envelope encryption pattern.
  2. Master Key (Key Encryption Key / KEK) resides in the remote HSM; Data Encryption Keys (DEKs) are dynamically generated, encrypted under the KEK, and rotated periodically (e.g. every 90 days).
  3. Implement automated key rotation and background re-encryption jobs for historical records stored in SQLite / PostgreSQL.
- **Priority**: Medium | **Estimated Effort**: 4 hours.

