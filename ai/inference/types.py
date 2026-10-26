"""
Unified speech perception result types.
Model-independent schema for ASR, LID, SER, and AED outputs.
"""

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, field_validator


class SpeechResult(BaseModel):
    """
    Unified, model-independent representation of speech processing results.

    Confidence Policy:
    SenseVoiceSmall rich transcription emits greedy discrete token predictions
    and does not expose calibrated posterior probabilities for emotion or language.
    Therefore, confidence defaults to None unless an explicit logit derivation
    is provided. We never fabricate artificial confidence scores.
    """
    transcript: str = Field(
        ...,
        description="Clean transcribed spoken text stripped of control tags."
    )
    language: str = Field(
        ...,
        description="ISO 639-1 two-letter language code (e.g. 'en', 'zh', 'ja', 'ko') or 'unknown'."
    )
    emotion: Optional[str] = Field(
        default=None,
        description="Normalized primary emotion label (e.g. 'happy', 'sad', 'angry', 'neutral', 'fearful', 'disgusted', 'surprised') or None."
    )

    @field_validator("emotion", mode="before")
    @classmethod
    def normalize_emotion(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = str(v).strip().strip("<|>").lower()
        if v_clean in ("emo_unknown", "unknown", "unk", "none", "null", ""):
            return None
        return v_clean
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Calibrated model confidence score in [0.0, 1.0], or None if uncalibrated/unavailable."
    )
    processing_time_ms: int = Field(
        ...,
        ge=0,
        description="Total wall-clock inference processing time in milliseconds."
    )
    model_version: str = Field(
        ...,
        description="Identifier of the model and checkpoint used for inference."
    )

    # Optional extras
    emotion_scores: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional posterior emotion probabilities or score dictionary."
    )
    audio_events: List[str] = Field(
        default_factory=list,
        description="Detected acoustic sound events (e.g. 'BGM', 'Applause', 'Laughter', 'Cough')."
    )
    segments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional segment-level timestamps and metadata."
    )
    debug: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional diagnostic data (e.g. raw tags, VAD stats)."
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        cleaned = v.strip().lower()
        return cleaned if cleaned else "unknown"

    @field_validator("emotion")
    @classmethod
    def validate_emotion(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        return cleaned if cleaned else None
