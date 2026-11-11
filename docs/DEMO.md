# VoiceSense AI — 10-Step Live Demo Script

This walkthrough demonstrates VoiceSense AI's verified capabilities (multilingual ASR, emotion/event reporting, intent-gated RAG, failure isolation, privacy guarantees, and optional authentication/history).

---

## Pre-Flight Checklist

1. **Backend & Frontend Running Locally:**
   - Backend: `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --ws-ping-interval 20 --ws-ping-timeout 20`
   - Frontend: `cd frontend && npm run dev` (`http://127.0.0.1:5173`)
   - Optional local LLM: `llama-server -m <path-to-qwen3-1.7b-q4_k_m.gguf> --host 127.0.0.1 --port 8080 -ngl 24`
2. **RAG Index Built (if showing grounded citations):**
   - `.venv\Scripts\python.exe -m rag.ingestion --docs data/documents --index-dir data/index`

---

## Demo Sequence

| Step | Action | Expected Output | Fallback Talking Point (If Component Offline) |
|---|---|---|---|
| **1. Health Verification** | Open `http://127.0.0.1:8000/api/health` (or run `curl.exe http://127.0.0.1:8000/api/health`). | JSON showing component states (`asr`, `emotion`, `llm`, `rag`, `tts`, `db`). `tts` displays `"disabled"`. | Even if `llm` reports degraded/unavailable, point out overall HTTP `200` and isolated ASR/emotion availability. |
| **2. Voice Replies Disabled Notice** | Open `http://127.0.0.1:5173` and inspect the dashboard response panel. | Audio playback controls are hidden; banner states **"Voice replies are off on this server"**. | Explain `TTS_ENABLED=false` protects the 4 GB RTX 2050 VRAM budget and Windows commit limit (`os error 1455` avoidance). |
| **3. Cold Model Load UX** | Click the microphone button and speak a first English sentence with `LAZY_LOAD_MODELS=true`. | UI shows `"Loading speech model (first use can take 30 s)..."` on `{"type":"status","state":"loading_model"}` and clears on `"model_ready"`. WebSocket stays connected without ping drops. | If `SenseVoiceSmall` is already warm, note subsequent turns skip the loading state cleanly. |
| **4. English ASR + Emotion + Chat** | Ask a conversational question in English (e.g., *"Hello, how are you today?"*). | `speech_result` returns English transcript, `language: "en"`, detected `emotion` (e.g., `neutral`/`happy`), `confidence: "-"` in UI (`null` in JSON). LLM streams `llm_delta` tokens directly without touching RAG. | Explain SenseVoiceSmall uses greedy discrete emotion tags (`confidence: null` avoids fabricated probabilities) and plain chat skips vector retrieval. |
| **5. Intent-Gated RAG Turn** | Ask a question matching sample knowledge docs (e.g., *"What is the warranty period?"*). | Intent router crosses threshold (`>= 0.70`), emits `rag_sources` citations (`score`, `doc_name`), and LLM answers grounded in retrieved chunks. | If no index exists, show `{"type":"status","status":"rag_fallback"}` graceful degradation back to plain chat. |
| **6. Hindi ASR Turn (Explicit Selector)** | Switch language selector to **Hindi** (`language_hint: "hi"`) and speak in Hindi (or replay `tests/samples/sample_hindi_speech.wav` via `scripts/e2e_real.py`). | Routes to `IndicConformer-600m` (CTC CPU), emits Devanagari Hindi transcript (`"आज मौसम बहुत अच्छा है"` on sample clip), and displays `"-"` (`null`) for emotion and confidence. | Explain Auto (`null`) defaults to SenseVoiceSmall; automatic LID was intentionally not wired after failing on real Hindi audio (`docs/architecture/language-routing.md`). If `HF_TOKEN` is missing for gated IndicConformer weights, cite recorded log `docs/deployment/runs/run_phase10_e2e_real.txt`. |
| **7. Multi-Segment Continuous Utterance** | Speak two sentences separated by > 700 ms pause without clicking Stop. | Silero VAD emits two separate `speech_result` rows (`segment_index` 1 and 2) with independent assistant replies. | Mention 700 ms VAD silence segmentation ensures streaming responsiveness without cutting mid-phrase pauses. |
| **8. Graceful LLM Failure Isolation** | Stop `llama-server` (or unplug LLM port `8080`) and speak another turn. | `speech_result` transcript and emotion still render normally, followed by friendly notice for `llm_unavailable`. Connection remains open. | Demonstrates core architectural invariant: ASR and emotion never depend on LLM/RAG/TTS/DB. |
| **9. Auth & Scoped History (Optional)** | Start with `AUTH_REQUIRED=true` (`VITE_AUTH_REQUIRED=true`), register/login in UI, speak one turn, inspect session drawer, then click purge history. | Token stays in React memory (not `localStorage`), passes as `auth_token` in WebSocket `start`, turns persist async to `sessions`/`predictions`, and **Delete All History** removes all user data. | When demoing with `AUTH_REQUIRED=false`, cite the open-mode session bypass (zero anonymous DB writes) and show [`docs/api/rest.md`](./api/rest.md). |
| **10. Zero Raw Audio Privacy Proof** | Inspect `database/` or logs after all turns. | Zero `.wav` or `.pcm` recordings written to disk; transcripts/emotions persist only for authenticated sessions when `STORE_TRANSCRIPTS=true`. | Emphasize privacy-first in-memory audio buffers capped at 5 MB (`WS_MAX_BUFFER_BYTES`) and 30 s (`MAX_UTTERANCE_DURATION_SECONDS`). |
