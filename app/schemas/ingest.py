"""
Request and response schemas for ingestion endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.product import ProductOut
from app.schemas.review import ReviewItemOut


class IngestTextRequest(BaseModel):
    """Body for POST /api/v1/ingest/text."""

    text: str = Field(min_length=1, max_length=10_000)
    locale: str = Field(default="en-IN", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    idempotency_key: str | None = Field(default=None, max_length=64)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class IngestResponse(BaseModel):
    """
    Response for synchronous ingest endpoints.

    ``product`` is ``None`` only when the job was queued for async
    processing (future image/batch endpoints).  For text ingestion it
    is always present.

    ``review_items`` lists any fields that fell below the confidence
    threshold and need human review before the product is considered
    final.
    """

    job_id: uuid.UUID
    status: str  # "completed" | "needs_review" | "failed"
    product: ProductOut | None = None
    review_items: list[ReviewItemOut] = Field(default_factory=list)
    processing_ms: int
    created_at: datetime


class IngestImageResponse(BaseModel):
    """Response for async image ingestion."""

    job_id: uuid.UUID
    status: str  # "queued" | "processing" | "completed" | "failed"
    poll_url: str
