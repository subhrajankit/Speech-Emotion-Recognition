# VoiceSense AI — Deep Forensic Audit

**Run:** `runs/2026-11-13_12-05-57/`
**Audit date:** 2026-11-13
**Repository:** `D:\Capstone Project\NewSenseVoice` (branch `migration/voicesense`)
**Mode:** Read-only forensic audit. No application source was modified.

## Naming note (important)

The audit brief describes "VoiceSense AI — A Full-Stack Real-Time Speech Emotion
Recognition platform using fine-tuned Wav2Vec 2.0". The repository's actual
product is **SenseAI Voice Assistant** (`AGENTS.md`, `brain/03_ARCHITECTURE.md`):
a multilingual voice assistant built on **SenseVoiceSmall + IndicConformer-600m
(ASR) + Qwen3 LLM (llama.cpp) + Indic Parler-TTS**, with emotion taken from
SenseVoice's discrete SER tags — **not** a fine-tuned Wav2Vec 2.0 classifier.

A Wav2Vec2-style emotion pipeline *does* exist in the repo
(`ai/models/emotion/`, `ai/training/`, `ai/inference/emotion.py`) but is
**research code that is not wired into the runtime** — see `06_WAV2VEC2_SER_MODEL_AUDIT.md`.

## Report index

| File | Contents |
|---|---|
| `00_EXECUTIVE_SUMMARY.md` | Condition, top findings, scores |
| `01_COMPLETE_FILE_INVENTORY.md` | Tree + file inventory |
| `02_SYSTEM_ARCHITECTURE_AUDIT.md` | Actual vs intended architecture |
| `03_FRONTEND_AUDIT.md` | React/Vite audit |
| `04_BACKEND_API_AUDIT.md` | Every endpoint traced |
| `05_DATABASE_AUDIT.md` | Schema, ORM, migrations |
| `06_WAV2VEC2_SER_MODEL_AUDIT.md` | ML/emotion pipeline audit |
| `07_AUDIO_REALTIME_STREAMING_AUDIT.md` | Mic → VAD → WS → TTS |
| `08_LLM_INTEGRATION_AUDIT.md` | Qwen3/llama.cpp integration |
| `09_END_TO_END_INTEGRATION_AUDIT.md` | Workflow traces |
| `10_SECURITY_PRIVACY_AUDIT.md` | Security findings |
| `11_TESTING_QA_AUDIT.md` | Test inventory + executed results |
| `12_DEPENDENCIES_DEPLOYMENT_AUDIT.md` | Deps, Docker, CI/CD |
| `13_DEAD_CODE_DUPLICATION_TECHNICAL_DEBT.md` | Dead code & duplicates |
| `14_MASTER_FEATURE_STATUS_MATRIX.md` | Feature status matrix |
| `15_MASTER_FINDINGS_REGISTER.md` | Numbered findings |
| `16_PRIORITIZED_REMEDIATION_ROADMAP.md` | P0–P4 remediation |
| `17_VERIFICATION_EVIDENCE.md` | Commands & outputs |
| `18_AUDIT_LIMITATIONS_AND_UNVERIFIED_ITEMS.md` | What could not be verified |
