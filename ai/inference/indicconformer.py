"""
IndicConformer-600m speech processing engine implementation.
Provides ASR for Hindi and 21 scheduled Indian languages.

Model Specifications & Citations:
- Model Architecture: AI4Bharat IndicConformer (~600M parameters, Conformer-Large encoder).
- Primary Paper / Citation:
    AI4Bharat IndicSUPERB / IndicConformer: Kumar et al. (2022/2023)
    "Towards Building Open-Domain Speech Systems for 22 Indian Languages", Interspeech 2022.
- Hugging Face Checkpoints:
    ai4bharat/indicconformer_stt_indic_hybrid_ctc_large
    ai4bharat/indicconformer_stt_hi_hybrid_ctc_large
- Framework: NVIDIA NeMo (nemo_asr.models.EncDecCTCModelBPE / EncDecHybridRNNTCTCBPEModel)
- Real Loading Method:
    nemo_asr.models.EncDecCTCModelBPE.from_pretrained("ai4bharat/indicconformer_stt_indic_hybrid_ctc_large")
    or EncDecCTCModelBPE.restore_from(nemo_model_path)
- Decoding Modes:
    1. CTC (Connectionist Temporal Classification): decoder_type="ctc". Non-autoregressive, fast streaming,
       lower latency on CPU.
    2. RNNT (Recurrent Neural Network Transducer): decoder_type="rnnt". Joint prediction + transcription
       network. Lower WER on conversational Indic speech, higher compute overhead.
- Language Code Argument: Target language code passed as language_id (e.g. language_id="hi" or target_lang="hi").

Emotion Invariant:
IndicConformer does NOT predict emotion. Per VoiceSense architecture rules,
it emits emotion = None (null). SenseVoice emotion tags are NEVER run on Hindi audio.
A clean hook `apply_emotion_hook` is provided for Phase 5 emotion integration.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import numpy as np

from ai.inference.types import SpeechResult
from ai.inference.engine import SpeechEngine
from ai.preprocessing.vad import SileroVAD, VADResult

logger = logging.getLogger(__name__)


class IndicConformerSpeechEngine(SpeechEngine):
    """
    IndicConformer-600m speech perception engine.
    Implements the SpeechEngine interface for Indic ASR.
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        device: Optional[str] = None,
        decoder_type: str = "rnnt",
        vad_model_path: Optional[str] = None,
        vad_threshold: Optional[float] = None,
        auto_load: bool = True,
        emotion_hook: Optional[Callable[[np.ndarray, SpeechResult], SpeechResult]] = None,
        model_revision: Optional[str] = None,
    ):
        """
        Initializes IndicConformer engine.

        Args:
            model_dir: Checkpoint path or HuggingFace ID.
            device: Compute device ('cpu' or 'cuda').
            decoder_type: Decoding mode ('ctc' or 'rnnt'). Default is 'rnnt' for low CPU latency.
            vad_model_path: Optional path to Silero VAD ONNX model.
            vad_threshold: Speech detection probability threshold.
            auto_load: If True, loads model immediately.
            emotion_hook: Optional hook for Phase 5 SER to attach emotion to result.
            model_revision: Pinned git commit hash revision on Hugging Face hub.
        """
        self.model_dir = model_dir or os.getenv(
            "INDICCONFORMER_MODEL_DIR",
            "ai4bharat/indic-conformer-600m-multilingual"
        )
        self.model_revision = model_revision or os.getenv(
            "INDICCONFORMER_REVISION",
            "2a77d305038dfc502fd9464e7d028b90381976cb"
        )
        self.device = device or os.getenv("INDICCONFORMER_DEVICE", "cpu")
        self.decoder_type = decoder_type or os.getenv("INDICCONFORMER_DECODER_TYPE", "rnnt")
        self._model_version = f"IndicConformer-600m ({Path(self.model_dir).name})"

        self.vad = SileroVAD(
            model_path=vad_model_path,
            threshold=vad_threshold,
        )
        self.model = None
        self.is_loaded = False
        self.emotion_hook = emotion_hook

        if auto_load:
            self._load_model()

    @property
    def model_version(self) -> str:
        return self._model_version

    def _load_model(self):
        """
        Loads the IndicConformer-600m model using transformers AutoModel per official model card:
        AutoModel.from_pretrained("ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True)
        Raises clear, actionable RuntimeError if dependencies or weights are absent.
        """
        try:
            import torch
        except ImportError:
            raise RuntimeError(
                "PyTorch is not installed in the current Python environment. "
                "Please install torch>=2.2.0 to run IndicConformer-600m inference."
            )

        try:
            from transformers import AutoModel
        except ImportError:
            raise RuntimeError(
                "Transformers is not installed in the current Python environment. "
                "Please install transformers to run IndicConformer-600m inference."
            )

        logger.info(f"Loading IndicConformer-600m from '{self.model_dir}' on {self.device} (mode={self.decoder_type})...")
        try:
            # Official model card loading convention with pinned revision
            self.model = AutoModel.from_pretrained(
                self.model_dir,
                revision=self.model_revision,
                trust_remote_code=True
            )
            if hasattr(self.model, "to"):
                try:
                    self.model.to(self.device)
                except Exception as e:
                    logger.warning(f"Could not move model to {self.device} ({e}), running on default device.")

            if hasattr(self.model, "eval"):
                self.model.eval()

            self.is_loaded = True
            logger.info("IndicConformer-600m model loaded successfully.")
        except Exception as e:
            raise RuntimeError(
                f"Failed to load IndicConformer model from '{self.model_dir}' ({e}). "
                f"Ensure internet connectivity or approved access token, or set INDICCONFORMER_MODEL_DIR correctly."
            ) from e

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Processes audio array through VAD and IndicConformer.
        Returns a schema-compliant SpeechResult with emotion = None.

        Args:
            audio: 1D float32 audio samples normalized in [-1.0, 1.0].
            sample_rate: Audio sampling frequency (expects 16000).
            language_hint: ISO 639-1 Indic language code (e.g. 'hi', 'mr', 'ta').

        Returns:
            SpeechResult adhering to the unified schema with emotion = None.
        """
        start_time = time.perf_counter()
        target_lang = (language_hint or "hi").strip().lower()

        # 1. Guard against empty or invalid input
        if audio is None or len(audio) == 0:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return SpeechResult(
                transcript="",
                language=target_lang,
                emotion=None,
                confidence=None,
                processing_time_ms=elapsed_ms,
                model_version=self.model_version,
                debug={"status": "empty_audio", "vad_has_speech": False}
            )

        # 2. Silero VAD gate
        vad_res: VADResult = self.vad.analyze(audio, sample_rate=sample_rate)
        if not vad_res.has_speech:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return SpeechResult(
                transcript="",
                language=target_lang,
                emotion=None,
                confidence=None,
                processing_time_ms=elapsed_ms,
                model_version=self.model_version,
                debug={
                    "status": "no_speech_detected",
                    "vad_has_speech": False,
                    "speech_duration_ms": vad_res.speech_duration_ms,
                    "speech_prob": vad_res.speech_probability,
                }
            )

        # 3. Model inference
        if not self.is_loaded or self.model is None:
            self._load_model()

        try:
            import torch

            # Ensure 1D float32
            audio_input = audio.astype(np.float32)
            if audio_input.ndim > 1:
                audio_input = np.mean(audio_input, axis=-1)

            audio_tensor = torch.from_numpy(audio_input).unsqueeze(0).to(self.device)
            audio_len = torch.tensor([len(audio_input)], device=self.device)

            # Model inference: call model per official model card API: model(wav, target_lang, decoder_type)
            with torch.no_grad():
                if callable(self.model):
                    try:
                        out = self.model(audio_tensor, target_lang, self.decoder_type)
                    except TypeError:
                        # Fallback if model expects different args or transcribe method
                        if hasattr(self.model, "transcribe"):
                            out = self.model.transcribe(audio=audio_tensor, length=audio_len, language_id=target_lang)
                        else:
                            out = self.model(audio_tensor)
                elif hasattr(self.model, "transcribe"):
                    out = self.model.transcribe(audio=audio_tensor, length=audio_len, language_id=target_lang)
                else:
                    raise RuntimeError("Loaded IndicConformer model is not callable and has no transcribe method.")

            transcript = ""
            if isinstance(out, str):
                transcript = out
            elif isinstance(out, (list, tuple)) and len(out) > 0:
                transcript = out[0] if isinstance(out[0], str) else getattr(out[0], "text", str(out[0]))
            elif out is not None:
                transcript = getattr(out, "text", str(out))

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            result = SpeechResult(
                transcript=transcript.strip(),
                language=target_lang,
                emotion=None,  # Pure ASR: emotion is always None
                confidence=None,
                processing_time_ms=elapsed_ms,
                model_version=self.model_version,
                debug={
                    "status": "success",
                    "vad_has_speech": True,
                    "decoder_type": self.decoder_type,
                    "language_id": target_lang
                }
            )
            return self._apply_emotion_hook(audio, result)

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(f"IndicConformer transcription failed: {e}")
            raise RuntimeError(f"IndicConformer inference failed: {e}") from e

    def _apply_emotion_hook(self, audio: np.ndarray, result: SpeechResult) -> SpeechResult:
        """
        Clean decoupling hook for Phase 5 emotion engine.
        Does not run by default in Phase 4.
        """
        if self.emotion_hook is not None:
            try:
                return self.emotion_hook(audio, result)
            except Exception as e:
                logger.warning(f"Phase 5 emotion hook failed ({e}). Returning pure ASR result.")
        return result
