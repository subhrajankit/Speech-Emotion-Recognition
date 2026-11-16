# VoiceSense AI — Viva Documentation Package

This folder contains the complete technical documentation for the VoiceSense AI
capstone project, written for a final viva examination. Every statement is based
on the actual source code in this repository — nothing here describes a planned
feature as if it were finished.

## How to use this package

| File | What it covers | When to read it |
|---|---|---|
| `01_OVERVIEW.md` | What the project is, the problem it solves, real vs planned features | First — your 2-minute pitch |
| `02_ARCHITECTURE.md` | Full system architecture, pipeline stages, data flow, module boundaries | When asked "how does it work?" |
| `03_REPOSITORY_GUIDE.md` | Every folder and important file, what it does, who uses it | When asked "explain your codebase" |
| `04_AI_ML.md` | VAD, ASR engines, language routing, RAG, LLM, TTS, SER training pipeline | When asked about the ML side |
| `05_BACKEND_API.md` | REST endpoints, WebSocket protocol v1, services, database schema | When asked about backend/API |
| `06_FRONTEND.md` | React app structure, hooks, state, protocol client, UI components | When asked about frontend |
| `07_SECURITY_TESTING_DEPLOYMENT.md` | Auth, rate limits, privacy, tests, Docker, CI | When asked about quality/security |
| `08_VIVA_QA.md` | Likely viva questions with short model answers, limitations, future work | Last — your rehearsal sheet |

## Ground rules used while writing

- The **canonical, running system** is `backend/app/` + `ai/` + `rag/` + `frontend/`
  (the "target architecture"). `src/backend/` and `src/frontend/` are a quarantined
  legacy prototype — they are NOT imported at runtime.
- The project has two names in the repo history: **SenseAI Voice Assistant**
  (design docs in `brain/`) and **VoiceSense AI** (code, README, this report).
  They are the same project; "VoiceSense AI" is the current product name.
- Where the code honestly reports something as unverified or disabled
  (e.g. TTS, PostgreSQL, full SER training), this documentation says so.
  Examiners reward honesty about limitations far more than overselling.
