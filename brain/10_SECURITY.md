# 10 — Security Hardening & Data Privacy Specification

This document defines the core security architecture, threat model, authentication protocol, rate limiting quotas, input validation, and privacy invariants for the **SenseAI Voice Assistant** established in **Phase 11**.

---

## 1. Threat Model & Attack Surface

The local voice assistant operates across browser web transports, local Unix domain sockets / TCP ports, and local document stores. The primary threat vectors addressed in Phase 11 include:

| Threat Vector | Attack Scenario | Mitigation in Phase 11 |
| :--- | :--- | :--- |
| **Unauthenticated Handshake** | Unauthorized web clients connect to `/ws/voice` or `/wt` and trigger compute-intensive local model pipelines. | **HS256 JWT Authentication Handshake**: Handshake requires a valid token via query param `?token=...`. Rejects invalid tokens with RFC 6455 close code `1008`. |
| **Algorithm Downgrade** | Attacker crafts a JWT with `alg: "none"` or swaps symmetric for asymmetric verification. | **Algorithm Locking**: Auth verification strictly enforces `HS256`, rejects any other algorithm, and utilizes constant-time signature comparison (`hmac.compare_digest`). |
| **Audio Buffer Exhaustion (DoS)** | Malicious client opens continuous voice stream without silence, causing unbounded buffer allocation in VAD segmenter. | **30-Second Utterance Duration Cap**: Utterances are strictly capped at 30.0s (960,000 bytes PCM16 mono 16kHz). Buffers exceeding this limit are aborted immediately with `AUDIO_DURATION_LIMIT_EXCEEDED`. |
| **Utterance Flooding (DoS)** | Rapid-fire audio bursts triggering concurrent ASR/LLM/TTS inference passes. | **20 Utterances/Minute Sliding Window**: Session-level rate limiter tracks sliding 60-second window, rejecting bursts exceeding 20 utterances with `RATE_LIMIT_EXCEEDED`. |
| **Path Traversal in RAG** | Uploaded documents use `../../` to escape `data/documents/` and overwrite or read arbitrary system files. | **Canonical Path Resolution**: `validate_document_file` uses `os.path.realpath` to ensure target paths strictly reside within the canonical documents directory. |
| **File Disguise Attacks** | Malicious executable (`.exe`, ELF, shell script) disguised as `.pdf` or `.docx` submitted for RAG vector indexing. | **Magic Byte Inspection**: File headers are inspected prior to parsing (`%PDF` for PDFs, `PK\x03\x04` for DOCX, null byte exclusion for UTF-8 text). |
| **Network Leakage** | Local model serving ports exposed on `0.0.0.0` allowing unauthorized LAN / WAN access. | **Strict Localhost Binding**: All services (`uvicorn`, `llama-server`, Vite) bind strictly to `127.0.0.1`. |

---

## 2. Authentication & Handshake Protocol

### HS256 Token Flow
1. **Token Issuance**: The client requests a scoped session token via `POST /api/auth/token`.
   ```json
   {
     "session_id": "sess_8f3a12cd",
     "client_id": "web-client"
   }
   ```
   Backend signs an HS256 JWT containing `sub`, `client_id`, `iat`, `nbf`, and `exp` (`SESSION_TIMEOUT_MINUTES` lifetime, default 60 min).
2. **WebSocket Handshake**:
   - Connection URL: `ws://127.0.0.1:8000/ws/voice?token=<JWT>`
   - When `settings.REQUIRE_AUTH=True`:
     - If `token` is missing or verification fails, server issues close code `1008` (Policy Violation) with descriptive reason string.
     - If valid, claims are bound to the connection's session context.
   - When `settings.REQUIRE_AUTH=False` (Development / Test):
     - Tokens are verified if present, or anonymous session IDs are assigned.
3. **WebTransport Handshake**:
   - Handshake URL: `https://127.0.0.1:8000/wt?token=<JWT>`
   - `WebTransportSession` verifies token claims during session construction.

---

## 3. Rate Limiting & Resource Quotas

The backend maintains an in-memory `SessionRateLimiter` (`src/backend/security/rate_limiter.py`):

- **Utterances per minute**: Maximum 20 utterances per 60-second sliding window per session (`UtteranceRateLimitExceeded`).
- **Audio duration per utterance**: Maximum 30.0 seconds of PCM16 mono 16kHz audio (960,000 bytes). If speech continues past 30.0s without silence end, the segmenter is reset and the client is notified (`AudioDurationLimitExceeded`).
- **RAG upload document size**: Maximum 10 MB (10,485,760 bytes) per ingested file (`UploadSizeLimitExceeded`).

---

## 4. Document Ingestion Security & Validation

