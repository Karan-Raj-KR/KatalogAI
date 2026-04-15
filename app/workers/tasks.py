"""
ARQ tasks for background job processing.
"""

import traceback
import uuid
from datetime import datetime

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.ingestion_job import IngestionJob

logger = get_logger(__name__)


async def process_image_job(ctx: dict, job_id: str) -> None:
    """
    Process an image ingestion job.

    This task runs the full pipeline:
    1. Load job from DB
    2. Run OCR on image
    3. Run multimodal Gemini extraction
    4. Persist product and fields
    5. Update job status

    Catches ALL exceptions - never lets task crash silently.
    Marks job failed with sanitized error on any exception.
    """
    request_id = str(uuid.uuid4())
    logger.info("Starting image job processing", request_id=request_id, job_id=job_id)

    async with async_session_maker() as db:
        result = await db.execute(select(IngestionJob).where(IngestionJob.id == uuid.UUID(job_id)))
        job = result.scalars().first()

        if not job:
            logger.error("Job not found", request_id=request_id, job_id=job_id)
            return

        try:
            from app.services.ingestion_service import process_image_pipeline

            await process_image_pipeline(job, db, request_id)

            job.status = "completed"
            job.completed_at = datetime.utcnow()
            await db.commit()

            logger.info(
                "Image job completed successfully",
                request_id=request_id,
                job_id=job_id,
            )

        except Exception as exc:
            error_msg = str(exc)
            sanitized = error_msg[:500] if error_msg else "Unknown error"

            logger.error(
                "Image job failed",
                request_id=request_id,
                job_id=job_id,
                error=error_msg,
                traceback=traceback.format_exc(),
            )

            job.status = "failed"
            job.error = sanitized
            job.completed_at = datetime.utcnow()
            await db.commit()
