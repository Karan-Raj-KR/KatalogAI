from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.models.api_key import APIKey
from app.models.ingestion_job import IngestionJob
from app.models.product import Product
from app.schemas.job import JobStatusOut
from app.schemas.product import ProductOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    response_model=JobStatusOut,
    summary="Get job status",
)
async def get_job_status(
    job_id: UUID,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> JobStatusOut:
    """
    Get the status of an ingestion job.

    Returns 404 if the job doesn't exist or isn't owned by this API key.
    """
    result = await db.execute(
        select(IngestionJob).where(
            IngestionJob.id == job_id,
            IngestionJob.api_key_id == api_key.id,
        )
    )
    job = result.scalars().first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return JobStatusOut(
        job_id=job.id,
        status=job.status,
        input_type=job.input_type,
        created_at=job.created_at,
        completed_at=job.completed_at,
        processing_ms=job.processing_ms,
        error=job.error,
    )


@router.get(
    "/{job_id}/product",
    response_model=ProductOut,
    summary="Get product from completed job",
)
async def get_job_product(
    job_id: UUID,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    """
    Get the extracted product from a completed job.

    Returns 404 if the job isn't completed or doesn't have a product.
    """
    result = await db.execute(
        select(IngestionJob).where(
            IngestionJob.id == job_id,
            IngestionJob.api_key_id == api_key.id,
        )
    )
    job = result.scalars().first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not completed, status: {job.status}",
        )

    product_result = await db.execute(select(Product).where(Product.job_id == job_id))
    product = product_result.scalars().first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No product found for job",
        )

    return ProductOut(
        id=product.id,
        job_id=product.job_id,
        name=product.name,
        brand=product.brand,
        category=product.category,
        subcategory=product.subcategory,
        barcode=product.barcode,
        mrp=product.mrp,
        selling_price=product.selling_price,
        currency=product.currency,
        unit=product.unit,
        weight_grams=product.weight_grams,
        volume_ml=product.volume_ml,
        hsn_code=product.hsn_code,
        ondc_category=product.ondc_category,
        ondc_subcategory=product.ondc_subcategory,
        description=product.description,
        confidence_overall=float(product.confidence_overall),
        created_at=product.created_at,
    )
