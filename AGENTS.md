# SenseAI Voice Assistant — Agent Rules

## What this project is
Multilingual, emotion-aware, fully local voice assistant. See `brain/03_ARCHITECTURE.md` for
the full pipeline — do not re-derive it from memory, read that file.

## Tech stack
Frontend: React + TypeScript + Vite. Backend: Python + FastAPI. Models: Silero VAD,
SenseVoiceSmall, IndicConformer-600m, Qwen3-4B via llama.cpp, multilingual-e5-small + FAISS,
Indic Parler-TTS. DB: SQLite (dev) → PostgreSQL (prod). MVP transport: WebSocket
(WebTransport is a later upgrade — do not build it before Phase 9, see roadmap).

## Before doing anything
Read, in order: `brain/03_ARCHITECTURE.md`, `brain/16_CHANGELOG.md`,
`brain/17_DECISIONS.md`, and this file's current phase section. Never start coding a phase
you haven't read the prompt for.

## Hard rules
- Build one phase at a time, in order. Do not implement later-phase features early
  (no WebTransport before Phase 9, no RAG-by-default, no emotion styling before Phase 5).
- Load every model once at startup. Never load per-request.
- The intent router (Phase 4+) is a hard gate: RAG and command handling are explicit
  branches, never a silent default — default is plain chat.
- Never persist raw audio beyond the request lifecycle. Transcripts, emotion_history, and
  uploaded RAG documents ARE persisted — see `brain/10_SECURITY.md`.
- Local model-serving ports bind to 127.0.0.1 only.
- No Kubernetes, Kafka, Redis cluster, or multiple LLMs/vector DBs. Keep it simple.

## Definition of done, every phase
Tests pass. `brain/16_CHANGELOG.md` and `brain/17_DECISIONS.md` updated (decisions only if
a judgment call was made). Manual smoke test confirmed by the human before moving to the
next phase.

## Skills available in this project
- `ui-ux-pro-max` — activates automatically for frontend/UI work (Phase 1 mic UI,
  Phase 10 dashboard). Do not invoke for backend-only phases.
- ECC harness rules — plan → test → implement → review → verify → remember loop applies
  to every phase's task, not just the ones you're told to test.

## MCP servers connected
`github` (PRs, CI, issues), `sqlite` (read-only, dev DB), `postgres` (prod DB, once Phase 12
exists). Use them to verify your own work — e.g. query the DB directly after a migration
instead of assuming it applied correctly.

## Don't
- Don't ask the human to re-explain the architecture — it's in `brain/`.
- Don't mark a phase done without the human's manual smoke test, even if all automated
  tests pass.
- Don't touch the browser tool outside `localhost` / configured doc sources.
