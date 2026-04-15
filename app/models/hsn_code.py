from sqlalchemy import Numeric, String, Text
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HSNCode(Base):
    """
    HSN (Harmonised System of Nomenclature) reference table.

    Seeded once from the government tariff schedule; used for GST rate
    lookup and ONDC ``taxonomyNode`` mapping.
    """

    __tablename__ = "hsn_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    section: Mapped[str | None] = mapped_column(String(5), nullable=True)
    gst_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )  # percentage, e.g. 18.00
    common_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True, index=True)
