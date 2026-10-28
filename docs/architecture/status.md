# VoiceSense AI — System Truth Table & Component Status

> **Generated**: Phase 8i Close-Out (2026-10-28)  
> **Repository Branch**: `migration/voicesense`  
> **Verification Standard**: Strict empirical labeling (`real-verified`, `test-double only`, `not measured`, `known issue`).

---

## 1. Component Status Truth Table

| Component | Status | Evidence File / Commit | Last Verified | Known Limitations & Empirical Facts |
| :--- | :--- | :--- | :--- | :--- |
| **VAD** | `real-verified` | `models/silero_vad.onnx`, `ai/preprocessing/vad.py`, `docs/deployment/runs/ws_english_speech_8i.txt` | 2026-10-28 | 300ms pre-roll window; on `sample_hindi_speech.wav`, acoustic speech onset ~1.18s, segment begins ~0.96s (no VAD cut). |
| **SenseVoice** | `real-verified` | `docs/deployment/runs/cli_english_speech_8i.txt`, `docs/deployment/runs/ws_english_speech_8i.txt` | 2026-10-28 | Model card confirms zh, en, yue, ja, ko support only. Hindi is **NOT** supported. Test clip `english_speech_16k.wav` is synthetic audio transcribing to *"Voice sense A provides multilingual and emotion or air voice systems across 23 in languages."* |
| **IndicConformer** | `real-verified` | `docs/architecture/language-routing.md`, `tests/ai/test_indicconformer.py` | 2026-10-28 | Tested against exactly one authentic human Hindi clip (`sample_hindi_speech.wav`). Connectionist Temporal Classification (`ctc`) configured as default decoder. Strictly requires `language_hint="hi"`. |
| **Language Routing** | `real-verified` | `ai/routing/language_router.py`, `docs/architecture/language-routing.md` | 2026-10-28 | Automatic spoken language identification (LID) is **NOT** wired into runtime. Hindi routing strictly requires `language_hint="hi"`. Default fallback routes to SenseVoice. |
| **Emotion Engine** | `test-double only` | `ai/inference/sensevoice.py`, `tests/ai/test_sensevoice_engine.py` | 2026-10-28 | SenseVoice extracts discrete acoustic emotion tags (`<|NEUTRAL|>`, `<|HAPPY|>`, `<|SAD|>`, `<|ANGRY|>`). Custom emotion model training results **do not exist** (none in repository). |
| **LLM Service** | `real-verified` | `backend/app/services/llm_service.py`, `tests/backend/test_llm_service.py` | 2026-10-28 | Qwen3-1.7B via local `llama-server`. Uncontrolled sampling caused Hindi repetition loops and 500 peg-native parsing crashes in Phase 8h; stabilized in Phase 8i with `repeat_penalty=1.1`, `frequency_penalty=0.2`, `max_tokens=120`, and typed `LLMBadResponse` error mapping. |
| **RAG Gate** | `real-verified` | `rag/intent_router.py`, `docs/deployment/runs/hard_gate_eval_8i.txt` | 2026-10-28 | Overall accuracy: 94.0% (47/50) on hard eval set (25 chat, 25 knowledge). **Caveat**: Evaluation datasets and gate sets were authored by the agent (indicative only, not an independent human benchmark). |
| **RAG Retrieval** | `real-verified` | `data/index/chunks.json`, `docs/deployment/runs/rag_ingestion_8i.txt` | 2026-10-28 | FAISS IndexFlatIP with `multilingual-e5-small`. Ingests 3 documents (5 chunks total: `company_policy.md`, `developer_guide.md`, `warranty_terms.txt`). Knowledge base documents are sample fixtures, not production enterprise data. |
| **TTS (Indic Parler)** | `known issue` | `docs/deployment/tts-benchmark-rtx2050.md`, `docs/deployment/runs/tts_llama_stopped.txt`, `docs/deployment/runs/tts_llama_running.txt` | 2026-10-28 | `TTS_ENABLED=false` by default. Standalone RTF is 2.65–8.3 on GPU (RTX 2050 4GB) and 17–24 on CPU. End-to-end co-residence fails with `OSError: [WinError 1455] The paging file is too small for this operation to complete` due to Windows commit limit exhaustion. |
| **WebSocket** | `real-verified` | `backend/app/websocket/speech_socket.py`, `tests/backend/test_websocket.py`, `docs/deployment/runs/ws_english_speech_8i.txt` | 2026-10-28 | Real-time audio streaming and JSON events (`ready`, `vad`, `speech_result`, `llm_delta`, `llm_done`, `error`). Isolates LLM and TTS errors while keeping connection open. |
| **REST API** | `real-verified` | `backend/app/api/health.py`, `backend/app/api/auth.py` | 2026-10-28 | `/health` monitors subsystem readiness and LLM cool-down state; `/api/auth` issues development mock JWT tokens. |
| **Frontend** | `test-double only` | `frontend/src/App.tsx`, `frontend/src/hooks/useWebSocket.ts` | 2026-10-28 | React + Vite UI with audio capture and state display. UI changes are out of scope for Phase 8 and not evaluated in automated test runs. |
| **Legacy Tree** | `not measured` | `docs/architecture/legacy-src.md`, `src/` | 2026-10-28 | Unmigrated prototype code from early exploration. Not imported or executed by production backend. |

---

## 2. Invariants & Ground Truth Summary

1. **Synthetic vs Authentic Audio**:
   - `tests/samples/english_speech_16k.wav` is a **synthetic** audio clip (generated via TTS, 8.23s). It transcribes to *"Voice sense A provides multilingual and emotion or air voice systems across 23 in languages."*
   - `tests/samples/sample_hindi_speech.wav` is the **only authentic human acoustic Hindi recording** in the repository (5.28s). Spoken prompt confirmed by speaker: *"आज मौसम बहुत अच्छा है।"* (Speaker confirmed they **DID NOT** say *"नमस्ते"*).
2. **Language Gating**:
   - No automatic spoken LID is active.
   - Hindi speech requires explicit client specification: `{"type": "start", "language_hint": "hi"}`.
3. **RAG Gating Invariant**:
   - Conversational utterances make **zero** calls to retrieval or FAISS.
   - Evaluated on agent-authored test sets (50 examples: 25 chat, 25 knowledge).
4. **TTS Memory & Co-Residence Invariant**:
   - RTX 2050 Mobile (4GB VRAM) cannot support concurrent resident GPU execution of Qwen3-1.7B and Indic Parler-TTS without paging/OOM.
   - Windows commit limit (32,176 MB) is exhausted when backend (+ SenseVoice + IndicConformer + RAG = 30,279 MB commit) attempts to spawn a 3.8GB Parler-TTS worker process. `TTS_ENABLED=false` is enforced.
