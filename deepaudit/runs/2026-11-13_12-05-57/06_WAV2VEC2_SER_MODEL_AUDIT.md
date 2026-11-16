# 06 — Wav2Vec2 / SER Model Audit

## Reality check vs. brief

The project title claims "fine-tuned Wav2Vec 2.0". Actual runtime SER = **SenseVoiceSmall's built-in discrete emotion tags** (`<|HAPPY|>`…`<|SURPRISED|>`, `<|EMO_UNKNOWN|>`), parsed in `ai/inference/sensevoice.py:35-101`. There is **no Wav2Vec2 model in the serving path**.

## What exists

| Component | File | Status |
|---|---|---|
| `EmotionModelConfig` | `ai/models/emotion/config.py` | backbone="facebook/wav2vec2-base", emb 768, 4 classes default [neutral,happy,sad,angry] — config only; **no Wav2Vec2 weights are ever loaded** |
| `EmotionClassifier` (PyTorch head) + `NumPyEmotionClassifier` | `ai/models/emotion/model.py` | implemented; NumPy variant = LayerNorm+MLP with deterministic RNG init |
| `Wav2Vec2EmotionEngine` | `ai/inference/emotion.py` | EmotionEngine ABC impl; checkpoint .npz/.pt loading; **`extract_features()` (lines 123-140) is a pseudo-feature generator** — deterministic RNG vector seeded by audio checksum + energy/zcr, NOT SSL embeddings |
| Training pipeline | `ai/training/{dataset,train,evaluate,metrics}.py`, `config/{default,crema_d_smoke}.yaml` | CREMA-D manifest CSVs in `data/metadata/`; speaker-independent split logic in dataset.py |
| Trained artifact | `docs/training/runs/run_20261025_193120/checkpoints/best_model.npz` + metrics.json | **smoke run: 5 samples, accuracy 0.40, UAR 0.167, macro-F1 0.20** — not a usable model |
| Tests | `tests/ai/test_emotion_{inference,metrics,split}.py` | pass (mock mode) |

## Wiring status

`ai/inference/emotion.py` is imported **only** by its own tests. `speech_service.py`, `speech_socket.py`, `health.py` never reference it. The IndicConformer engine has an `emotion_hook` parameter (`indicconformer.py:58,267-277`) explicitly reserved "for Phase 5" — never supplied. **VERDICT: IMPLEMENTED BUT NOT WIRED — production emotion is SenseVoice tags only.**

## SER quality assessment (SenseVoice path)

- Emotion = single greedy tag per utterance; `confidence=None` always (`types.py:14-19` documents this honestly — no fabricated scores).
- `history_service` then **fabricates** confidence/valence/arousal for DB storage (see report 05).
- No per-frame/continuous emotion, no smoothing, no calibration, no evaluation of the SER head on a benchmark.

## Training pipeline audit (research code)

- Dataset: CREMA-D only (smoke manifests: `data/metadata/crema_d_smoke_{train,val}.csv`). Speaker-independent split implemented in `dataset.py` (verified by `test_emotion_split.py`).
- Features: the "Wav2Vec2" backbone is **not actually used for feature extraction** — `extract_features` is a hash-seeded random projection. Even a "trained" checkpoint would classify synthetic features, not audio embeddings. This is the single biggest research-validity gap.
- Metrics (`metrics.py`): accuracy, UAR, macro/weighted F1, per-class P/R/F1, confusion matrix — genuinely computed; saved under `docs/training/runs/`.
- Reproducibility: seed in config; checkpoint `best_model.npz` + `model_config.json` + `run_metadata.json` saved. But only a 5-sample smoke run exists.
- No RAVDESS/TESS/SAVEE/IEMOCAP/MELD usage anywhere (grep-confirmed names absent except docs).

## Recommendations (for report 16)

Either (a) wire `Wav2Vec2EmotionEngine` behind `SpeechService` with real HF `Wav2Vec2Model` feature extraction and a properly trained checkpoint, or (b) formally descope the Wav2Vec2 claim and document SenseVoice-tag SER as the production path. Fix `extract_features` before any real training — current features are non-informative.
