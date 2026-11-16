# 08 — Viva Q&A Prep, Limitations & Future Work

Model answers are short and speakable. Numbers come from the repo's own
verification ledger — reuse them confidently.

## 1. The 60-second pitch

> "VoiceSense AI is a fully local, real-time voice assistant. Speech is captured
> in the browser, streamed as PCM16 over WebSocket, segmented by Silero VAD,
> transcribed by SenseVoiceSmall — which also emits emotion and audio-event
> tags in one pass — with IndicConformer-600m available for Hindi in
> multilingual mode. A hard intent gate decides whether the turn is chat,
> document Q&A via RAG, or a command; chat is the default and never touches the
> vector index. Answers stream from a local Qwen3-1.7B on llama.cpp, conditioned
> on detected emotion, and optionally spoken by Indic Parler-TTS. Auth,
> history, rate limits, and delete-my-data are built in. Everything runs on
> 127.0.0.1 — no audio or transcript ever leaves the machine."

## 2. Likely questions & answers

**Q: Walk me through what happens when I speak.**
A: Mic → AudioWorklet downsamples to 16 kHz PCM16 → binary WebSocket frames →
server `VADSpeechSegmenter` detects speech start, collects frames until 700 ms
of silence → complete utterance goes to `speech_service` → language routing →
SenseVoiceSmall (or IndicConformer for Hindi) returns a `SpeechResult` with
transcript + emotion + events → `speech_result` frame is sent to the client
**before** anything else → intent router classifies the transcript → chat goes
straight to Qwen3, knowledge queries retrieve top-3 FAISS chunks → LLM streams
`llm_delta` → `llm_done` → optional TTS → turn persisted to SQLite in the
background.

**Q: Why WebSocket and not REST for voice?**
A: Low-latency bidirectional streaming. Audio is a continuous binary stream
and the response is a token stream — REST request/response can't express
either. REST is still used for health, auth, file upload, and history.

**Q: Why is the transcript sent before the LLM answer?**
A: Perception-first isolation. If the LLM server is down, RAG index missing, or
TTS fails, the user still gets their transcript and emotion instantly. It's an
explicit reliability invariant, covered by fault-isolation tests.

**Q: How does emotion recognition work?**
A: Two layers exist. **Live**: SenseVoiceSmall emits discrete emotion tags
(`<|HAPPY|>` etc.) alongside text in a single pass; tags are normalized into
`SpeechResult.emotion` and used to condition the LLM system prompt. **Planned**:
a dedicated wav2vec2-base + MLP SER model trained on CREMA-D — the training
pipeline, speaker-independent splits, and eval harness are built, but the
checkpoint is currently untrained scaffold (honest status: `NOT YET MEASURED`).
Hindi audio reports `emotion=null` because IndicConformer has no emotion head.

**Q: Why two ASR models?**
A: SenseVoiceSmall covers en/zh/yue/ja/ko with emotion+events but not Hindi.
IndicConformer-600m covers Hindi + 21 Indic languages but no emotion. A
`SpeechEngine` interface + `LanguageRouter` (hint → LID → default) picks the
right one per utterance. In the default English-only MVP everything routes to
SenseVoice.

**Q: Why not fine-tune one model for everything?**
A: Cost and risk. Two specialized pretrained models beat training one
multilingual emotion ASR from scratch on a capstone budget; the router keeps
the seam clean and either engine can be swapped.

**Q: How does RAG work and why the "hard gate"?**
A: Documents are chunked (500 chars/100 overlap), embedded with
multilingual-e5-small ("passage:" prefix), stored in FAISS IndexFlatIP. At
query time a two-tier intent router first checks ~20 regex rules, then cosine
similarity against knowledge vs chat exemplars — below threshold or ambiguous
→ **chat**, and FAISS is never queried (test-verified: zero retrieval calls on
chat). This prevents RAG latency and hallucinated citations on normal
conversation. Result: 47/50 (94%) on our 50-example gate eval.

**Q: Why FAISS?**
A: CPU-fast approximate/exact search, tiny footprint at this scale, pure
local. We keep a `NumpyVectorIndex` fallback because Windows Smart App Control
blocks the native faiss binary on the dev machine — mathematically identical
(inner product on L2-normalized vectors = cosine).

**Q: Why Qwen3-1.7B and llama.cpp?**
A: Fits in ~1.5 GB VRAM on a laptop GPU, OpenAI-compatible HTTP API = simple
httpx integration, no Python ML deps in the backend venv, fully local. The
service adds an SSE streaming parser, `<think>` tag stripping, repetition
penalties, and a 3-failure/15 s circuit breaker.

**Q: How is the LLM kept from rambling or leaking reasoning?**
A: System prompt demands 1–2 spoken sentences, no chain-of-thought;
`enable_thinking=false` in chat template kwargs; `ThinkingFilter` strips
`<think>` blocks even when split across stream chunks; `max_tokens=120` +
repeat/frequency penalties.

**Q: How does auth work?**
A: `hashlib.scrypt` password hashing (stdlib, memory-hard) + hand-rolled HS256
JWT — no PyJWT dependency, alg pinned to HS256, exp/nbf checks. Tokens travel
inside the WebSocket `start` frame, not the URL. `AUTH_REQUIRED` can be
enforced; production mode refuses to boot without it and a strong secret.

**Q: How is user data protected?**
A: Raw audio never touches disk — decoded in RAM only. Transcripts persist only
for authenticated users, can be redacted via `STORE_TRANSCRIPTS=false`, and
`DELETE /api/history` purges everything (delete-my-data). Sessions are
user-isolated at the query level; anonymous users persist nothing.

