# VoiceSense AI — Language Routing Architecture

This document specifies the language routing architecture, Spoken Language Identification (LID) candidate evaluation, ASR engine integration, and technical invariants implemented in Phase 4.

---

## 1. High-Level Architecture & Pipeline Invariant

```text
               Audio Input (PCM16 / Container) + optional [language_hint]
                                     │
                                     ▼
                     Silero VAD (Speech Boundary Gate)
                                     │
                                     ▼
                            Language Router
               (3-Tier Precedence Policy: Hint > LID > Default)
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
             [ "sensevoice" ]                [ "indicconformer" ]
           SenseVoiceSmall ASR               IndicConformer-600m
           (Global: EN, ZH, JA,              (Indic: Hindi + 21
            KO, YUE + SER + AED)              Scheduled Languages)
                    │                                 │
                    │ (text, lang, emo)               │ (text, lang, emo=None)
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                      Unified SpeechResult Schema
                        {transcript, language,
                         emotion, processing_time_ms,
                         model_version, debug}
                                     │
                                     ▼
                         [Phase 5 SER Hook]
                       (Independent Emotion)
```

### Invariants
1. **Single Unified Pipeline**: Audio routing and engine dispatch are handled strictly within `SpeechService`. No secondary or duplicated speech pipeline exists.
2. **Standardized Schema**: Both engines return the identical `SpeechResult` schema.
3. **Decoupled Emotion (SER)**: IndicConformer is an ASR model only and outputs `emotion = None`. SenseVoice's emotion head is **never** run on Hindi audio. A clean hook is reserved for the Phase 5 emotion engine.
4. **Engine Fallback & Lazy Loading**: Both engines support lazy / on-demand loading (`LAZY_LOAD_MODELS=true`), ensuring deployments that only need one engine do not pay the memory cost of the other. If routing or IndicConformer execution fails, the pipeline automatically falls back to the default engine (`sensevoice`) and documents the fallback in `result.debug["fallback"]`.

---

## 2. Language Routing Policy

The decision logic in `ai/routing/language_router.py` enforces a deterministic 3-tier precedence policy:

1. **Explicit Client `language_hint` (Highest Precedence)**:
   - When the client specifies a language code (e.g. `hi`, `mr`, `en`, `zh`), this hint is prioritized.
   - If the code belongs to the 22 scheduled Indian languages, routes to `indicconformer`.
   - If the code belongs to SenseVoice supported languages (`en`, `zh`, `yue`, `ja`, `ko`), routes to `sensevoice`.
   - If unrecognized, safely falls back to the default engine (`sensevoice`).
   - Decision origin: `source = "hint"`.

2. **Spoken Language Identification (LID) (Medium Precedence)**:
   - Evaluated when `language_hint` is omitted and a pluggable LID detector is configured.
   - If the predicted language has confidence $\ge$ `LID_CONFIDENCE_THRESHOLD` (default: `0.60`), routes to the corresponding engine.
   - Decision origin: `source = "detected"`.

3. **Default Engine Fallback (Lowest Precedence)**:
   - When no hint is provided and LID confidence is below threshold (or unconfigured), falls back to SenseVoiceSmall default (`en`).
   - Decision origin: `source = "default"`.

---

## 3. Model Card Citations & Scope

### A. SenseVoiceSmall Language Scope
- **Citations**:
  - ModelScope: `https://modelscope.cn/models/iic/SenseVoiceSmall`
  - GitHub: `https://github.com/FunAudioLLM/SenseVoice`
  - Local Snapshot: `C:\Users\subhr\.cache\modelscope\models\iic--SenseVoiceSmall\snapshots\master\README.md`
- **Official Model Card Language Statement** (README line 68):
  > "模型可以被应用于中文、粤语、英语、日语、韩语音频识别，并输出带有情感和事件的富文本转写结果。"
  *(Translation: "The model can be applied to speech recognition in Chinese, Cantonese, English, Japanese, and Korean, and outputs rich text transcription results with emotion and events.")*
- **Tokenizer Artifact**: `chn_jpn_yue_eng_ko_spectok.bpe.model` (strictly covering `chn` [Chinese], `yue` [Cantonese], `eng` [English], `jpn` [Japanese], `ko` [Korean]).
- **Supported Languages**: Chinese (`zh`), Cantonese (`yue`), English (`en`), Japanese (`ja`), Korean (`ko`). Indic languages are outside its model card design scope.

### B. AI4Bharat IndicConformer-600m Multilingual
- **Citation**: AI4Bharat IndicSUPERB / IndicConformer: Kumar et al. (2022/2023); *"Towards Building Open-Domain Speech Systems for 22 Indian Languages"*, Interspeech 2022.
- **Hugging Face Model**: `ai4bharat/indic-conformer-600m-multilingual` (License: MIT).
- **Pinned Revision**: `2a77d305038dfc502fd9464e7d028b90381976cb` (enforced via `INDICCONFORMER_REVISION` in `config.py` and `AutoModel.from_pretrained(..., revision=...)`).
- **Supported Languages**: IN-22 (22 officially recognized Indian languages: `as`, `bn`, `brx`, `doi`, `gu`, `hi`, `kn`, `kok`, `ks`, `mai`, `ml`, `mni`, `mr`, `ne`, `or`, `pa`, `sa`, `sat`, `sd`, `ta`, `te`, `ur`).
- **Loading Mechanism**: Loaded directly via Hugging Face Transformers per official model card:
  ```python
  from transformers import AutoModel
  model = AutoModel.from_pretrained(
      "ai4bharat/indic-conformer-600m-multilingual",
      revision="2a77d305038dfc502fd9464e7d028b90381976cb",
      trust_remote_code=True
  )
  ```
