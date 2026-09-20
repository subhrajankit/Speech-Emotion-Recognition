# SenseAI Voice Assistant — Deployment Guide (Phase 12)

This guide covers deployment strategies for the SenseAI Voice Assistant across three tiers:
1. **Local Development** (Bare-metal processes)
2. **Single-Machine Demo Deployment** (All-in-one Docker Compose)
3. **GPU-Server Production Architecture** (Decoupled CPU web/backend tier + dedicated GPU model-serving host)

---

## 1. Local Development (Bare Metal)

Best for active code editing, testing, and debugging.

### Step 1: Start LLM Inference Server (llama.cpp)
```bash
# Windows
.\llama-server.exe -m .\models\qwen3-1.7b.gguf --host 127.0.0.1 --port 8080 -ngl 33 -c 4096

# Linux / macOS
./llama-server -m ./models/qwen3-1.7b.gguf --host 127.0.0.1 --port 8080 -ngl 33 -c 4096
```

### Step 2: Start FastAPI Backend
```bash
# Activate virtual environment
source .venv/bin/activate  # Linux
# .\.venv\Scripts\Activate.ps1  # Windows

# Launch with hot-reload
uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 3: Start React Frontend
```bash
cd src/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Access the UI at `http://127.0.0.1:5173`.

---

## 2. Single-Machine Demo Deployment (Docker Compose)

Best for staging, client demonstrations, and self-hosted on-premise servers with an attached NVIDIA GPU.

### Prerequisites
- Docker Engine 24+ with Docker Compose v2
- NVIDIA Container Toolkit (`nvidia-container-toolkit`) installed and configured with the Docker daemon if GPU acceleration is enabled.

### Running with Docker Compose
```bash
# 1. Ensure production secrets are populated
cp security/secrets.example/env.secrets.example .env
chmod 600 .env

# 2. Build and launch all services in detached mode
docker compose -f docker-compose.prod.yml up -d --build

# 3. View container logs
docker compose -f docker-compose.prod.yml logs -f
```

### Verification
```bash
# Verify container health
docker compose -f docker-compose.prod.yml ps

# Execute operational health audit
python monitoring/health-checks/check_health.py
```

---

## 3. GPU-Server Production Architecture (Decoupled Topology)

In production environments with variable traffic, running all services on a single monolithic GPU instance is financially inefficient and operationally risky.

### Decoupled Service Topology

```text
+-------------------------------------------------------------+
|                      INTERNET INGRESS                       |
|           Cloudflare / TLS Reverse Proxy (Port 443)         |
+------------------------------+------------------------------+
                               |
                               ▼
+-------------------------------------------------------------+
|                TIER 1: WEB & PIPELINE HOST                  |
|          (Low-Cost CPU Instance: 2-4 vCPUs, 8GB RAM)        |
|                                                             |
|   +--------------------------+  +-----------------------+   |
|   |   Frontend Container     |  |   Backend Container   |   |
|   |   (Nginx Alpine:80)      |  |   (FastAPI:8000)      |   |
|   +-------------+------------+  +-----------+-----------+   |
|                 |                           |               |
|                 +---------------------------+               |
|                                             |               |
|                        +--------------------+-------+       |
|                        | PostgreSQL (Port 5432)     |       |
|                        +----------------------------+       |
+--------------------------------------|----------------------+
                                       | Private VPC / WireGuard
                                       | (Port 8080 Internal Only)
                                       ▼
+-------------------------------------------------------------+
|             TIER 2: DEDICATED GPU INFERENCE HOST            |
|       (Cloud GPU Instance: NVIDIA A10G / L4 / RTX 4090)     |
|                                                             |
|   +-----------------------------------------------------+   |
|   |  llm-server Container (llama.cpp CUDA server:8080)  |   |
|   |  - Quantized Qwen3-1.7B / IndicConformer / TTS      |   |
|   +-----------------------------------------------------+   |
+-------------------------------------------------------------+
```

