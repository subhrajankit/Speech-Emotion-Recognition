"""
History and session schemas for VoiceSense AI.
"""

from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict


class TranscriptSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    language: str
    script: Optional[str] = None
    mixed_language: Optional[bool] = None
    audio_events: Optional[List[str]] = None
    created_at: datetime


class EmotionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    primary_emotion: str
    confidence: Optional[float] = None
    valence: Optional[float] = None
    arousal: Optional[float] = None
    raw_tags: Optional[List[str]] = None
    created_at: datetime


class ModelVersionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    engine_name: str
    model_id: str
    pinned_revision: Optional[str] = None
    decoder_type: Optional[str] = None


class PredictionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    audio_duration_ms: Optional[float] = None
    processing_time_ms: Optional[float] = None
    confidence: Optional[float] = None
    model_version: Optional[ModelVersionSchema] = None
    transcript: Optional[TranscriptSchema] = None
    emotion_result: Optional[EmotionSchema] = None
    created_at: datetime


class MessageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    text: str
    sources: Optional[Any] = None
    prediction_id: Optional[str] = None
    created_at: datetime


class SessionSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    primary_language: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    turn_count: int


class SessionDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    primary_language: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    predictions: List[PredictionSchema] = []
    messages: List[MessageSchema] = []


class DeleteHistoryResponse(BaseModel):
    deleted: bool
    purged_sessions_count: int
    message: str