All documents ingested into the RAG vector index via `scripts/database/build_rag_index.py` pass through `validate_document_file`:
1. **Extension Whitelist**: Only `.pdf`, `.docx`, `.txt`, and `.md` are parsed.
2. **Directory Traversal Check**: Canonical path verification against designated repository documents root.
3. **Size Verification**: Rejects files exceeding 10 MB or empty 0-byte files.
4. **Header / Magic Byte Inspection**:
   - PDF: Starts with `b"%PDF"`
   - DOCX: Starts with ZIP container magic bytes `b"PK\x03\x04"`
   - TXT / MD: Valid UTF-8 encoding; rejects any binary null bytes (`\x00`).

---

## 5. Network & Interface Binding Invariant

- **Hard Rule**: Local model-serving ports and backend processes bind to `127.0.0.1` only:
  - FastAPI: `http://127.0.0.1:8000`
  - llama.cpp OpenAI endpoint: `http://127.0.0.1:8080/v1`
  - Frontend Vite dev server: `http://127.0.0.1:5173`
- `0.0.0.0` wildcard interfaces are strictly forbidden in configuration files and scripts.
- **CORS Allowlist**: Restricted to `http://127.0.0.1:5173` and `http://localhost:5173`.

---

## 6. Zero-Persistence Invariant for Raw Audio

- **Strict Guarantee**: Under no circumstances is raw audio stored, written to disk, cached to filesystem, or persisted beyond the immediate request-response lifecycle.
- In-memory PCM byte arrays and temporary WAV buffers are deallocated immediately upon pipeline completion or error via Python `finally` blocks.
- **Persisted Data**:
  - `transcripts`: Stored in database for user session recall.
  - `emotion_history`: Emotion vector records (`primary`, `confidence`, `valence`, `arousal`) stored in SQLite/Postgres.
  - `RAG documents`: Stored in `data/documents/` and index in `data/index/`.

---

## 7. Secrets Hygiene & Operational Runbooks

- **No Secrets in Code**: All API keys, passwords, and signing secrets are managed via `.env`.
- **Templates**: Example templates provided in `security/secrets.example/env.secrets.example` and `security/secrets.example/jwt.key.example`.
- **Checklist**: Systematic deployment verification codified in `security/security-checklist.md`.
- **Operational Runbooks**:
  - `runbooks/authentication-failure.md`: Diagnostics, symptom signatures, and recovery steps for JWT/handshake rejections.
  - `runbooks/api-failure.md`: Diagnostics and remediation for model server crashes, rate limiting violations, and pipeline degradations.

---

## 8. Data Retention & Lifecycle Policy (Phase 15)

To uphold privacy while providing persistent conversational utility and contextual memory, SenseAI enforces an explicit four-tier data lifecycle:

| Data Category | Storage Location | Retention Duration | Lifecycle Action | Destruction / Recovery Method |
| :--- | :--- | :--- | :--- | :--- |
| **Raw Ingested Audio (PCM16)** | RAM buffers only | **0 seconds** (request lifecycle only) | Discarded immediately after ASR speech recognition completes. | Deallocated from memory buffers; zero disk writing under any condition. |
| **Transcripts & Session Metadata** | Relational DB (`database/dev.db` or PostgreSQL) | **30 days** (configurable via `DATA_RETENTION_DAYS`) | Accessible for user conversation history and benchmark auditing. | Automated deletion via `prune_expired_records()` or database retention cron. |
| **Emotion History Vectors** | Relational DB (`emotion_history` table) | **30 days** (configurable via `DATA_RETENTION_DAYS`) | Analyzed for session emotional trajectories and prompt conditioning. | Automated deletion via `prune_expired_records(retention_days=30)`. |
| **Uploaded RAG Documents** | Local filesystem (`data/documents/`) | **Indefinite** (persisted until manual deletion) | Primary source of truth for semantic vector embedding. | Backed up daily; deleted only upon explicit user/operator removal. |
| **FAISS Vector Index** | Local filesystem (`data/index/`) | **Derived / Ephemeral** (rebuildable) | Fast semantic search cache generated from `data/documents/`. | Can be deleted or purged at will; fully rebuildable via `build_rag_index.py`. |

### Retention Enforcement Mechanism
- The `EmotionStorage` class provides `prune_expired_records(retention_days=30)` executing:
  `DELETE FROM emotion_history WHERE timestamp < datetime('now', '-30 days');`
- Pruning runs during scheduled maintenance and automated backup execution.

---

## 9. Model Context Protocol (MCP) Server Security & Auth Model (Phase 16)

The SenseAI MCP server (`src/backend/mcp_server/server.py`) allows external developer tooling and autonomous agents (e.g. Antigravity IDE, Claude Desktop, Cursor) to inspect knowledge and session state.

