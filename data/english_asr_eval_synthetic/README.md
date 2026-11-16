# Synthetic English ASR Smoke-Test Dataset

Isolated smoke-test set for `scripts/eval_english_asr.py` — **synthetic TTS audio only**, separate from the authentic dataset `data/english_asr_eval/`.

## Contents

| recording_id | audio (referenced in place) | reference | source text |
|---|---|---|---|
| `EN_SYN_001` | `tests/samples/en_5_words_gpu_fp16.wav` | `references/EN_SYN_001.txt` | `Hello! How are you doing?` |
| `EN_SYN_002` | `tests/samples/en_14_words_gpu_fp16.wav` | `references/EN_SYN_002.txt` | `VoiceSense AI provides multilingual and emotion aware voice assistance across twenty three Indian languages.` |

- Both entries are **synthetic TTS outputs** (Indic Parler-TTS, fp16 GPU). `speaker_id=EN_S99` is a placeholder — these are **not** two independent human speakers and must never be reported as authentic-speech evidence.
- `consent_confirmed=n/a`: human consent is **not applicable** to generated TTS audio. The evaluator (`load_manifest`) accepts `n/a`/`yes` for `recording_type=synthetic_tts` and still requires `yes` for human recordings.
- `audio/` is intentionally empty: originals are referenced via `../../tests/samples/` relative paths, unmodified and unduplicated.
- Excluded by design: `english_speech_16k.wav` (unverified source text), `reversed_hybrid_en_5_gpu_fp16.wav` (degraded), `output_*` variants (duplicates), all Hindi/Chinese audio.

## Run

```bash
.venv/Scripts/python.exe scripts/eval_english_asr.py \
    --manifest data/english_asr_eval_synthetic/manifests/english_asr_synthetic_manifest.csv \
    --dataset-root data/english_asr_eval_synthetic \
    --modes auto,en --split dev
```

Preflight verified: `load_manifest` returns both rows; `validate_rows` reports no errors; external relative audio paths resolve correctly.
