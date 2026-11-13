# English ASR Evaluation Dataset

Authentic human English speech for evaluating `SenseVoiceSpeechEngine` (`iic/SenseVoiceSmall`).

- **Pilot target**: 8–10 clips, ≥3 speakers, natural Indian English accents, read + spontaneous, ~3–15 s each, verified reference transcripts.
- **Recording rules**: follow `data/lid_validation/PROTOCOL.md` and the collection plan in `docs/dataset/english_asr_eval_protocol.md` (WAV mono PCM, quiet room, originals immutable, anonymous speaker IDs, consent required, corrected speaker-disjoint split).
- **No TTS**: synthetic audio (`tests/samples/en_*`, `output_english_*`, `english_speech_16k.wav`, `scripts/bench_en_*`) is excluded from this set.
- **Splits**: `dev` for iteration/analysis, `heldout` frozen for final scoring — never use heldout for tuning.

## Layout

```
data/english_asr_eval/
├── audio/        # EN_R*.wav originals (immutable)
├── references/   # EN_R*.txt verified transcripts (one per clip)
└── manifests/
    └── english_asr_eval_manifest.csv
```

`audio_path` / `reference_path` in the manifest are relative to `data/english_asr_eval/` unless absolute.

## Running the evaluation

Requires the ML environment (`.venv` with torch/funasr — **not** CI-lite):

```bash
.venv/Scripts/python.exe scripts/eval_english_asr.py \
    --manifest data/english_asr_eval/manifests/english_asr_eval_manifest.csv \
    --dataset-root data/english_asr_eval \
    --modes auto,en
```

The script transcribes each clip twice — `language="auto"` and `language="en"` — and reports per-file and aggregate WER/CER plus the detected language tag (recorded separately from transcription quality). See script docstring for normalization policy.

## Adding a recording

1. Record per `data/lid_validation/PROTOCOL.md` → save original to `audio/EN_R##_speaker_take.wav` (e.g. `EN_R01_EN_S01_read_01.wav`).
2. Write the verified transcript to `references/EN_R01.txt` — plain text, exactly what was spoken (spelling/punctuation may be normal; the metric normalizes).
3. Append one row to `manifests/english_asr_eval_manifest.csv`:

```
EN_R01,EN_S01,audio/EN_R01_EN_S01_read_01.wav,references/EN_R01.txt,read,6.4,16000,1,Indian English (neutral),yes,self-recorded 2026-11-XX,dev,
```

Field rules enforced by `scripts/eval_english_asr.py` before any model loads:
- `recording_id` unique; `speaker_id` must look like `EN_S01` (anonymous only);
- `split` must be `dev` or `heldout`; `consent_confirmed` must be `yes`;
- `audio_path`/`reference_path` must exist relative to `data/english_asr_eval/`;
- reference file must be non-empty. Violations fail fast with per-row errors.

Speaker-disjoint rule: assign each `EN_S##` entirely to `dev` or `heldout` — never both.
