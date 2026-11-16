"""
Dedicated Acoustic Speech Emotion Recognition (SER) Engine.
Wraps emotion2vec_plus_base via FunASR for discrete 4-class emotion classification
(angry, happy, neutral, sad) with explicit uncertainty and fallback policies.

Operates purely on acoustic audio waveforms (zero transcript sentiment).
Guarded by threadpool limits and lazy singleton lifecycle.
"""

import os
import time
import logging
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import numpy as np

from ai.inference.emotion import EmotionEngine, EmotionResult
from ai.preprocessing.audio import load_and_preprocess_audio, resample_audio

logger = logging.getLogger(__name__)

# Supported target 4-class domain
SUPPORTED_4CLASS_MAP = {
    "angry": "angry",
    "happy": "happy",
    "neutral": "neutral",
    "sad": "sad",
}

# Unsupported classes mapped to unknown with raw label preserved
UNSUPPORTED_CLASSES = {
    "disgusted",
    "fearful",
    "surprised",
    "other",
    "<unk>",
    "unk",
}


def _normalize_funasr_label(raw_label: str) -> str:
    """Normalizes '生气/angry' -> 'angry'."""
    if "/" in raw_label:
        return raw_label.split("/")[-1].strip().lower()
    return raw_label.strip().lower()


class Emotion2VecSpeechEngine(EmotionEngine):
    """
    Dedicated Speech Emotion Recognition Engine powered by emotion2vec_plus_base.
    Implements EmotionEngine ABC.
    """

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        device: str = "cpu",
        threads: int = 2,
        confidence_threshold: float = 0.60,
        auto_load: bool = False,
    ):
        self.model_dir = Path(
            model_dir or os.getenv("EMOTION2VEC_MODEL_DIR", "models/emotion/emotion2vec-plus-base")
        )
        self.device = device or os.getenv("EMOTION2VEC_DEVICE", "cpu")
        self.threads = int(threads or os.getenv("EMOTION2VEC_THREADS", "2"))
        self.confidence_threshold = float(
            confidence_threshold
            if confidence_threshold is not None
            else os.getenv("EMOTION2VEC_CONFIDENCE_THRESHOLD", "0.60")
        )
        self.model_version = "emotion2vec_plus_base"

        self.model = None
        self.is_loaded = False
        self._lock = threading.Lock()

        if auto_load:
            self._load_model()

    def load(self) -> None:
        """Idempotently loads the emotion2vec model into memory."""
        if not self.is_loaded or self.model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Loads model weights under thread lock."""
        with self._lock:
            if self.is_loaded and self.model is not None:
                return

            if not self.model_dir.exists():
                raise RuntimeError(
                    f"emotion2vec model directory does not exist at '{self.model_dir}'. "
                    f"Please verify weights are placed at that path or configure EMOTION2VEC_MODEL_DIR."
                )

            try:
                import torch
                # Clamp CPU thread allocation to prevent threadpool starvation
                torch.set_num_threads(self.threads)
            except ImportError as e:
                raise RuntimeError(f"PyTorch is required for emotion2vec inference: {e}") from e

            try:
                from funasr import AutoModel
            except ImportError as e:
                raise RuntimeError(f"FunASR is required for emotion2vec inference: {e}") from e

            logger.info(
                f"Loading emotion2vec_plus_base from '{self.model_dir}' on device={self.device} "
                f"(threads={self.threads})..."
            )
            t0 = time.time()
            try:
                self.model = AutoModel(
                    model=str(self.model_dir),
                    device=self.device,
                    disable_update=True,
                    log_level="ERROR",
                )
                self.is_loaded = True
                load_time = round(time.time() - t0, 2)
                logger.info(f"emotion2vec_plus_base loaded successfully in {load_time}s.")
            except Exception as e:
                self.is_loaded = False
                self.model = None
                raise RuntimeError(
                    f"Failed to load emotion2vec model from '{self.model_dir}': {e}"
                ) from e

    def classify(
        self,
        audio: Union[np.ndarray, bytes, str, Path],
        sample_rate: int = 16000,
    ) -> EmotionResult:
        """
        Classifies speech emotion directly from raw acoustic waveform.

        Args:
            audio: 16 kHz float32 NumPy array, bytes, or file path.
            sample_rate: Input sampling rate (must be 16000 for emotion2vec).

        Returns:
            EmotionResult with primary emotion, calibrated confidence, scores dict,
            and processing latency.
        """
        self.load()

        # Preprocess input into 16 kHz mono float32 NumPy array
        if isinstance(audio, (str, Path)):
            audio_array = load_and_preprocess_audio(str(audio), target_sr=16000)
        elif isinstance(audio, bytes):
            audio_array = load_and_preprocess_audio(audio, target_sr=16000)
        elif isinstance(audio, np.ndarray):
            audio_array = audio
            # Stereo to mono
            if audio_array.ndim == 2:
                audio_array = audio_array.mean(axis=1 if audio_array.shape[1] < audio_array.shape[0] else 0)
            # Int16 to float32
            if audio_array.dtype in (np.int16, np.int32):
                audio_array = audio_array.astype(np.float32) / 32768.0
            elif audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)
            # Resample if needed
            if sample_rate != 16000:
                audio_array = resample_audio(audio_array, orig_sr=sample_rate, target_sr=16000)
        else:
            raise ValueError(f"Unsupported audio type for emotion2vec: {type(audio)}")

        # Guard against empty audio or digital silence
        if audio_array is None or len(audio_array) == 0:
            return EmotionResult(
                primary="unknown",
                confidence=0.0,
                scores={},
                processing_time_ms=0.0,
                model_version=self.model_version,
            )

        max_amp = float(np.max(np.abs(audio_array)))
        if max_amp < 1e-4:
            # Ambient silence
            return EmotionResult(
                primary="unknown",
                confidence=0.0,
                scores={"neutral": 1.0},
                processing_time_ms=0.0,
                model_version=self.model_version,
            )

        # Execute model forward pass
        t0 = time.time()
        try:
            res = self.model.generate(
                input=audio_array,
                granularity="utterance",
                extract_embedding=False,
            )
        except Exception as e:
            logger.error(f"emotion2vec forward inference failed: {e}")
            raise RuntimeError(f"emotion2vec inference error: {e}") from e

        processing_time_ms = round((time.time() - t0) * 1000.0, 1)

        if not res or not isinstance(res, list) or len(res) == 0:
            return EmotionResult(
                primary="unknown",
                confidence=0.0,
                scores={},
                processing_time_ms=processing_time_ms,
                model_version=self.model_version,
            )

        result_dict = res[0]
        raw_labels = result_dict.get("labels", [])
        scores = result_dict.get("scores", [])

        if not raw_labels or not scores:
            return EmotionResult(
                primary="unknown",
                confidence=0.0,
                scores={},
                processing_time_ms=processing_time_ms,
                model_version=self.model_version,
            )

        # Normalize label strings
        norm_labels = [_normalize_funasr_label(l) for l in raw_labels]
        scores_float = [float(s) for s in scores]

        # Build scores dictionary
        scores_dict = {label: round(score, 4) for label, score in zip(norm_labels, scores_float)}

        # Find top predicted class
        top_idx = int(np.argmax(scores_float))
        raw_top_label = norm_labels[top_idx]
        top_score = scores_float[top_idx]

        # Uncertainty and mapping policy
        # 1. Is the top class a supported primary class (angry, happy, neutral, sad)?
        # 2. Does its confidence cross the confidence threshold?
        if raw_top_label in SUPPORTED_4CLASS_MAP:
            if top_score >= self.confidence_threshold:
                final_emotion = SUPPORTED_4CLASS_MAP[raw_top_label]
            else:
                final_emotion = "unknown"
        else:
            # Unsupported class (disgusted, fearful, surprised, other, unk)
            final_emotion = "unknown"

        return EmotionResult(
            primary=final_emotion,
            confidence=round(top_score, 4),
            scores=scores_dict,
            processing_time_ms=processing_time_ms,
            model_version=self.model_version,
            raw_label=raw_top_label,
        )

    def check_health(self) -> Dict[str, Any]:
        """Returns health telemetry."""
        return {
            "status": "ok" if self.is_loaded else "ready",
            "model_version": self.model_version,
            "model_dir": str(self.model_dir),
            "device": self.device,
            "threads": self.threads,
            "confidence_threshold": self.confidence_threshold,
            "is_loaded": self.is_loaded,
        }
