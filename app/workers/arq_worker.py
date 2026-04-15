"""
ARQ Worker settings.

Redis connection pool configured from app config.
Includes watchdog cron task for stuck jobs.
"""

from datetime import UTC, datetime, timedelta

import redis.asyncio as redis
from sqlalchemy import select

from app.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.ingestion_job import IngestionJob
from app.workers.tasks import process_image_job

logger = get_logger(__name__)

STUCK_JOB_TIMEOUT_MINUTES = 10


async def sweep_stuck_jobs(ctx: dict) -> None:
    """
    ARQ cron task: Mark jobs stuck in 'processing' for >10 min as 'failed'.

    Runs periodically to catch orphaned processing jobs.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=STUCK_JOB_TIMEOUT_MINUTES)

    async with async_session_maker() as db:
        result = await db.execute(
            select(IngestionJob).where(
                IngestionJob.status == "processing",
                IngestionJob.created_at < cutoff.isoformat(),
            )
        )
        stuck_jobs = result.scalars().all()

        if stuck_jobs:
            logger.warning(
                "Sweeping stuck jobs",
                count=len(stuck_jobs),
                job_ids=[str(j.id) for j in stuck_jobs],
            )

            for job in stuck_jobs:
                job.status = "failed"
                job.error = f"Job timed out after {STUCK_JOB_TIMEOUT_MINUTES} minutes"
                job.completed_at = datetime.now(UTC)

            await db.commit()

        logger.info("Stuck job sweep completed", checked=len(stuck_jobs))


class WorkerSettings:
    """ARQ worker settings."""

    redis_settings = redis.Redis(
        host=settings.REDIS_URL.split("://")[1].split(":")[0],
        port=int(settings.REDIS_URL.split(":")[-1].split("/")[0]),
        db=int(settings.REDIS_URL.split("/")[-1] or 0),
        decode_responses=False,
    )

    job_processing_loop = None
    max_jobs = 10
    max_tries = 1
    retry_delay = 0

    functions = [process_image_job]

    cron_config = {
        "sweep-stuck-jobs": {
            "run_every": 300,
            "run_at_startup": True,
            "task": sweep_stuck_jobs,
        },
    }

    on_startup = None
    on_shutdown = None


async def startup() -> None:
    """Worker startup hook."""
    logger.info("ARQ worker starting up")


async def shutdown() -> None:
    """Worker shutdown hook."""
    await WorkerSettings.redis_settings.close()
    logger.info("ARQ worker shutting down")


WorkerSettings.on_startup = startup
WorkerSettings.on_shutdown = shutdown
