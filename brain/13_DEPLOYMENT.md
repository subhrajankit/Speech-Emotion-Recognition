# SenseAI Voice Assistant — Deployment Architecture & Reverse-Proxy Guide

## 1. Overview & Transport Architecture

SenseAI utilizes a **Dual-Transport Architecture**:
1. **Primary Transport**: **WebTransport (HTTP/3 over QUIC)** for multiplexed, low-latency streaming across dedicated uni- and bidirectional streams:
   - **Stream A (Client -> Server)**: 16kHz PCM16 audio chunks feeding Silero VAD.
   - **Stream B (Bidirectional)**: JSON control frames (`ping`/`pong`, `reset`, `end-of-utterance`).
   - **Stream C (Server -> Client)**: Transcripts, sentence start/end events, and turn completions.
   - **Stream D (Server -> Client)**: Binary synthesized WAV audio frames.
   - **Datagrams (Unreliable)**: Low-latency affective telemetry (`emotion`, `valence`, `arousal`, `latencies`).
2. **Fallback Transport**: **WebSocket (`/ws/voice`)** over standard HTTP/1.1 or HTTP/2 TLS. Automatic, transparent failover if WebTransport handshake or proxy fails.

---

## 2. Reverse-Proxy Implications & Known Deployment Risks

> [!WARNING]
> **Known Deployment Risk: WebTransport / HTTP/3 Reverse Proxying**
> Unlike HTTP/1.1 and WebSockets (which run over standard TCP and work seamlessly behind traditional reverse proxies), WebTransport relies on **HTTP/3 over UDP (QUIC)**.
> - **UDP Port 443 Routing**: Firewalls, cloud security groups (AWS SG, GCP firewall rules, Azure NSG), and enterprise NATs frequently block or throttle UDP traffic on port 443.
> - **TLS / Certificate Constraints**: WebTransport strictly enforces TLS 1.3 encryption. Self-signed certificates fail in modern browsers unless `serverCertificateHashes` are explicitly pre-computed and provided to the JavaScript client.
> - **Proxy Software Support**: Traditional stable Nginx (pre-1.25) does not support QUIC or HTTP/3 proxying. Even in modern Nginx versions, QUIC proxying requires explicit compilation flags and specialized configuration directives.

Because of these network and proxy constraints, **the WebSocket transport path is not a temporary shim; it is a permanent, fully maintained production fallback**. The frontend client automatically tests WebTransport connectivity and transparently falls back to WebSocket within milliseconds if QUIC is unreachable.

---

## 3. Reverse Proxy Configuration Examples

### A. Nginx (Version 1.25+ with `ngx_http_v3_module`)

```nginx
# HTTP/3 QUIC and HTTP/1.1 + WebSocket Reverse Proxy Configuration

server {
    # Listen on both TCP (HTTP/1.1, HTTP/2, WebSocket) and UDP (HTTP/3 QUIC)
    listen 443 ssl;
    listen 443 quic reuseport;
    server_name voice.senseai.local;

    # TLS 1.3 is strictly required for HTTP/3 and WebTransport
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_certificate /etc/ssl/certs/senseai.crt;
    ssl_certificate_key /etc/ssl/private/senseai.key;

    # Advertise HTTP/3 support via Alt-Svc response header
    add_header Alt-Svc 'h3=":443"; ma=86400';
    add_header QUIC-Status $http3;

    # 1. WebTransport Endpoint
    location /wt {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # 2. WebSocket Fallback Endpoint
    location /ws/voice {
        proxy_pass http://127.0.0.1:8000/ws/voice;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # 3. REST API & Health Checks
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### B. Caddy Server (Native HTTP/3 Support)

Caddy includes zero-configuration HTTP/3 support enabled by default:

```caddy
voice.senseai.local {
    # Caddy automatically binds to UDP 443 for HTTP/3 and issues Alt-Svc headers
    reverse_proxy localhost:8000
}
```

### C. Cloudflare & Edge CDNs

If deploying behind Cloudflare:
- Ensure **Network -> HTTP/3 (with QUIC)** is toggled **ON** in the Cloudflare dashboard.
- WebSockets must also be enabled (**Network -> WebSockets: ON**).
- Note: Cloudflare terminates QUIC at the edge and proxies to origin servers over TCP unless Cloudflare gRPC/Origin QUIC tunnels are configured. Origin fallback to `/ws/voice` ensures reliability across all edge regions.

---

## 4. Local Deployment & Smoke Testing

1. **Backend Server**:
   ```bash
   uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
   ```
2. **Frontend Dev Server**:
   ```bash
   npm run dev -- --host 127.0.0.1 --port 5173
   ```
3. **Transport Capabilities Verification**:
   ```bash
   curl http://127.0.0.1:8000/api/transport/capabilities
   ```
   Expected response:
   ```json
   {
     "webtransport": true,
     "websocket": true,
     "protocols": ["webtransport", "websocket"],
     "streams": { ... },
     "datagrams": { "supported": true }
   }
   ```
4. **Behavior on Localhost**:
   - In browser environments without pre-trusted local QUIC TLS certs, `new WebTransport('https://127.0.0.1:8000/wt')` rejects during the handshake.
   - The frontend immediately intercepts the rejection, logs `[Transport] WebTransport handshake failed (TLS/QUIC unavailable). Transparently falling back to WebSocket:`, and connects to `ws://127.0.0.1:8000/ws/voice`.
   - The UI displays the status pill: `WebSocket (Fallback)` and functions with 100% full streaming fidelity.