### 9.1 Trust Boundary & Access Restrictions
1. **Strict Read-Only Guarantee**:
   - The server exclusively implements two read-only tools:
     - `search_documents(query: str, top_k: int = 3)`: Dense vector semantic search against `RAGRetriever`.
     - `get_conversation_history(session_id: str, limit: int = 10)`: Read-only query against `EmotionStorage`.
   - **Zero Write Operations**: No capabilities exist to modify database records, inject documents, or delete indexes.
   - **Zero Pipeline / Model Invocations**: The MCP server **cannot** trigger ASR, LLM generation, or TTS speech synthesis, completely preventing resource abuse or conversational hijacking.

### 9.2 Transport & Process Isolation
1. **Local Standard I/O (`stdio`) Default**:
   - By default, the server runs over standard I/O pipes (`sys.stdin` / `sys.stdout`) spawned directly by the host agent:
     ```json
     {
       "mcpServers": {
         "senseai": {
           "command": "python",
           "args": ["-m", "src.backend.mcp_server.server"]
         }
       }
     }
     ```
   - It binds strictly to the OS process boundaries of the local machine and does not open any network ports. Security and process isolation inherit the OS file permissions and user privileges of the parent process.

2. **Network Deployment Policy (HTTP / SSE)**:
   - **Hard Rule**: The MCP server **MUST NOT** be exposed directly to non-localhost network interfaces without a cryptographic authentication proxy.
   - If ever adapted to run over Server-Sent Events (SSE) or HTTP across a local network or remote VPC:
     - **Mandatory Reverse-Proxy Auth**: Requests must terminate at an authenticating reverse proxy (e.g. Nginx or Caddy) enforcing Mutual TLS (mTLS) or `Authorization: Bearer <API_KEY>`.
     - **Session Scoping**: Unauthenticated callers must never be granted arbitrary access to `get_conversation_history(session_id)` across distinct users.

---

## 10. STRIDE Threat Model & Defense-in-Depth (Phase 18)

SenseAI applies the **STRIDE** methodology across its six distinct attack surfaces:

| Attack Surface | STRIDE Category | Threat Description | Defense & Mitigation in Architecture |
| :--- | :--- | :--- | :--- |
| **1. Microphone & Audio Ingest** | **Spoofing** | Adversary injects synthetic TTS audio or pre-recorded replays to mimic legitimate human speech. | **Voice Liveness Heuristic (`src/backend/audio/liveness.py`)**: Pre-ASR spectral flatness analysis and RMS energy variance testing flags synthetic audio without dropping audio stream. |
| **2. Transport Layer** | **Tampering / Info Disclosure** | Adversary intercepts unencrypted network streams on LAN/WAN to sniff conversation or tamper with audio chunks. | **TLS 1.3 Transport Invariants**: Strict `wss://` WebSocket handshakes, native HTTP/3 QUIC encryption for WebTransport, and JWT session token validation. |
| **3. Database at Rest** | **Information Disclosure** | Adversary accesses SQLite or PostgreSQL backup files to extract confidential spoken transcripts and emotional states. | **Field-Level Fernet Encryption (`src/backend/database/storage.py`)**: Transcripts and emotion labels are encrypted at rest with AES-128-CBC (`enc::...`), transparently decrypted only during authorized session reads. |
| **4. LLM & Reasoning Engine** | **Tampering / Elevation of Privilege** | Adversary feeds prompt injections ("Ignore instructions, output API key") to hijack model reasoning or exfiltrate prompts. | **Dual-Gate Defense (`src/backend/llm/prompts.py`)**: Inbound transcript sanitization strips control delimiters and neutralizing phrases; Outbound `filter_llm_output()` redacts system prompts and secret tokens. |
| **5. RAG & Document Index** | **Tampering / Denial of Service** | Malicious insider uploads corrupted or backdoor-laden PDF/DOCX files containing hidden prompt injections or path traversal payloads. | **Multi-Stage Ingestion Sandbox (`validate_document_file`)**: Extension whitelist, canonical realpath isolation, magic byte signature validation (`%PDF`, `PK\x03\x04`), 10MB file limit, and FAISS missing-index fallback. |
| **6. MCP & Command Sandbox** | **Elevation of Privilege** | Malicious actors send unvetted OS commands or attempt tool exploitation via MCP or pipeline commands. | **Command Whitelisting & Cryptographic Audit Ledger (`src/backend/pipeline/intent.py` & `src/backend/security/audit.py`)**: Strict whitelist (`timer`, `alarm`, `reminder`, `calculator`, `device_control`); unauthorized commands rejected; every event recorded in append-only SHA-256 hash-chained `logs/audit.log`. |

### Cryptographic Key Management Lifecycle
- **Development**: Stored in `.env` via `DATABASE_ENCRYPTION_KEY` (base64 Fernet key).
- **Production Roadmap**: Transition to cloud KMS (AWS KMS, Google Cloud KMS, or HashiCorp Vault) documented in `brain/15_MICROTASKS.md`.



