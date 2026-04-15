from base64 import b64encode
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.config import settings
from app.models.api_key import APIKey
from app.models.ingestion_job import IngestionJob
from app.schemas.ingest import IngestResponse, IngestTextRequest
from app.services.ingestion_service import ingest_text

router = APIRouter(prefix="/ingest", tags=["ingest"])

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_client


def _enqueue_image_job(job_id: str) -> None:
    """Enqueue image job to ARQ."""
    import json

    async def _enqueue():
        r = await get_redis()
        await r.lpush(
            "arq:default:queue", json.dumps({"job_id": job_id, "task": "process_image_job"})
        )

    import asyncio

    asyncio.create_task(_enqueue())


@router.post(
    "/text",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest product data from free-form text",
)
async def ingest_text_endpoint(
    body: IngestTextRequest,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Extract structured product data from a free-form text description.

    The response includes per-field confidence scores.  Fields whose
    confidence fall below the review threshold appear in ``review_items``
    and require human confirmation before the product is considered final.
    """
    return await ingest_text(
        request=body,
        api_key_id=api_key.id,
        db=db,
    )


@router.post(
    "/image",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest product data from an image",
)
async def ingest_image_endpoint(
    file: UploadFile = File(..., description="Product image (JPEG, PNG, WebP, max 5MB)"),
    hint: str | None = Form(default=None, description="Optional text hint"),
    idempotency_key: str | None = Form(default=None, max_length=64),
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Upload a product image for extraction.

    Returns 202 immediately - processing happens asynchronously via ARQ worker.
    Poll the returned job_id to get status and results.
    """
    contents = await file.read()

    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type: {file.content_type}. Allowed: {allowed}",
        )

    if idempotency_key:
        result = await db.execute(
            select(IngestionJob).where(
                IngestionJob.api_key_id == api_key.id,
                IngestionJob.idempotency_key == idempotency_key,
            )
        )
        existing = result.scalars().first()
        if existing:
            return {
                "job_id": str(existing.id),
                "status": existing.status,
                "poll_url": f"/api/v1/jobs/{existing.id}",
            }

    image_b64 = b64encode(contents).decode("utf-8")

    job = IngestionJob(
        api_key_id=api_key.id,
        input_type="image",
        input_payload={
            "image_base64": image_b64,
            "hint": hint,
            "filename": file.filename,
        },
        status="queued",
        idempotency_key=idempotency_key,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from arq import create_pool
    from arq.connections import RedisSettings

    redis_url = settings.REDIS_URL
    host = redis_url.split("://")[1].split(":")[0]
    port = int(redis_url.split(":")[-1].split("/")[0])
    db_num = int(redis_url.split("/")[-1] or 0)

    pool = await create_pool(
        RedisSettings(host=host, port=port, db=db_num),
    )

    await pool.enqueue_job("process_image_job", str(job.id))

    await pool.close()

    return {
        "job_id": str(job.id),
        "status": "queued",
        "poll_url": f"/api/v1/jobs/{job.id}",
    }
