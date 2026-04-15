from fastapi import APIRouter

from app.api.v1 import health, ingest, jobs, products, review

router = APIRouter(prefix="/api/v1")

router.include_router(health.router)
router.include_router(ingest.router)
router.include_router(jobs.router)
router.include_router(products.router)
router.include_router(review.router)
