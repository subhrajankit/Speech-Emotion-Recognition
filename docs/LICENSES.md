# Third-Party Model & Dataset Licenses

VoiceSense AI orchestrates local open-weight models and references public research datasets. Review upstream license terms, commercial restrictions, and Hugging Face gating rules before redistributing weights or deploying externally.

---

## 1. Project Source License

The repository [`LICENSE`](../LICENSE) file currently states the **MIT License** (`Copyright (c) 2026 SenseAI Contributors`). That file was **not** modified during Phase 12 documentation updates pending confirmation from the project owner.

---

## 2. Upstream Models & Dataset Matrix

| Component | Upstream Identifier | License | Gated Download? | Commercial Notes | Upstream URLs Checked |
|---|---|---|---|---|---|
| **SenseVoiceSmall** (ASR + Emotion + AED) | `iic/SenseVoiceSmall` / `FunAudioLLM/SenseVoice` | Code: `MIT License`<br/>Weights: `FunASR Model Open Source License Agreement` | No | Commercial use permitted under FunASR agreement with attribution / license notice preservation | [`FunAudioLLM/SenseVoice`](https://github.com/FunAudioLLM/SenseVoice)<br/>[`FunASR MODEL_LICENSE`](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE)<br/>[`HuggingFace SenseVoiceSmall`](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)<br/>[`ModelScope SenseVoiceSmall`](https://modelscope.cn/models/iic/SenseVoiceSmall) |
| **IndicConformer-600m** (Hindi ASR) | `ai4bharat/indic-conformer-600m-multilingual` (pinned rev `2a77d305038dfc502fd9464e7d028b90381976cb`) | `MIT License` | **Yes (Hugging Face gated repo)** | Permissive MIT terms; requires accepting upstream HF repo terms and authenticating via `HF_TOKEN` | [`ai4bharat/indic-conformer-600m-multilingual`](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) |
| **Qwen3-1.7B GGUF** (Local LLM) | `Qwen/Qwen3-1.7B` (`unsloth/Qwen3-1.7B-GGUF`) | `Apache License 2.0` | No | Permissive Apache 2.0 terms | [`Qwen/Qwen3-1.7B`](https://huggingface.co/Qwen/Qwen3-1.7B)<br/>[`unsloth/Qwen3-1.7B-GGUF`](https://huggingface.co/unsloth/Qwen3-1.7B-GGUF) |
| **Indic Parler-TTS** (Optional/Disabled TTS) | `ai4bharat/indic-parler-tts` | `Apache License 2.0` | Requires HF access / marked gated in `tts_service.py` notes | Permissive Apache 2.0 terms (`TTS_ENABLED=false` by default) | [`ai4bharat/indic-parler-tts`](https://huggingface.co/ai4bharat/indic-parler-tts) |
| **Multilingual E5 Small** (RAG Embeddings & Router) | `intfloat/multilingual-e5-small` | `MIT License` | No | Permissive MIT terms | [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) |
| **Silero VAD** (Speech Segmentation) | `snakers4/silero-vad` | `MIT License` | No | Permissive MIT terms | [`snakers4/silero-vad`](https://github.com/snakers4/silero-vad) |
| **Wav2Vec2-Base** (Emotion Training Backbone) | `facebook/wav2vec2-base` | `Apache License 2.0` | No | Configured in `ai/training/config/default.yaml` for offline training research | [`facebook/wav2vec2-base`](https://huggingface.co/facebook/wav2vec2-base) |
| **CREMA-D** (Emotion Research Corpus) | `CheyneyComputerScience/CREMA-D` | `Open Data Commons Open Database License (ODbL) v1.0` | External manual download | Share-alike & attribution obligations under ODbL v1.0 for derived databases; weights/data not redistributed in repo | [`CREMA-D GitHub`](https://github.com/CheyneyComputerScience/CREMA-D) |

*Upstream license metadata verified against public repository pages on 2026-11-11.*
