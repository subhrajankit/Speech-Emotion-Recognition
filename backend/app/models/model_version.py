"""
ModelVersion entity for tracking pinned models, engines, and revisions.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engine_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pinned_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decoder_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "engine_name",
            "model_id",
            "pinned_revision",
            "decoder_type",
            name="uq_engine_model_rev_decoder"
        ),
    )

    # Relationships
    predictions = relationship("Prediction", back_populates="model_version")
