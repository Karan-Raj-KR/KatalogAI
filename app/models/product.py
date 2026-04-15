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


class Product(Base):
    """
    A fully-extracted product record produced by an ingestion job.

    Confidence and provenance live in the companion ``ProductField`` rows
    so that each field can carry its own score independently.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "confidence_overall BETWEEN 0 AND 1",
            name="ck_product_confidence_range",
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

    # --- core identity fields ---
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(200), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # --- pricing ---
    mrp: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    selling_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    # --- measurement ---
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)   # kg, g, ml, pcs …
    weight_grams: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    volume_ml: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)

    # --- classification ---
    hsn_code: Mapped[str | None] = mapped_column(
        String(8),
        ForeignKey("hsn_codes.code"),
        nullable=True,
        index=True,
    )
    ondc_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ondc_subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- description ---
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- quality signal ---
    confidence_overall: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=0.0
    )

    # --- audit ---
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # --- relationships (string refs resolve at mapper-config time) ---
    fields: Mapped[list["ProductField"]] = relationship(
        "ProductField", back_populates="product", cascade="all, delete-orphan"
    )
    review_items: Mapped[list["ReviewItem"]] = relationship(
        "ReviewItem", back_populates="product"
    )
