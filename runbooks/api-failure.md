# Runbook: API & Pipeline Failure

**Target System:** SenseAI FastAPI Backend & Model Serving Pipeline  
**Severity:** Critical / High (End-to-end voice loop degraded or offline)  
**Last Updated:** Phase 11 Security Hardening

---

## 1. Overview & Architecture Context

The SenseAI backend orchestrates a multi-stage real-time pipeline:
`Audio In` → `Silero VAD` → `Language Router (SenseVoice / IndicConformer)` → `SER Emotion & Lexicon Analysis` → `Intent Router` → `Qwen3 LLM (llama.cpp)` → `Indic Parler-TTS` → `Client Stream`.

An API or pipeline failure occurs when any component in this chain fails to initialize, encounters an unhandled exception, times out, or triggers resource limits.

---

## 2. Symptoms

### Client-Side Symptoms
- WebSocket receives `{"type": "error", "error_code": "...", "message": "..."}`.
- Connection is aborted during active streaming.
- Rate limit alerts:
  - `RATE_LIMIT_EXCEEDED`: User exceeded 20 utterances/minute.
  - `AUDIO_DURATION_LIMIT_EXCEEDED`: Speech segment exceeded 30.0 seconds.
- Voice response stops mid-sentence or never arrives after transcription.

### Server-Side Symptoms
- `/health` returns `status: "degraded"` or HTTP 503.
- `llm_ready: false` or `vad_ready: false` in `/health` payload.
- Backend console logs `TimeoutError: llama.cpp server timed out after 30.0s`.
- Process crashes with CUDA Out of Memory (OOM) or high RSS memory spikes.

---

## 3. Diagnostic Procedures

### Step 1: Execute Automated Health Check
Run the Phase 10 operational health verification script:
```bash
python monitoring/health-checks/check_health.py
```
Or on Windows PowerShell:
```powershell
.\monitoring\health-checks\check_health.ps1
```

Review the output table:
- **Server HTTP**: Is port 8000 reachable?
- **VAD / ASR / Router**: Are local models loaded?
- **llama.cpp Server**: Is port 8080 active and responding to `/v1/models`?

### Step 2: Check llama.cpp Model Server Process
If LLM generation fails or times out:
- **Windows:**
  ```powershell
  Get-Process -Name llama-server -ErrorAction SilentlyContinue
  Test-NetConnection -ComputerName 127.0.0.1 -Port 8080
  ```
- **Linux:**
  ```bash
  ps aux | grep llama-server
  curl -s http://127.0.0.1:8080/v1/models
  ```

### Step 3: Inspect Backend Logs
```bash
tail -n 100 logs/senseai.log
```
Look for error signatures:
- `ERROR [senseai.backend]: Unexpected error in /ws/voice connection`
- `ERROR [senseai.llm]: LLM call failed: ...`
- `[SECURITY] Rate limit exceeded for session ...`

---

## 4. Root Causes & Remediation

### Scenario A: llama.cpp Server Crash / Not Running
**Cause:** Process terminated due to OOM or was not started prior to backend.  
**Fix:**
1. Relaunch llama-server binding strictly to `127.0.0.1`:
   ```bash
   llama-server -m models/qwen3-1.7b.gguf --host 127.0.0.1 --port 8080 -c 4096 -ngl 33
   ```
2. Verify connectivity:
   ```bash
   curl http://127.0.0.1:8080/v1/models
   ```

### Scenario B: Session Rate Limit Tripped
**Cause:** Client flooded server with more than 20 utterances in 60s, or speech buffer exceeded 30s.  
**Fix:**
1. Wait 60 seconds for sliding window to decay.
2. If testing automated stress suites, configure higher thresholds in `.env`:
   ```dotenv
   RATE_LIMIT_UTTERANCES_PER_MINUTE=60
   MAX_UTTERANCE_DURATION_SECONDS=60.0
   ```
3. Restart backend.

### Scenario C: VRAM Exhaustion / CUDA OOM
**Cause:** Shared VRAM capacity (4GB on RTX 2050) exceeded by concurrent model weights.  
**Fix:**
1. Verify LLM layers offloaded to GPU in `llama-server` command (reduce `-ngl 33` to `-ngl 24` or `-ngl 16` to leave headroom for TTS).
2. Ensure `SENSEVOICE_DEVICE=cpu` and `PARLER_TTS_DEVICE=cpu` in `.env` if VRAM is constrained.

### Scenario D: Corrupted FAISS Vector Index (RAG Error)
**Cause:** `data/index/` files missing or incompatible embedding dimensions.  
**Fix:**
1. Re-run document ingestion and index builder:
   ```bash
   python scripts/database/build_rag_index.py --mock
   ```
2. Verify `data/index/index.faiss` and `chunks.json` are created.

### Scenario E: Emergency Fallback Mode (Mock Mode)
If physical model weights are unavailable or GPU drivers are unresponsive:
1. Enable mock models in `.env`:
   ```dotenv
   MOCK_MODELS=true
   ```
2. Restart backend:
   ```bash
   python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
   ```
3. Full pipeline will respond with deterministic test responses.
