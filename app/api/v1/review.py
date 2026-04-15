from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.models.api_key import APIKey
from app.models.ingestion_job import IngestionJob
from app.models.product import Product
from app.models.product_field import ProductField
from app.models.review_item import ReviewItem
from app.schemas.review import ReviewItemOut

router = APIRouter(prefix="/review", tags=["review"])


class ResolveReviewRequest(BaseModel):
    """Request body for resolving a review item."""

    value: dict[str, str] | None = None
    action: str  # "accept" | "override" | "dismiss"


@router.get("", response_model=list[ReviewItemOut])
async def list_pending_reviews(
    limit: int = 50,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewItemOut]:
    """
    List pending review items for this API key.
    """
    job_subquery = (
        select(IngestionJob.id).where(IngestionJob.api_key_id == api_key.id).scalar_subquery()
    )

    product_subquery = select(Product.id).where(Product.job_id.in_(job_subquery)).scalar_subquery()

    result = await db.execute(
        select(ReviewItem)
        .where(
            ReviewItem.product_id.in_(product_subquery),
            ReviewItem.status == "pending",
        )
        .limit(limit)
    )
    items = result.scalars().all()

    return [
        ReviewItemOut(
            id=r.id,
            job_id=r.job_id,
            product_id=r.product_id,
            field_name=r.field_name,
            extracted_value=r.extracted_value,
            suggested_value=r.suggested_value,
            confidence=float(r.confidence),
            reason=r.reason,
            status=r.status,
            reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at,
            created_at=r.created_at,
        )
        for r in items
    ]


@router.post("/{item_id}/resolve", response_model=ReviewItemOut)
async def resolve_review_item(
    item_id: UUID,
    body: ResolveReviewRequest,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> ReviewItemOut:
    """
    Resolve a review item.

    Actions:
    - accept: Use the extracted value as-is
    - override: Use the provided value in body
    - dismiss: Remove the review item without changes
    """
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == item_id))
    item = result.scalars().first()

    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    product_result = await db.execute(select(Product).where(Product.id == item.product_id))
    product = product_result.scalars().first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    job_result = await db.execute(select(IngestionJob).where(IngestionJob.id == product.job_id))
    job = job_result.scalars().first()

    if job.api_key_id != api_key.id:
        raise HTTPException(status_code=404, detail="Review item not found")

    if body.action == "accept":
        final_value = item.extracted_value
        confidence = item.confidence
    elif body.action == "override":
        if not body.value:
            raise HTTPException(status_code=400, detail="value required for override action")
        field_name = item.field_name
        final_value = body.value.get(field_name)
        if not final_value:
            raise HTTPException(status_code=400, detail=f"value for field '{field_name}' required")
        confidence = 1.0
    elif body.action == "dismiss":
        item.status = "dismissed"
        await db.commit()
        await db.refresh(item)
        return ReviewItemOut(
            id=item.id,
            job_id=item.job_id,
            product_id=item.product_id,
            field_name=item.field_name,
            extracted_value=item.extracted_value,
            suggested_value=item.suggested_value,
            confidence=float(item.confidence),
            reason=item.reason,
            status=item.status,
            reviewed_by=item.reviewed_by,
            reviewed_at=item.reviewed_at,
            created_at=item.created_at,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    setattr(product, item.field_name, final_value)

    existing_field = await db.execute(
        select(ProductField).where(
            ProductField.product_id == item.product_id,
            ProductField.field_name == item.field_name,
        )
    )
    field_row = existing_field.scalars().first()

    if field_row:
        field_row.raw_value = final_value
        field_row.normalized_value = final_value
        field_row.confidence = confidence
        field_row.source = "human"
        field_row.method = "manual"
    else:
        new_field = ProductField(
            product_id=item.product_id,
            field_name=item.field_name,
            raw_value=final_value,
            normalized_value=final_value,
            confidence=confidence,
            source="human",
            method="manual",
        )
        db.add(new_field)

    item.status = "resolved"
    item.reviewed_by = str(api_key.id)
    from datetime import datetime

    item.reviewed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(item)
    await db.refresh(product)

    return ReviewItemOut(
        id=item.id,
        job_id=item.job_id,
        product_id=item.product_id,
        field_name=item.field_name,
        extracted_value=item.extracted_value,
        suggested_value=item.suggested_value,
        confidence=float(item.confidence),
        reason=item.reason,
        status=item.status,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
    )
