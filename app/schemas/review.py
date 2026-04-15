import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReviewItemOut(BaseModel):
    """A single field flagged for human review."""

    id: uuid.UUID
    job_id: uuid.UUID
    product_id: uuid.UUID | None = None
    field_name: str
    extracted_value: str | None = None
    suggested_value: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str | None = None
    status: str  # "pending" | "accepted" | "rejected"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDecision(BaseModel):
    """Payload for resolving a review item."""

    action: Literal["accept", "reject"]
    corrected_value: str | None = None  # required when action == "accept" and value differs
