"""
Transcript entity recording recognized text and linguistic context.
Zero raw audio retention invariant: raw audio chunks are NEVER persisted.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    prediction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    script: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mixed_language: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audio_events: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    prediction = relationship("Prediction", back_populates="transcript")
    session = relationship("Session", back_populates="transcripts")
