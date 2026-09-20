# Runbook: Deployment Failure

**Target System:** SenseAI Containerized Production Stack (`docker-compose.prod.yml`)  
**Severity:** Critical / High  
**Last Updated:** Phase 12 Docker & Deployment

---

## 1. Overview

This runbook provides diagnostic and recovery procedures for failures occurring during container build, deployment, or startup of the SenseAI production stack:
`llm-server` (llama.cpp CUDA) | `backend` (FastAPI) | `frontend` (Nginx) | `db` (PostgreSQL).

---

## 2. Common Symptoms & Failure Signatures

| Failure Symptom | Error Signature in Logs | Primary Root Cause |
| :--- | :--- | :--- |
| **GPU Driver Initialization Failure** | `docker: Error response from daemon: could not select device driver "" with capabilities: [[gpu]]` | NVIDIA Container Toolkit not installed or Docker daemon not configured with `nvidia` runtime. |
| **Port Collision** | `Bind for 0.0.0.0:8000 failed: port is already allocated` or `Errno 10048` | Host has an active local process (e.g. earlier uvicorn or llama-server) bound to port 80, 8000, 8080, or 5432. |
| **Container OOM Killed (Exit 137)** | `senseai-backend-prod exited with code 137` | Container memory limit exceeded during model loading or PyTorch allocation. |
| **Database Connection Refusal** | `sqlalchemy.exc.OperationalError: could not connect to server: Connection refused (db:5432)` | Backend container started before PostgreSQL completed initialization or incorrect credentials. |
| **Unhealthy Container Status** | `senseai-backend-prod (unhealthy)` | `/health` endpoint failing, models taking longer than `start-period` (10s) to initialize, or missing volume mount. |

---

## 3. Step-by-Step Diagnostic Procedures

### Step 1: Check Container Status
```bash
docker compose -f docker-compose.prod.yml ps
```
Identify containers with state `Exited (1)`, `Exited (137)`, or `(unhealthy)`.

### Step 2: Inspect Container Logs
```bash
# Backend logs
docker compose -f docker-compose.prod.yml logs --tail=100 backend

# LLM server logs
docker compose -f docker-compose.prod.yml logs --tail=100 llm-server

# Database logs
docker compose -f docker-compose.prod.yml logs --tail=100 db
```

### Step 3: Verify GPU Availability
On the host machine:
```bash
nvidia-smi
```
Verify:
- GPU is detected.
- Sufficient VRAM available (minimum 2.5GB for Qwen3-1.7B + context).
- No stale zombie processes consuming VRAM.

### Step 4: Verify Host Port Availability
- **Linux:**
  ```bash
  sudo netstat -tulpn | grep -E ':(80|8000|8080|5432)'
  ```
- **Windows (PowerShell):**
  ```powershell
  Get-NetTCPConnection -LocalPort 80, 8000, 8080, 5432 -ErrorAction SilentlyContinue
  ```

---

## 4. Remediation Steps

### Scenario A: Resolving NVIDIA Container Driver Errors
If Docker cannot find the NVIDIA runtime:
1. Verify toolkit installation:
   ```bash
   nvidia-ctk --version
   ```
2. Re-register NVIDIA runtime with Docker:
   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
3. Test GPU access inside Docker:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
   ```

### Scenario B: Resolving Port Collisions
1. Terminate conflicting host processes:
   - **Linux:** `sudo fuser -k 8000/tcp`
   - **Windows:** `Stop-Process -Id <PID> -Force`
2. Or remap host ports in `docker-compose.prod.yml`:
   ```yaml
   ports:
     - "127.0.0.1:8001:8000"
   ```

### Scenario C: Resolving Database Readiness Race Conditions
If backend crashes because PostgreSQL takes 5–10 seconds to create tables:
1. Ensure `depends_on` in `docker-compose.prod.yml` uses condition checks:
   ```yaml
   depends_on:
     db:
       condition: service_healthy
   ```
2. Add healthcheck to `db` service:
   ```yaml
   healthcheck:
     test: ["CMD-SHELL", "pg_isready -U senseai -d senseai_prod"]
     interval: 5s
     timeout: 5s
     retries: 5
   ```

### Scenario D: Resolving OOM Memory Spikes
1. Reduce LLM context length in `docker-compose.prod.yml`:
   Change `-c 4096` to `-c 2048`.
2. Ensure GPU offloading does not exceed physical VRAM:
   Reduce `-ngl 33` to `-ngl 20` or `-ngl 16`.
