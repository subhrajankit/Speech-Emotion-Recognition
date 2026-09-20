# SenseAI Setup & Local Execution Guide (Phase 1)

This guide walks you through setting up and running the **Phase 1 Minimum Voice Loop** (SenseVoiceSmall ASR → llama.cpp / Qwen3-1.7B → Indic Parler-TTS) locally on Windows and Linux.

---

## Prerequisites

1. **Python**: 3.10 to 3.12 (or 3.13)
2. **Node.js**: v18+ and npm
3. **Hardware**: 
   - **Recommended**: NVIDIA GPU (≥ 4GB VRAM, e.g. RTX 2050/3050) with CUDA 12+
   - **Supported**: CPU-only mode (quantized inference)

---

## 1. Local LLM Setup (llama.cpp)

SenseAI connects to a locally hosted `llama.cpp` server exposing OpenAI-compatible endpoints (`/v1/chat/completions`) bound strictly to `127.0.0.1:8080`.

### Option A: Using Pre-built llama.cpp Binary (Windows / Linux)
1. Download the latest `llama-server` binary from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases).
2. Download the Qwen3-1.7B (or Qwen2.5-1.5B) Q4_K_M GGUF model:
   ```bash
   mkdir -p models
   # Example download via huggingface-cli:
   huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF qwen2.5-1.5b-instruct-q4_k_m.gguf --local-dir ./models
   ```
3. Start the llama.cpp server:
   - **Windows (PowerShell)**:
     ```powershell
     .\llama-server.exe -m .\models\qwen2.5-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -ngl 33 -c 4096
     ```
   - **Linux**:
     ```bash
     ./llama-server -m ./models/qwen2.5-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -ngl 33 -c 4096
     ```


---

## 2. Backend Setup (FastAPI)

### Step 2.1: Python Virtual Environment
- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```
- **Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### Step 2.2: Install Dependencies
```bash
pip install -r src/backend/requirements.txt
```

For GPU acceleration (PyTorch with CUDA 12.1+):
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install funasr transformers soundfile
```

### Step 2.3: Environment Configuration
Copy the development environment file:
```bash
cp config/development/.env.example .env
```
*(Or on Windows PowerShell: `Copy-Item config\development\.env.example .env`)*

### Step 2.4: Launch Backend Server
```bash
python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Verify health:
```bash
curl http://127.0.0.1:8000/health
```

---

## 3. Frontend Setup (React + Vite)

### Step 3.1: Install Dependencies
```bash
cd src/frontend
npm install
```

### Step 3.2: Launch Frontend Development Server
```bash
npm run dev
```
The interface will be live at: `http://127.0.0.1:5173`.

---

## 4. How to Test Manually (Smoke Test)

1. Open `http://127.0.0.1:5173` in Chrome or Edge.
2. Check the status badge at top right: should indicate **127.0.0.1:8000 Online**.
3. Click the glowing **Microphone Button** (browser will prompt for microphone permission).
4. Speak a clear English sentence (e.g.: *"Hello, what is the capital of France?"*).
5. Click the button again to signal end of utterance.
6. Observe:
   - Status changes to **Processing speech...**.
   - Your speech appears in the **User Speech** card.
   - The LLM text response appears in the **Assistant Speech** card.
   - The returned WAV audio automatically plays through your speakers.
   - The latency bar reports component timings (`ASR`, `LLM`, `TTS`, and `Roundtrip`).

---

## 5. Expected Latency Benchmarks (Roundtrip)

| Hardware Setup | ASR (SenseVoice) | LLM (Qwen3-1.7B) | TTS (Parler-TTS) | Total Roundtrip |
| :--- | :--- | :--- | :--- | :--- |
| **NVIDIA RTX 3080/4070 (GPU)** | ~80–120 ms | ~100–160 ms | ~200–300 ms | **~450–650 ms** |
| **Entry GPU (RTX 2050 / 4GB VRAM)** | ~100–150 ms | ~130–190 ms | ~260–380 ms | **~550–750 ms** |
| **Mid-tier GPU (RTX 3060/4060)**| ~120–160 ms | ~140–220 ms | ~300–450 ms | **~600–850 ms** |
| **Modern 8-Core CPU** | ~280–400 ms | ~250–450 ms | ~600–900 ms | **~1150–1750 ms** |