### Configuration
1. **On the GPU Inference Host**:
   Run only the `llm-server` service:
   ```bash
   docker run -d \
     --name senseai-llm-prod \
     --gpus all \
     -p 10.0.1.5:8080:8080 \
     -v /opt/models:/models:ro \
     ghcr.io/ggerganov/llama.cpp:server-cuda \
     -m /models/qwen3-1.7b.gguf --host 0.0.0.0 --port 8080 -c 4096 -ngl 33
   ```
2. **On the Web & Pipeline Host**:
   Configure `.env`:
   ```dotenv
   LLAMA_CPP_URL=http://10.0.1.5:8080/v1
   REQUIRE_AUTH=true
   MOCK_MODELS=false
   DATABASE_URL=postgresql://senseai:password@db:5432/senseai_prod
   ```
   Start frontend and backend containers:
   ```bash
   docker compose -f docker-compose.prod.yml up -d backend frontend db
   ```

---

## 4. Critical Cloud Cost Reality: GPU Hosting is NOT Free

> [!CAUTION]
> **Open Source Software ≠ Free Cloud Compute**
> 
> The entire SenseAI software stack (FastAPI, React, Silero VAD, SenseVoice, IndicConformer, Qwen3, Indic Parler-TTS) is 100% open-source with zero software licensing fees.
> 
> **However, dedicated cloud GPU hosting requires substantial real-money operational expenditure (OpEx).**

### Typical Cloud GPU Hourly Rates (2026 Baseline)
| GPU Model | Dedicated VRAM | Provider Example | Hourly Cost | Monthly Cost (24/7) |
| :--- | :--- | :--- | :--- | :--- |
| **NVIDIA T4** | 16 GB GDDR6 | AWS (g4dn.xlarge) / GCP | ~$0.52 / hr | **~$380 / month** |
| **NVIDIA L4** | 24 GB GDDR6 | GCP (g2-standard-4) | ~$0.70 / hr | **~$510 / month** |
| **NVIDIA A10G** | 24 GB GDDR6 | AWS (g5.xlarge) | ~$1.01 / hr | **~$730 / month** |
| **RTX 4090** | 24 GB GDDR6X | RunPod / Lambda / Vast.ai | ~$0.35–$0.50 / hr | **~$260–$360 / month** |

### Recommended Cost Optimization Strategies
1. **Decoupled Tiering**: Never run web/frontend servers on GPU instances. Keep the web tier on a $10–$20/month basic CPU droplet/VPS.
2. **Spot / Preemptible Instances**: For non-critical internal demos, spot GPU instances reduce hourly rates by 60–70%.
3. **Auto-Shutdown / Idle Scale-to-Zero**: If the voice assistant is used during business hours (e.g. 9 AM – 6 PM), schedule the GPU instance to stop at night, saving ~65% of monthly hosting costs.
4. **Local Hardware for Fixed Workloads**: For enterprise deployments with predictable physical presence, purchasing a dedicated on-premise workstation with an RTX 4080/4090 ($1,500 one-time CapEx) pays for itself in less than 3 months compared to cloud GPU rentals.

---

## 5. Network Security & Firewall Invariants

- **Zero Public GPU Access**: Port 8080 (`llm-server`) must NEVER be exposed to the public internet (`0.0.0.0:8080` without auth). It must bind to `127.0.0.1` only or be accessible strictly across a private VPC/WireGuard network.
- **Port 80/443 Only**: Public traffic enters exclusively through TLS-terminating reverse proxies (Nginx / Caddy / Cloudflare).
- **Transport Layer Encryption (WSS & HTTP/3 QUIC)**:
  - **WebSocket Handshake**: Production environments strictly mandate `wss://` (WebSocket Secure over TLS 1.3). Plaintext `ws://` is prohibited and rejected.
  - **WebTransport over HTTP/3**: WebTransport connections utilize UDP-based QUIC, which natively mandates and embeds **TLS 1.3** forward-secret handshake negotiation. No plaintext WebTransport fallback is permitted.
  - **Field-Level Encryption at Rest**: SQLite/Postgres stores sensitive transcript and emotion fields encrypted with AES-128-CBC (`DATABASE_ENCRYPTION_KEY`).
  - **WebSocket Timeout Configuration**: Reverse proxies must configure `proxy_read_timeout 3600s;` and `proxy_send_timeout 3600s;` to prevent premature disconnection during idle voice turns.
