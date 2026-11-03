"""
Prediction entity representing an individual speech perception turn.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    model_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("model_versions.id", ondelete="SET NULL"), index=True, nullable=True)
    audio_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False
    )

    # Relationships
    session = relationship("Session", back_populates="predictions")
    model_version = relationship("ModelVersion", back_populates="predictions")
    transcript = relationship("Transcript", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    emotion_result = relationship("EmotionResult", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="prediction")
