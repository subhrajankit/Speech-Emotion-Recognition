# Runbook: Authentication Failure (WebSocket & WebTransport)

**Target System:** SenseAI Voice Assistant Transport Layer  
**Severity:** High (Prevents voice session establishment)  
**Last Updated:** Phase 11 Security Hardening

---

## 1. Overview & Failure Modes

SenseAI enforces HMAC-SHA256 JWT access authentication on all real-time voice streaming connections (WebSocket `/ws/voice` and WebTransport `/wt`) when `REQUIRE_AUTH=true`.

If authentication fails during the connection handshake, the server terminates the connection immediately with RFC 6455 close code **1008** (Policy Violation).

---

## 2. Symptoms

### Client-Side Symptoms
- WebSocket closes immediately after connection initiation with close code `1008`.
- WebSocket error reason string:
  - `"Authentication required: token missing"`
  - `"Authentication failed: Token signature verification failed"`
  - `"Authentication failed: Token has expired"`
  - `"Authentication failed: Token is not yet active (nbf check failed)"`
  - `"Authentication failed: Unsupported algorithm 'none': only HS256 is permitted"`
- Frontend microphone UI shows "Disconnected" or "Connection Rejected".
- Dev benchmark dashboard reports 0 active streaming sessions.

### Server-Side Log Signatures
- `WARNING [senseai.transport.websocket]: Rejecting WebSocket connection: missing 'token' query parameter.`
- `WARNING [senseai.transport.websocket]: Rejecting WebSocket connection due to invalid token: Token signature verification failed`
- `WARNING [senseai.transport.websocket]: Rejecting WebSocket connection due to invalid token: Token has expired`

---

## 3. Root Causes & Diagnostics

| Root Cause | Diagnostic Method |
| :--- | :--- |
| **Missing Token Query Parameter** | Check browser Network tab or client connection URL: verify query string includes `?token=<JWT>`. |
| **Expired Token** | Decode JWT payload (`base64url` decode payload segment) or test via `POST /api/auth/verify`: check if `exp` < current epoch timestamp. |
| **Secret Key Mismatch** | Verify if the backend server was restarted with a new or rotated `JWT_SECRET` while the client is using an old token. |
| **Clock Skew / NTP Drift** | If client and server host clocks differ by > 10 seconds, `nbf` or `exp` validations will fail. |
| **Tampered / Malformed Token** | Token string does not contain exactly three period-delimited segments (`header.payload.sig`) or signature does not match payload with `JWT_SECRET`. |

---

## 4. Verification Procedures

### Verify Token with Backend API
Run an interactive verification call against the local auth verification endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"token": "YOUR_SUSPECT_JWT_HERE"}'
```

- If valid: returns `{"valid": true, "claims": {"sub": "...", ...}}`.
- If invalid: returns `{"valid": false, "error": "<reason>"}`.

### Request Fresh Access Token
```bash
curl -X POST http://127.0.0.1:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"session_id": "operator_debug_session", "client_id": "cli"}'
```

---

## 5. Remediation & Recovery Steps

### Step 1: Force Client Token Renewal
If the client token has expired (default lifetime: 60 minutes), instruct the frontend to obtain a fresh token:
1. Hit `POST /api/auth/token`.
2. Append the new token: `ws://127.0.0.1:8000/ws/voice?token=${newToken}`.

### Step 2: Harmonize `JWT_SECRET`
Ensure the backend server environment has a consistent `JWT_SECRET` configured:
```bash
# Check current configured secret in .env
grep JWT_SECRET .env
```
Ensure no mismatch between multiple worker processes.

### Step 3: Synchronize System Clocks
Ensure server system clock is synced via NTP:
- **Windows:**
  ```powershell
  w32tm /resync
  ```
- **Linux:**
  ```bash
  sudo systemctl restart systemd-timesyncd
  timedatectl status
  ```

### Step 4: Emergency Break-Glass (Temporary Recovery)
If an unexpected key rotation breaks clients and voice service must be restored immediately during an outage:
1. Set `REQUIRE_AUTH=false` in `.env`.
2. Restart backend:
   ```bash
   python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
   ```
3. Connections will be accepted with fallback anonymous session IDs.
4. Investigate and re-enable `REQUIRE_AUTH=true` once keys are aligned.
