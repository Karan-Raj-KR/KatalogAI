import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReviewItem(Base):
    """
    A field that requires human review before the product record is finalised.

    Created when confidence for a field falls below the project threshold, or
    when the extractor is uncertain between multiple candidate values.
    """

    __tablename__ = "review_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','rejected')",
            name="ck_review_status",
        ),
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_review_confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id"),
        nullable=False,
        index=True,
    )
    # nullable: the product row may not exist yet when review is triggered
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    extracted_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="pending", index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    product: Mapped["Product | None"] = relationship("Product", back_populates="review_items")
