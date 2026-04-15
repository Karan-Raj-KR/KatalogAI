import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Index,
    DateTime,
    func,
    String,
    Text,
    Integer,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "input_type IN ('text','image','screenshot','batch')", name="ck_job_input_type"
        ),
        CheckConstraint(
            "status IN ('queued','processing','completed','failed','needs_review')",
            name="ck_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id"),
        index=True,
    )
    input_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
