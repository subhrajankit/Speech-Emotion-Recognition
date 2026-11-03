"""
Message entity representing conversational turns, user inputs, and assistant responses.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    prediction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("predictions.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False
    )

    # Relationships
    session = relationship("Session", back_populates="messages")
    prediction = relationship("Prediction", back_populates="messages")
