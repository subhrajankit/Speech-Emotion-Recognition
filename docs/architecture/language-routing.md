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

### A. SenseVoiceSmall Language Limitations
- **Citation**: Alibaba FunASR / DAMO Academy, *"SenseVoice: An End-to-End Speech Recognition Model for Rich Transcription"*, 2024. Hugging Face: `FunAudioLLM/SenseVoiceSmall`, ModelScope: `iic/SenseVoiceSmall`.
- **Supported Languages**: Chinese (`zh`), Cantonese (`yue`), English (`en`), Japanese (`ja`), Korean (`ko`).
- **Hindi Support**: **NONE**. The vocabulary and model weights do not include Hindi or Devanagari script. Any claim that SenseVoiceSmall natively supports Hindi is technically invalid.

### B. AI4Bharat IndicConformer-600m
- **Citation**: AI4Bharat IndicSUPERB / IndicConformer: Kumar et al. (2022/2023); *"Towards Building Open-Domain Speech Systems for 22 Indian Languages"*, Interspeech 2022.
- **Hugging Face Model**: `ai4bharat/indicconformer_stt_hi_hybrid_ctc_rnnt_large` / `ai4bharat/indicconformer_stt_indic_hybrid_ctc_large`.
- **Phase 8b Invalidation & Gated Status [VERIFIED]**: The Hugging Face checkpoint `ai4bharat/indicconformer_stt_hi_hybrid_ctc_rnnt_large` is a gated repository. Live access without approved organization permissions returns HTTP `403 Forbidden`. Any Phase 4 benchmark figures alleging live execution without authenticated credentials were mock-derived and are INVALID. When weights are gated or unavailable, the language router gracefully falls back to SenseVoice without crashing.
- **Loading Mechanism**: Built using NVIDIA NeMo toolkit (`nemo.collections.asr.models.EncDecCTCModelBPE`). Restored via `EncDecCTCModelBPE.from_pretrained(...)` or `.restore_from(...)`.
- **Decoding Modes**:
  - `ctc` (Connectionist Temporal Classification): Non-autoregressive, fast streaming, lower CPU latency.
  - `rnnt` (Recurrent Neural Network Transducer): Autoregressive joint network, lower conversational WER, higher compute overhead.
- **Language Code Argument**: Specified in transcription requests via `language_id` (e.g. `language_id="hi"`).

---

## 4. Spoken Language Identification (LID) Candidate Evaluation

| Candidate | License | Model Size | CPU Latency (Est.) | Language Coverage | Recommendation & Notes |
|---|---|---|---|---|---|
| **SpeechBrain VoxLingua107** (`speechbrain/lang-id-voxlingua107-ecapa`) | **Apache 2.0** | ~85 MB (21.4M params) | ~30ms – 70ms | 107 languages (includes `hi`, `en`) | **Recommended for PyTorch**. Lightweight ECAPA-TDNN architecture with fast CPU inference. |
| **Meta MMS-LID** (`facebook/mms-lid-126`) | **CC-BY-NC 4.0** *(Non-Commercial)* | ~1.2 GB (300M params) | ~200ms – 400ms | 126 / 256 languages | Heavy footprint, slower CPU forward pass, and restrictive non-commercial license. |
| **OpenAI Whisper Head** (`openai/whisper-tiny`) | **Apache 2.0** | ~151 MB (39M params) | ~80ms – 160ms | 99 languages (includes `hi`, `en`) | **Recommended for ONNX / C++ runtimes**. Permissive license, exportable to ONNX. |

*Note: Per VoiceSense safety rules, model weights are not downloaded automatically. Injected hand-written LID outputs are used for automated unit testing until a labelled dataset is provided by the user.*

---

## 5. Known Limitations: Code-Mixed Speech (Hinglish)

Spoken Hindi mixed with English vocabulary (code-switching or conversational Hinglish) is an open research problem:
- Pure English models miss phonetic and semantic Hindi tokens.
- Pure Devanagari models frequently hallucinate or produce erratic phonetic transcriptions when English nouns/verbs are embedded.
- **Status**: Code-mixed speech is formally documented as an **unmeasured known limitation** in Phase 4. Empirical evaluation on code-mixed corpora (such as LinCE or DISCO) is deferred until dedicated code-switching benchmarks are conducted.
