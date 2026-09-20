---
trigger: always_on
---

# VoiceSense AI — Always-On Rules

## Working style
- Audit first. Read before you change. Never rewrite or delete working code just to match a target structure.
- One phase at a time. Never start a phase I haven't approved. At the end of every phase, report and STOP.
- Smallest reasonable change. Use `git mv` for moves and update all imports/references in the same change.
- Work on branch `migration/voicesense`. One commit per phase.
- Before any change, state: what you'll change, what you'll preserve, which tests you'll run.

## Truthfulness
- Never write "works", "implemented", or "passing" unless you ran it in this session. Paste the command and the real (trimmed) output.
- Label every finding: VERIFIED (I ran it), READ (from code only), or UNKNOWN.
- If something fails, show the actual error. No mocks, stubs, fake outputs, or hard-coded results unless I explicitly ask for mock mode.
- Never fabricate metrics. Only measured results go into docs.

## Architecture invariants
- ASR and emotion recognition must NOT import or depend on Qwen3, RAG, or TTS. If any of those fail, transcript + emotion must still work.
- RAG runs only when the intent router flags a knowledge query, never on every utterance.
- Local-first. Cloud Gemini is optional and off by default.
- One implementation per service. Models must be swappable through config.
- Do not replace SenseVoiceSmall without a written technical reason.
- Do not claim SenseVoiceSmall supports Hindi unless the model card/README confirms it (cite the source).
- Hindi ASR and Hindi emotion recognition are separate problems.

## Safety
- Never commit model weights, datasets, `.env`, or secrets.
- Do not download large models automatically; ask first.
- Do not run destructive commands (rm -rf, git reset --hard, force push, docker system prune, DB drops) without asking.