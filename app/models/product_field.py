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


class ProductField(Base):
    """
    Per-field extraction result for a Product.

    Each extractable field (name, brand, mrp, …) gets its own row so that
    confidence and provenance are tracked at field granularity — the core
    value proposition of KatalogAI.
    """

    __tablename__ = "product_fields"
    __table_args__ = (
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_field_confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. "name", "brand", "mrp"
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 0.0 → 1.0 confidence score for this field
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)

    # who produced this value
    source: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "text_parser" | "vlm" | "ocr" | "manual"
    method: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g. "regex", "ner", "gemini-pro"

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    product: Mapped["Product"] = relationship("Product", back_populates="fields")