- **Empirical Decoding Speed & Mode Selection (Controlled Fair Benchmark — Single Process, 1 Warm-up + 5 Timed Runs, CPU Execution)**:
  - Evaluation Clip: `tests/samples/sample_hindi_speech.wav` (5.28s authentic human acoustic speech resampled to 16kHz; prompt spoken confirmed by speaker: "आज मौसम बहुत अच्छा है।", speaker confirmed they DID NOT say "नमस्ते" at the start).
  - `ctc` (Connectionist Temporal Classification):
    - Warm-up: 1,987.4 ms
    - 5 Timed Runs: min = **966.4 ms**, median = **1,198.1 ms** (RTF 0.23), max = **1,321.9 ms**
    - Transcript across all runs: `"आज मौसम बहुत अच्छा है"`
    - Working Set RAM: 3,749 MB – 3,750 MB
  - `rnnt` (Recurrent Neural Network Transducer):
    - Warm-up: 11,762.4 ms
    - 5 Timed Runs: min = **2,395.9 ms**, median = **2,757.5 ms** (RTF 0.52), max = **6,144.9 ms**
    - Transcript across all runs: `"आज मौसम बहुत अच्छा है"`
    - Working Set RAM: 3,738 MB – 3,740 MB
  - **Findings & Theoretical Alignment**:
    - CTC is ~2.3x faster than RNNT (median 1.20s vs 2.76s) because CTC performs a non-autoregressive parallel forward pass over acoustic frames, whereas RNNT evaluates its prediction and joint network sequentially in an autoregressive transducer loop.
    - Earlier reports suggesting CTC was 4x slower were confounded by cold model weight loading and thread-throttling in un-warmed benchmark scripts.
    - **Decision**: `ctc` is configured as the default `INDICCONFORMER_DECODER_TYPE="ctc"` because it provides lowest CPU latency while producing the exact same transcript.
  - **Speech Onset & Greeting Verification Facts**:
    - The speaker confirmed they **DID NOT** say "नमस्ते" at the start of `tests/samples/sample_hindi_speech.wav`.
    - The VAD segmenter did not cut speech (speech onset ~1.18 s, segment starts ~0.96 s).
    - Bypassing the engine's internal VAD did not recover it.
    - Prepending 300ms digital silence resulted in: `rnnt`: `"आज मौसम बहुत अच्छा है"` ('नमस्ते' recovered: False), `ctc`: `"आज मौसम बहुत अच्छा है"` ('नमस्ते' recovered: False).
    - Cause of any earlier discrepancy assumption: UNKNOWN. Single-clip observation, not an accuracy claim.

---

## 4. Automatic Language Identification Status & LID Candidates

> [!IMPORTANT]
> **Plain Statement**: Automatic Hindi detection is **NOT** currently implemented. No spoken language identification (LID) model is wired into the runtime pipeline.
> Hindi transcription currently **strictly requires** an explicit client hint: `language_hint="hi"`.
> If `language_hint` is omitted, the router defaults to SenseVoice per policy.

The Phase 4 evaluation evaluated the following LID candidate models, but none will be wired into production without user approval:

| Candidate | License | Model Size | CPU Latency (Est.) | Language Coverage | Recommendation & Notes |
|---|---|---|---|---|---|
| **SpeechBrain VoxLingua107** (`speechbrain/lang-id-voxlingua107-ecapa`) | **Apache 2.0** | ~85 MB (21.4M params) | ~30ms – 70ms | 107 languages (includes `hi`, `en`) | **Recommended for PyTorch**. Lightweight ECAPA-TDNN architecture. |
| **Meta MMS-LID** (`facebook/mms-lid-126`) | **CC-BY-NC 4.0** *(Non-Commercial)* | ~1.2 GB (300M params) | ~200ms – 400ms | 126 / 256 languages | Heavy footprint, slower CPU forward pass, restrictive license. |
| **OpenAI Whisper Head** (`openai/whisper-tiny`) | **Apache 2.0** | ~151 MB (39M params) | ~80ms – 160ms | 99 languages (includes `hi`, `en`) | **Recommended for ONNX / C++ runtimes**. Permissive license. |

---

## 5. Audio Sample Disclosures & Invariants

> [!WARNING]
> **Synthetic Audio Disclosure**: The test audio `tests/samples/english_speech_16k.wav` is **synthetic audio** (generated via TTS synthesis), not natural human speech.
> **Invariant**: Synthetic TTS audio must **never** be cited or used as evidence of human ASR accuracy. Human ASR evidence must come strictly from authentic acoustic recordings (e.g. `tests/samples/sample_hindi_speech.wav`).

---

## 6. Known Limitations: Code-Mixed Speech (Hinglish)

Spoken Hindi mixed with English vocabulary (code-switching or conversational Hinglish) is an open research problem:
- Pure English models miss phonetic and semantic Hindi tokens.
- Pure Devanagari models frequently hallucinate or produce erratic phonetic transcriptions when English nouns/verbs are embedded.
- **Status**: Code-mixed speech is formally documented as an **unmeasured known limitation**. Empirical evaluation on code-mixed corpora (such as LinCE or DISCO) is deferred until dedicated code-switching benchmarks are conducted.
