import uuid
from datetime import datetime

from pydantic import BaseModel


class JobStatusOut(BaseModel):
    """Ingestion job status — returned by GET /jobs/{job_id}."""

    job_id: uuid.UUID
    status: str  # queued | processing | completed | failed | needs_review
    input_type: str
    created_at: datetime
    completed_at: datetime | None = None
    processing_ms: int | None = None
    error: str | None = None

    model_config = {"from_attributes": True}