**Q: How do you handle rate limiting/abuse?**
A: Sliding 60-second window of utterances per session (20/min), 30 s max
utterance duration, 5 MB WS buffer cap, 10 MB upload cap, per-IP auth limits.
Confirmed silence refunds the utterance slot so it doesn't burn quota.

**Q: What happens if a model or service fails?**
A: Everything degrades gracefully: missing LLM → transcript still delivered +
`llm_unavailable` error frame; missing RAG index → `rag_fallback` status +
plain chat; TTS failure → text-only; DB failure → logged and swallowed; ASR
engine failure → fallback to SenseVoice; IndicConformer absent → English-only
mode unaffected. `/api/health` reports per-component status.

**Q: Why is TTS disabled?**
A: It's fully implemented but `TTS_ENABLED=false` because real benchmarks on
our RTX 2050/16 GB dev machine showed RTF 2.65–24.46 — slower than real time —
plus Windows commit-charge exhaustion when co-resident with ASR+RAG. The code
supports in-process or isolated `.venv-tts` worker, CUDA→CPU fallback, and
cooldown breakers so enabling it is a config flip on adequate hardware.

**Q: Why English-only by default?**
A: The multilingual path is built and tested, but automatic spoken-LID
candidates misclassified real Hindi audio and cost ~400 MB RAM — so we ship
English-only MVP and kept explicit `language_hint="hi"` routing behind
`ASR_ENGLISH_ONLY=false`. Honest limitation, documented in README §16.

**Q: What is `src/` then?**
A: The original Phase 1–3 monolith (`/ws/voice`), kept for history but
quarantined — nothing imports it, its tests are excluded, and it's slated for
removal. The live system is `backend/app/` + `ai/` + `rag/` + `frontend/`.

**Q: How is the project tested?**
A: ~150+ pytest tests across `tests/ai|backend|rag|eval` (CI-lite runs without
ML weights), 24 Vitest files for frontend, import-isolation CI check, real-
model benchmark scripts (`e2e_real.py`, `evaluate_hard_gate.py`), saved run
evidence under `docs/deployment/runs/` and `docs/training/runs/`.

**Q: What are the limitations?** (see §3)

**Q: Future work?** (see §4)

## 3. Limitations (say these unprompted — they make you credible)

1. English-only ASR by default; Hindi needs a config flag.
2. No Hindi emotion recognition (`emotion=null` on Indic path).
3. Code-mixed/Hinglish speech untested.
4. Wav2Vec2 SER model is scaffold-only — real CREMA-D training not yet run.
5. TTS implemented but disabled (RTF > 1 on dev hardware).
6. PostgreSQL and Docker runtime paths unverified (SQLite dev works).
7. No standardized WER/CER benchmark; ASR evidence is narrow (1 Hindi clip,
   1 synthetic English clip).
8. RAG eval set is agent-authored (94% on our own 50 examples, not a blind
   external benchmark).
9. Qwen3-1.7B is compact — not SOTA reasoning; `max_tokens=120` suits voice.
10. Windows Smart App Control blocked native faiss/CUDA-ONNX on the dev
    machine → CPU inference + numpy fallback locally.

## 4. Future work (prioritized, matches repo roadmap)

1. Run real CREMA-D training → evaluate wav2vec2 SER vs SenseVoice zero-shot
   baseline (harness already exists in `ai/training/evaluate.py`).
2. Enable multilingual mode by default once a better LID is chosen or
   fine-tuned; re-run Hinglish/code-mixed eval.
3. TTS on adequate GPU (or distilled TTS) → enable `TTS_ENABLED` with emotion
   styling.
4. PostgreSQL migration verification + Docker runtime bring-up.
5. Standardized ASR benchmark (WER on a fixed eval set) + blind external RAG
   eval.
6. Command branch completion (calculator/timer/reminders are reserved in the
   intent taxonomy).
7. WebTransport upgrade (Phase 9+ roadmap) for lower-latency transport.
8. Speaker verification / voice enrollment for stronger session identity.

## 5. Numbers to memorize

- VAD frame: 512 samples = 32 ms @ 16 kHz; silence split 700 ms; pre-pad 250 ms
- ASR: SenseVoiceSmall (zh/yue/en/ja/ko + emotion + 9 event types);
  IndicConformer-600m, CTC median ~1.2 s on 5.28 s Hindi (RTF 0.23), RNNT ~2.76 s
- RAG: e5-small 384-dim, top-3, threshold 0.70 retrieval / 0.80 intent gate;
  47/50 = 94% gate accuracy, ~119 ms mean
- LLM: Qwen3-1.7B Q4_K_M, ~1.5 GB VRAM, TTFT ~0.8 s, 20–61 tok/s (dev GPU),
  max_tokens 120, breaker 3 fails/15 s
- TTS: RTF 2.65–24.46 measured → disabled; 23 languages, 69 speakers, 44.1 kHz
- Limits: 20 utt/min, 30 s/utterance, 10 MB upload, 5 MB WS buffer, 60 min JWT
- Tests: backend+ai+rag pytest suites green on CI-lite; 24 frontend Vitest files

## 6. If you forget everything else

1. It's **local-first** — privacy is the point.
2. Pipeline order: **VAD → route → perceive → emit result → gate → reason →
   stream → persist**.
3. **Perception is isolated** — transcript/emotion arrive before LLM/RAG/TTS.
4. **Intent gate is hard** — chat never touches FAISS.
5. **Honesty is a feature** — the repo labels what's verified vs scaffold;
   mirror that in your answers.
