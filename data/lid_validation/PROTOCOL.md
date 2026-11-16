# LID Validation Recording Protocol — Hindi & English

Status: planning document only. `LID_ENABLED=false`; nothing here changes code, config, routing, thresholds, or models.

Scope is narrowed to **Hindi (`hi`) and English (`en`) only**. No other languages are in scope for this collection round.

---

## 1. Recording guide

### Hardware / format
- Record in **WAV, mono, PCM 16-bit** (44.1 kHz or 48 kHz preferred; 16 kHz minimum acceptable — the detector resamples internally, but higher source quality preserves evidence).
- Quiet room, minimal background noise, ~30 cm mic distance, consistent gain across a session.
- Do **not** apply noise suppression, normalization, or effects — keep originals untouched.
- One speaker per file; name files only by `recording_id` (see §4).

### Speaker targets
- **8–10 clips per language** initially.
- **≥3 independent speakers per language** where feasible.
- English set **must include Indian English accents** (at least 2 speakers); do not ask anyone to exaggerate or imitate an accent.
- Anonymous speaker IDs only: `HI_S01`, `HI_S02`, … / `EN_S01`, `EN_S02`, …
- **Never record real names, phone numbers, or other personal data.**

### Clip rules
- **3–15 seconds** per clip (hard bounds; discard <2 s or >20 s takes).
- Mix of **read speech** (scripted passage) and **spontaneous speech** (unscripted topic monologue, ~15–30 s of talking, then trim/select 1–2 clean 3–15 s segments).
- Natural pace, natural volume. No whispering in the main set (whisper goes to `challenge/`).
- Speakers may code-switch naturally in Hindi set (English loanwords are expected and desired — see §2), but each clip's `language_gt` is the **dominant** language.

### Consent / provenance
- Every recording requires the speaker's explicit consent for research/evaluation use.
- Record `consent_confirmed=yes` and a one-line `provenance` note (e.g. "self-recorded, speaker consented 2026-11-XX") in the manifest.
- Keep originals immutable; any trimming/normalization produces a *derived* file noted in `notes`.

---

## 2. Recording content

Do **not** record Hindi and English from the same translated passage. Use language-specific natural material.

### Hindi (`hi`)

**Read-passage suggestions** (pick 1–2 per speaker, ~30–60 s source material):
- Everyday narrative: a short story about a morning routine, a trip to the market, or planning a family event.
- News-style formal read: a simple Hindi news paragraph (e.g., weather, local event).
- Informal conversational read: dialogue-like sentences ("आज क्या计划 है?" style natural code-mixed phrasing is fine and realistic).
- Must include **common Hindi vocabulary and everyday topics**; include a few sentences with English loanwords (e.g., "मैं आजAppointment लेनी है", "यहSalary बहुत अच्छी है") — do not make clips artificially Sanskrit-heavy.

**Spontaneous topics** (speaker talks freely 30–60 s; select clean segments):
- Describe your last weekend.
- Explain how to make a simple dish or fix something at home.
- Talk about a film/series you watched recently.
- Describe your job or studies in your own words.

### English (`en`)

**Read-passage suggestions** (pick 1–2 per speaker):
- Everyday narrative: a short story about a commute, a recipe, or a childhood memory.
- Formal read: a short newspaper-style paragraph.
- Informal conversational read: casual dialogue sentences.

**Spontaneous topics:**
- Describe your daily routine.
- Talk about a hobby or something you are learning.
- Describe a recent trip or plan for the weekend.
- Explain a simple process (how to use an app, how to cook something).

Indian English speakers should speak **naturally** — Indian accent is expected and desired in at least 2 of ≥3 speakers; no imitation, no exaggeration.

---

## 3. Fixed regression sample

`tests/samples/sample_hindi_speech.wav` (5.28 s, 48 kHz, authentic human Hindi, speaker-confirmed prompt) is a **fixed regression sample**:
- It must remain **byte-identical** — never re-record, trim, normalize, or overwrite.
- It is pre-registered in `manifests/lid_validation_manifest.csv` with `split=fixed_regression`.
- It is evaluated on every run but is **not** counted in dev/held-out splits and **not** used for threshold selection.
- Known 4B result for reference: VoxLingua107 → `sa` @ 0.448 (below 0.6 → default). Any future change in this outcome is a regression signal.

---

## 4. CSV manifest schema

File: `manifests/lid_validation_manifest.csv` (header only + pre-filled regression row).

Columns:
```
recording_id, speaker_id, language_gt, recording_type, duration_seconds, sample_rate, channels, format, environment, consent_confirmed, provenance, split, notes
```

Field rules:
- `recording_id`: `HI_R01`, `EN_R01`, … unique per clip.
- `speaker_id`: `HI_S01` / `EN_S01` anonymous IDs only.
- `language_gt`: `hi` or `en` (dominant language; never inferred from model output).
- `recording_type`: `read` | `spontaneous`.
- `split`: `dev` | `heldout` | `challenge` | `fixed_regression`.
- `consent_confirmed`: `yes`/`no` — only `yes` rows enter evaluation.
- Blank = unknown; do not invent values.

---

## 5. Directory structure

```
data/lid_validation/
├── PROTOCOL.md                      # this document
├── hindi/                           # authentic Hindi clips (HI_R*)
├── english/                         # authentic English clips (EN_R*)
├── challenge/                       # Hinglish, noisy, whisper, <1.5s clips — NEVER in main eval
│   └── (files named CH_R*)
└── manifests/
    └── lid_validation_manifest.csv  # the only manifest
```

Rules:
- `challenge/` is permanently separate from dev/held-out evaluation.
- Originals stay untouched inside these folders; derived/trimmed copies go to a `derived/` subfolder per language with the derivation noted in `notes`.
- No speaker may appear in both `dev` and `heldout` splits wherever speaker count permits; when a language has <2 speakers per split, flag the split as speaker-confounded in `notes`.

---

## 6. Evaluation safeguards

- **Speaker-disjoint splits**: assign whole speakers to dev or heldout; never split one speaker across both.
- **No speaker leakage**: verify `speaker_id` sets are disjoint between splits before any run.
- **Challenge set isolation**: `challenge/` clips are reported separately and never influence threshold or acceptance decisions.
- **Held-out freeze**: held-out data is never used for threshold selection, error analysis-driven tuning, or model/prompt changes. Threshold stays **0.6** unless dev-set evidence forces a documented change *before* held-out evaluation.
- **TTS exclusion**: no TTS/synthetic file may enter the authentic set; existing `en_*`/`hi_*`/`output_*`/`bench_*` files remain TTS-only evidence.
- **Provenance honesty**: `language_gt` comes only from recording instructions/consent records — never from ASR transcripts or LID predictions.
