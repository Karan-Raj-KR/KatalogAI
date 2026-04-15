"""
Pydantic schemas for product data.

The central design principle: every extractable field is wrapped in a
``FieldValue`` envelope that carries the value itself, a 0–1 confidence
score, and the source/method that produced it.  Consumers can decide at
read-time which fields they trust enough to use.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FieldValue(BaseModel):
    """Per-field extraction result with confidence and provenance."""

    value: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    source: str  # "text_parser" | "vlm" | "ocr" | "manual"
    method: str | None = None  # e.g. "regex", "ner", "gemini-1.5-pro"


class ProductOut(BaseModel):
    """Full product record returned to API clients."""

    id: uuid.UUID
    job_id: uuid.UUID

    # core identity
    name: FieldValue
    brand: FieldValue | None = None
    category: FieldValue | None = None
    subcategory: FieldValue | None = None
    barcode: FieldValue | None = None

    # pricing
    mrp: FieldValue | None = None
    selling_price: FieldValue | None = None
    currency: str = "INR"

    # measurement
    unit: FieldValue | None = None
    weight_grams: FieldValue | None = None
    volume_ml: FieldValue | None = None

    # classification
    hsn_code: FieldValue | None = None
    ondc_category: FieldValue | None = None
    ondc_subcategory: FieldValue | None = None

    # description
    description: FieldValue | None = None

    # aggregate quality signal
    confidence_overall: float = Field(ge=0.0, le=1.0)

    created_at: datetime

    model_config = {"from_attributes": True}
