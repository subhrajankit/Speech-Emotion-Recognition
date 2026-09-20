# SenseAI Security Hardening Checklist (Phase 11)

This checklist enforces defense-in-depth security standards across all deployments of the SenseAI Voice Assistant. Every deployment must be verified against this checklist prior to production promotion.

---

## 1. Network & Interface Binding

- [ ] **No `0.0.0.0` Wildcard Listeners**: Verify that all services bind exclusively to `127.0.0.1` (localhost):
  - Backend FastAPI server (`uvicorn src.backend.main:app --host 127.0.0.1 --port 8000`)
  - Local llama.cpp model server (`llama-server --host 127.0.0.1 --port 8080`)
  - Frontend dev server / reverse proxy (`--host 127.0.0.1 --port 5173`)
- [ ] **Firewall Ingress Restriction**: External ingress must terminate at an authenticated reverse proxy (e.g., Nginx, Envoy) with TLS 1.3. Internal model-serving ports (8080) must be blocked from LAN exposure.
- [ ] **CORS Origin Whitelisting**: `allow_origins` strictly restricted to approved local domains (`http://127.0.0.1:5173`, `http://localhost:5173`). Wildcard `*` origins are forbidden.

---

## 2. Authentication & Authorization

- [ ] **JWT Handshake Enforcement**: `REQUIRE_AUTH=true` is enabled in production `.env`.
- [ ] **WebSocket Handshake Validation**: Handshake rejects unauthenticated requests with RFC 6455 close code `1008` (Policy Violation).
- [ ] **WebTransport Auth Validation**: WebTransport session initialization validates JWT claims before binding audio streams.
- [ ] **Algorithm Locking**: Verification strictly permits `HS256` and rejects algorithm downgrade attacks (e.g., `alg: "none"` or RSA/HMAC confusion).
- [ ] **Token Expiry & Signature Verification**: Constant-time signature comparison (`hmac.compare_digest`) and expiration time window (`exp`) enforced with maximum 10s leeway.
- [ ] **Session Expiration**: Client tokens time out after `SESSION_TIMEOUT_MINUTES` (default: 60 minutes) requiring re-authentication.

---

## 3. Rate Limiting & Resource Quotas

- [ ] **Utterance Frequency Limiting**: Max 20 utterances per minute per session enforced via sliding window (`UtteranceRateLimitExceeded`).
- [ ] **Audio Duration Cap**: Utterance duration strictly capped at 30.0 seconds (960,000 bytes PCM16 mono 16kHz). Buffers exceeding cap are immediately aborted to prevent memory exhaustion (`AudioDurationLimitExceeded`).
- [ ] **RAG Ingestion Size Cap**: Max upload size capped at 10 MB per file (`UploadSizeLimitExceeded`).
- [ ] **Buffer Cleanup on Disconnect**: `finally` blocks explicitly purge VAD buffers and stream accumulators on client disconnect or session termination.

---

## 4. Input Validation & RAG Ingestion Security

- [ ] **Path Traversal Protection**: Canonical path resolution (`os.path.realpath`) verifies documents reside within the designated `data/documents/` directory; `../` traversal sequences rejected.
- [ ] **File Extension Whitelist**: Only `.pdf`, `.docx`, `.txt`, and `.md` accepted; executable (`.exe`, `.sh`, `.bat`, `.py`) and script extensions strictly rejected.
- [ ] **Magic Bytes Verification**: File headers inspected prior to text extraction:
  - PDF starts with `b"%PDF"`
  - DOCX starts with `b"PK\x03\x04"`
  - TXT/MD verified for valid UTF-8 and zero binary null bytes (`\x00`).
- [ ] **Empty File Handling**: 0-byte files rejected without triggering embedding passes.

---

## 5. Privacy & Zero-Persistence Invariant

- [ ] **Raw Audio Zero-Persistence**: Under NO circumstances is raw audio written to persistent disk beyond the live request lifecycle. Audio buffers live strictly in memory and are discarded after processing.
- [ ] **Transcript & Emotion Audit**: Only normalized text transcripts and aggregated emotion coordinates (`valence`, `arousal`, `primary`) may be written to SQLite/Postgres.
- [ ] **PII Masking**: Ensure logs do not print full raw speech buffers or sensitive user query payloads at `INFO` level.

---

## 6. Secrets & Environment Hygiene

- [ ] **No Hardcoded Secrets**: Zero secrets, passwords, or API keys embedded in source code.
- [ ] **Gitignore Verification**: `.env`, `.env.local`, `*.key`, `*.pem`, and `database/*.db` are excluded from version control.
- [ ] **Secure File Permissions**: Production `.env` file set to `chmod 600` (readable only by the service owner).
- [ ] **Key Rotation**: High-entropy JWT secrets generated with at least 256 bits of randomness (`openssl rand -base64 32`) and rotated quarterly.

---

## 7. Incident Response & Operations

- [ ] **Auth Failure Runbook**: Operators familiar with `runbooks/authentication-failure.md`.
- [ ] **API Failure Runbook**: Operators familiar with `runbooks/api-failure.md`.
- [ ] **Health Monitoring**: Automated health checks monitor `/health` and model readiness.
