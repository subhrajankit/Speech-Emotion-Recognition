"""
Speech Engine Interface.
Abstract base protocol implemented by ASR / Speech perception engines.
"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np

from ai.inference.types import SpeechResult


class SpeechEngine(ABC):
    """
    Abstract interface for speech processing engines.
    Implemented by SenseVoiceSmall (Phase 1) and IndicConformer-600m (Phase 4).
    """

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Returns model identifier / version string."""
        pass

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Transcribes audio array into a unified SpeechResult.

        Args:
            audio: 1D float32 audio samples normalized in [-1.0, 1.0].
            sample_rate: Sampling frequency in Hz (typically 16000).
            language_hint: Optional ISO 639-1 language code hint.

        Returns:
            SpeechResult conforming to the unified schema.
        """
        pass
