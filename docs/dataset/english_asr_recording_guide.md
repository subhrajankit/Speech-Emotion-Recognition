# English ASR Recording Session Guide — EN_R01 to EN_R03 (dev split)

Purpose: collect the first three **authentic human** English recordings for the
SenseVoiceSmall evaluation set. Speaker: **EN_S01** (anonymous ID only — no name
or personal details anywhere in the repo).

Authoritative rules: `docs/dataset/english_asr_eval_protocol.md` and
`data/english_asr_eval/README.md`. This guide is a checklist, not a substitute.

---

## 1. Setup

- **Room**: quiet room, no music/TV/fan directly under the mic. Soft furnishings
  help; a closet or bedroom works.
- **Mic**: any headset, laptop, or phone mic is fine. Hold ~30 cm from your mouth,
  speak at a normal conversational level. Do **not** enable noise suppression,
  AGC, normalization, or any "enhancement" in the recording app.
- **Consistency**: use the same mic, room, and distance for all three clips.

## 2. Format requirements

- **Container/codec**: WAV, uncompressed.
- **Sample format**: PCM 16-bit.
- **Channels**: mono.
- **Sample rate**: 44.1 kHz or 48 kHz preferred; 16 kHz minimum.
- Do **not** convert, trim, normalize, or edit the files after recording.
  Originals are immutable.

## 3. What to record

Record each prompt **once or twice**; keep the cleanest complete take.

| Slot | Type | Prompt |
|---|---|---|
| EN_R01 | read | "The city bus was late again this morning, so I walked to the office instead." |
| EN_R02 | spontaneous | "Describe how you usually start your day, from waking up to leaving home." (30–60 s free speech, then we select a clean 3–15 s segment) |
| EN_R03 | read | "Please read the instructions carefully before you start the experiment." |

- **Read clips**: speak clearly at a natural pace, one take, no restarting
  mid-sentence. Target 3–15 s.
- **Spontaneous clip**: talk naturally for 30–60 s; afterwards pick one clean
  3–15 s segment with no long pauses or false starts. Note the segment
  boundaries — the transcript must cover **only** that segment.

## 4. Consent (required before anything is stored)

Ask the speaker (yourself, for self-recordings) and record a verbal "yes" to:

> "This recording is for evaluating a speech-recognition system. Only an
> anonymous clip ID will be stored — no name or personal details. Do you
> consent to this recording being used for evaluation?"

Keep the verbal confirmation in private operator notes **outside the repo**.
The manifest will store only `consent_confirmed=yes` plus a date in
`accent_notes`.

## 5. File naming & placement

Save originals with these exact names, then copy them into the dataset folder:

```
data/english_asr_eval/audio/EN_R01_EN_S01_read_01.wav
data/english_asr_eval/audio/EN_R02_EN_S01_spontaneous_01.wav
data/english_asr_eval/audio/EN_R03_EN_S01_read_01.wav
```

Write one transcript file per clip:

```
data/english_asr_eval/references/EN_R01.txt
data/english_asr_eval/references/EN_R02.txt
data/english_asr_eval/references/EN_R03.txt
```

- Transcript = **exactly what was spoken**, including disfluencies
  ("um", "uh") and contractions ("don't"). Normal punctuation is fine — the
  metric normalizes it.
- For EN_R02, transcribe only the selected segment.

## 6. Transcript confirmation

Before handoff, **listen to each clip and verify the transcript matches the
audio word-for-word**. Fix any mismatch — the transcript is the ground truth
for WER/CER. Do not guess or paraphrase.

## 7. Handoff checklist

For each of EN_R01, EN_R02, EN_R03 confirm:

- [ ] WAV, mono, PCM 16-bit, ≥16 kHz (prefer 44.1/48 kHz)
- [ ] Duration 3–15 s (EN_R02: selected segment only)
- [ ] File named `EN_R0X_EN_S01_<read|spontaneous>_01.wav` in `audio/`
- [ ] `references/EN_R0X.txt` written and speaker-verified against audio
- [ ] Consent confirmed verbally and noted privately (outside repo)
- [ ] No personal info (name, location, etc.) in filenames or transcripts
- [ ] Originals untouched — no edits, normalization, or trimming

## 8. Common mistakes to avoid

- Recording in a noisy room or with a fan/AC in frame.
- Using compressed formats (MP3, M4A, OGG) — must be WAV PCM.
- "Cleaning up" audio with noise suppression or loudness normalization.
- Transcribing what you *intended* to say instead of what was actually said.
- Including your name or any PII in file names, transcripts, or notes in the repo.
- Mixing speakers — all three clips must be EN_S01.
- Using TTS or any synthetic voice — excluded by protocol.

## 9. After handoff

Once all three pairs are in place and confirmed, the manifest rows are added
(`split=dev`, `consent_confirmed=yes`) and a dev-only smoke evaluation runs.
Held-out recordings (EN_S02, EN_S03) are collected separately and are never
used for tuning.
