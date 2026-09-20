"""
Language Router for VoiceSense AI.
Standardizes ASR engine selection between SenseVoiceSmall (global languages)
and IndicConformer-600m (Hindi and 21 Indic languages).

Decision Policy:
1. Explicit client `language_hint` (Highest Precedence):
   - Client specifies target language directly.
   - If hint maps to an Indic language (e.g. 'hi', 'mr', 'ta'), routes to IndicConformer.
   - If hint maps to SenseVoice supported languages ('en', 'zh', 'yue', 'ja', 'ko'), routes to SenseVoice.
   - Unrecognized hint falls back to default engine (SenseVoice).
   - source = "hint"

2. Spoken Language Identification (LID) (Medium Precedence):
   - Invoked when language_hint is absent and a pluggable LID detector is available.
   - If detected language has confidence >= configurable threshold (default: 0.6), routes accordingly.
   - source = "detected"

3. Default Engine Fallback (Lowest Precedence):
   - If LID confidence is below threshold or LID is unconfigured.
   - Routes to SenseVoiceSmall default engine (English).
   - source = "default"
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, Literal, Set
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Languages natively supported by SenseVoiceSmall rich transcription
# Citation: FunASR / Alibaba DAMO Academy SenseVoiceSmall model card (2024)
SENSEVOICE_LANGUAGES: Set[str] = {
    "en",   # English
    "zh",   # Chinese (Mandarin)
    "yue",  # Cantonese
    "ja",   # Japanese
    "ko",   # Korean
}

# 22 Scheduled Indian Languages supported by AI4Bharat IndicConformer-600m
# Citation: AI4Bharat IndicSuperb / IndicConformer, Kumar et al. (2022/2023)
INDIC_LANGUAGES: Set[str] = {
    "hi",   # Hindi
    "bn",   # Bengali
    "mr",   # Marathi
    "te",   # Telugu
    "ta",   # Tamil
    "gu",   # Gujarati
    "kn",   # Kannada
    "ml",   # Malayalam
    "pa",   # Punjabi
    "or",   # Odia
    "as",   # Assamese
    "ur",   # Urdu
    "sa",   # Sanskrit
    "mai",  # Maithili
    "bho",  # Bhojpuri
    "ne",   # Nepali
    "sd",   # Sindhi
    "ks",   # Kashmiri
    "kok",  # Konkani
    "mni",  # Manipuri
    "sat",  # Santali
    "brx",  # Bodo
    "doi",  # Dogri
}


class RoutingDecision(BaseModel):
    """
    Standardized routing decision returned by LanguageRouter.
    """
    language: str = Field(
        ...,
        description="Resolved language code (ISO 639-1 / 639-2) or 'unknown'."
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score in [0.0, 1.0] if derived from calibrated LID, else None."
    )
    engine: str = Field(
        ...,
        description="Target ASR engine identifier ('sensevoice' or 'indicconformer')."
    )
    source: Literal["hint", "detected", "default"] = Field(
        ...,
        description="Origin of the routing decision: 'hint' (explicit), 'detected' (LID), or 'default'."
    )
    debug: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details for telemetry and debugging."
    )


class LanguageIdentifier(ABC):
    """
    Abstract interface for pluggable spoken language identification (LID) models.
    Can be implemented by SpeechBrain VoxLingua107, Meta MMS-LID, or Whisper.
    """

    @abstractmethod
    def identify(self, audio: np.ndarray, sample_rate: int = 16000) -> Tuple[str, float]:
        """
        Predicts language code and confidence from audio array.

        Args:
            audio: 1D float32 audio samples normalized in [-1.0, 1.0].
            sample_rate: Sampling frequency in Hz.

        Returns:
            Tuple of (predicted_language_code, confidence_score in [0.0, 1.0]).
        """
        pass


class LanguageRouter:
    """
    Deterministic language router enforcing the 3-tier routing policy:
    1. Client language_hint wins
    2. Spoken LID with confidence >= threshold
    3. Default engine (SenseVoiceSmall)
    """

    def __init__(
        self,
        default_engine: str = "sensevoice",
        default_language: str = "en",
        lid_confidence_threshold: float = 0.6,
        lid_detector: Optional[LanguageIdentifier] = None,
    ):
        self.default_engine = default_engine
        self.default_language = default_language
        self.lid_confidence_threshold = lid_confidence_threshold
        self.lid_detector = lid_detector

    def route(
        self,
        audio: Optional[np.ndarray] = None,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> RoutingDecision:
        """
        Evaluates input parameters and audio to decide the target ASR engine.

        Args:
            audio: Optional audio waveform for LID detection.
            sample_rate: Sampling rate of audio.
            language_hint: Explicit ISO language code passed by client.

        Returns:
            Standardized RoutingDecision.
        """
        # Tier 1: Explicit client language_hint wins
        if language_hint:
            cleaned_hint = language_hint.strip().lower()
            if cleaned_hint:
                if cleaned_hint in INDIC_LANGUAGES:
                    return RoutingDecision(
                        language=cleaned_hint,
                        confidence=1.0,
                        engine="indicconformer",
                        source="hint",
                        debug={"policy": "explicit_hint_indic", "raw_hint": language_hint}
                    )
                elif cleaned_hint in SENSEVOICE_LANGUAGES:
                    return RoutingDecision(
                        language=cleaned_hint,
                        confidence=1.0,
                        engine="sensevoice",
                        source="hint",
                        debug={"policy": "explicit_hint_sensevoice", "raw_hint": language_hint}
                    )
                else:
                    # Unrecognized hint: fallback to default engine
                    logger.warning(
                        f"Unrecognized language hint '{language_hint}'. "
                        f"Falling back to default engine '{self.default_engine}'."
                    )
                    return RoutingDecision(
                        language=cleaned_hint,
                        confidence=None,
                        engine=self.default_engine,
                        source="hint",
                        debug={
                            "policy": "unrecognized_hint_fallback",
                            "raw_hint": language_hint,
                            "fallback_engine": self.default_engine
                        }
                    )

        # Tier 2: Spoken Language Identification (LID)
        if self.lid_detector is not None and audio is not None and len(audio) > 0:
            try:
                detected_lang, confidence = self.lid_detector.identify(audio, sample_rate=sample_rate)
                detected_lang = detected_lang.strip().lower()

                if confidence >= self.lid_confidence_threshold:
                    if detected_lang in INDIC_LANGUAGES:
                        return RoutingDecision(
                            language=detected_lang,
                            confidence=confidence,
                            engine="indicconformer",
                            source="detected",
                            debug={
                                "policy": "lid_detected_indic",
                                "threshold": self.lid_confidence_threshold
                            }
                        )
                    elif detected_lang in SENSEVOICE_LANGUAGES:
                        return RoutingDecision(
                            language=detected_lang,
                            confidence=confidence,
                            engine="sensevoice",
                            source="detected",
                            debug={
                                "policy": "lid_detected_sensevoice",
                                "threshold": self.lid_confidence_threshold
                            }
                        )
                    else:
                        # LID detected a language outside Indic and SenseVoice scopes
                        return RoutingDecision(
                            language=detected_lang,
                            confidence=confidence,
                            engine=self.default_engine,
                            source="detected",
                            debug={
                                "policy": "lid_detected_other",
                                "fallback_engine": self.default_engine
                            }
                        )
                else:
                    logger.debug(
                        f"LID confidence {confidence:.2f} for '{detected_lang}' "
                        f"below threshold {self.lid_confidence_threshold:.2f}."
                    )
            except Exception as e:
                logger.error(f"Error executing LID detector: {e}")

        # Tier 3: Default engine fallback
        return RoutingDecision(
            language=self.default_language,
            confidence=None,
            engine=self.default_engine,
            source="default",
            debug={
                "policy": "default_fallback",
                "default_engine": self.default_engine,
                "default_language": self.default_language
            }
        )
