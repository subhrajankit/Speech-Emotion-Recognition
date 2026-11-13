# English ASR Evaluation — Recording Protocol & Collection Plan

Status: planning document. `LID_ENABLED=false`; no production code, config, or routing is affected.
Supersedes the Chunk 4.4H slot table (corrected split assignments — see §2).

## 1. Recording requirements (from repo docs)

- **Format**: WAV, mono, PCM 16-bit; 44.1/48 kHz preferred, 16 kHz minimum (`data/lid_validation/PROTOCOL.md:12`).
- **Duration**: 3–15 s per final clip; discard takes <2 s or >20 s (`PROTOCOL.md:25`).
- **Environment**: quiet room, ~30 cm mic distance, consistent gain; no noise suppression/normalization/effects; originals immutable (`PROTOCOL.md:13-14`).
- **Speakers**: 8–10 clips, ≥3 independent speakers, Indian English accents (≥2 speakers), anonymous `EN_S##` IDs, no PII (`PROTOCOL.md:18-22`).
- **Types**: mix of `read` and `spontaneous` (`PROTOCOL.md:26`, `data/english_asr_eval/README.md:5`).
- **Consent**: explicit consent per recording; `consent_confirmed=yes` mandatory for human rows (`PROTOCOL.md:31-32`; evaluator rejects `n/a`/`no`/empty for non-`synthetic_tts`).
- **No TTS**: synthetic audio is excluded (`README.md:7`).

### Consent wording (suggested script)

> "This recording is for evaluating a speech-recognition system. Only an anonymous clip ID will be stored — no name or personal details. Do you consent to this recording being used for evaluation?"

Record the verbal yes in private operator notes (outside the repo); the manifest stores only `consent_confirmed=yes` + date in `accent_notes` provenance text.

### Mild background noise

Main set stays clean. If a robustness check is wanted later, record 1–2 clips with mild domestic background noise (fan, distant traffic) — keep them in a separate `challenge`-style grouping, never mixed into dev/heldout scoring.

## 2. Corrected 10-slot plan (speaker-disjoint)

Correction applied: `EN_R03` and `EN_R04` split changed `dev` → `heldout` (speakers and types unchanged). Fixes the 4.4H violation where EN_S02 appeared in both splits.

| Slot | Speaker | Type | Split |
|---|---|---|---|
| EN_R01 | EN_S01 | read | dev |
| EN_R02 | EN_S01 | spontaneous | dev |
| EN_R03 | EN_S02 | read | **heldout** |
| EN_R04 | EN_S02 | spontaneous | **heldout** |
| EN_R05 | EN_S02 | read | heldout |
| EN_R06 | EN_S03 | spontaneous | heldout |
| EN_R07 | EN_S03 | read | heldout |
| EN_R08 | EN_S03 | spontaneous | heldout |
| EN_R09 | EN_S01 | read | dev |
| EN_R10 | EN_S02 | spontaneous | heldout |

**Counts**: dev = 3 clips (EN_S01: 2 read + 1 spontaneous); heldout = 7 clips (EN_S02: 2 read + 2 spontaneous; EN_S03: 1 read + 2 spontaneous). Total: 5 read / 5 spontaneous.

**Verification**: (a) no speaker appears in both splits — EN_S01→dev only, EN_S02/EN_S03→heldout only ✓; (b) each split contains both recording types — dev has read (R01,R09) + spontaneous (R02); heldout has both ✓. No slot-type switching needed.

**Usage rule**: `dev` is for debugging the evaluator only; `heldout` is run **once** for the reported number and is never used for tuning.
**Limits**: 2 heldout speakers, ~7 clips — results are indicative only, not statistically robust.

## 3. Read-speech prompts (neutral, no personal disclosure)

- R1: "The city bus was late again this morning, so I walked to the office instead."
- R2: "She packed a small bag, locked the door, and walked quickly to the station."
- R3: "Please read the instructions carefully before you start the experiment."
- R4: "The weather forecast says it will rain later in the afternoon."
- R5: "He opened the window to let in some fresh air."

## 4. Spontaneous-speech prompts

- S1: "Describe how you usually start your day, from waking up to leaving home."
- S2: "Explain how to make a simple cup of tea or coffee, step by step."

Record 30–60 s free speech; select clean 3–15 s segments.

## 5. File naming & placement

```
data/english_asr_eval/audio/EN_R01_EN_S01_read_01.wav
data/english_asr_eval/references/EN_R01.txt
```

- `audio/` originals are immutable; `references/` holds one `.txt` per clip.
- **`data/english_asr_eval/audio/` content stays out of Git** (add to `.gitignore` or keep untracked) — audio files are not committed.

## 6. Reference transcripts

- Exact spoken text including disfluencies and contractions; punctuation may be normal (metric normalizes).
- For spontaneous clips, transcribe only the selected segment boundaries.
- **Speaker confirms the transcript** against the audio before manifest entry.

## 7. Manifest entry

Append to `data/english_asr_eval/manifests/english_asr_eval_manifest.csv` per `README.md` field rules; `split` follows §2; `consent_confirmed=yes`; provenance noted in `accent_notes` (no dedicated column exists).

## 8. Pre-evaluation check

```bash
.venv/Scripts/python.exe scripts/eval_english_asr.py \
  --manifest data/english_asr_eval/manifests/english_asr_eval_manifest.csv \
  --dataset-root data/english_asr_eval --modes auto,en --split dev
```

(`PYTHONPATH=.` no longer required — repo root is added inside the script.)
