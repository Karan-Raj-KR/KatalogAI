from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.models.api_key import APIKey
from app.models.ingestion_job import IngestionJob
from app.models.product import Product
from app.models.product_field import ProductField
from app.schemas.product import FieldValue, ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=dict[str, Any])
async def list_products(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: UUID | None = Query(default=None, description="Cursor for pagination"),
    status: str | None = Query(
        default=None, description="Filter by status (completed, needs_review)"
    ),
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    List products for this API key with cursor-based pagination.

    Returns products with pagination cursor, tenant-scoped.
    """
    job_subquery = (
        select(IngestionJob.id).where(IngestionJob.api_key_id == api_key.id).scalar_subquery()
    )

    query = select(Product).where(Product.job_id.in_(job_subquery))

    if status == "completed":
        query = query.where(Product.confidence_overall >= 0.75)
    elif status == "needs_review":
        query = query.where(Product.confidence_overall < 0.75)

    if cursor:
        query = query.where(Product.id < cursor)

    query = query.order_by(Product.id.desc()).limit(limit + 1)

    result = await db.execute(query)
    product_rows = result.scalars().all()

    next_cursor = None
    if len(product_rows) > limit:
        product_rows = product_rows[:limit]
        next_cursor = product_rows[-1].id

    items = []
    for p in product_rows:
        items.append(
            {
                "id": str(p.id),
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "mrp": float(p.mrp) if p.mrp else None,
                "confidence_overall": float(p.confidence_overall),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        )

    return {
        "items": items,
        "next_cursor": str(next_cursor) if next_cursor else None,
    }


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: UUID,
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    """
    Get full product with per-field confidences.

    Returns product plus all extracted fields with their confidence scores.
    """
    job_subquery = (
        select(IngestionJob.id).where(IngestionJob.api_key_id == api_key.id).scalar_subquery()
    )

    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.job_id.in_(job_subquery),
        )
    )
    product = result.scalars().first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    fields_result = await db.execute(
        select(ProductField).where(ProductField.product_id == product_id)
    )
    fields = fields_result.scalars().all()

    field_dict: dict[str, FieldValue] = {}
    for f in fields:
        field_dict[f.field_name] = FieldValue(
            value=f.raw_value,
            confidence=float(f.confidence),
            source=f.source,
            method=f.method,
        )

    return ProductOut(
        id=product.id,
        job_id=product.job_id,
        name=field_dict.get("name")
        or FieldValue(value=product.name, confidence=1.0, source="human", method="manual"),
        brand=field_dict.get("brand"),
        category=field_dict.get("category"),
        subcategory=field_dict.get("subcategory"),
        barcode=field_dict.get("barcode"),
        mrp=field_dict.get("mrp"),
        selling_price=field_dict.get("selling_price"),
        currency=product.currency,
        unit=field_dict.get("unit"),
        weight_grams=field_dict.get("weight_grams"),
        volume_ml=field_dict.get("volume_ml"),
        hsn_code=field_dict.get("hsn_code"),
        ondc_category=field_dict.get("ondc_category"),
        ondc_subcategory=field_dict.get("ondc_subcategory"),
        description=field_dict.get("description"),
        confidence_overall=float(product.confidence_overall),
        created_at=product.created_at,
    )


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: UUID,
    updates: dict[str, Any],
    api_key: APIKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    """
    Partial update a product.

    Edited fields get source='human', confidence=1.0.
    """
    job_subquery = (
        select(IngestionJob.id).where(IngestionJob.api_key_id == api_key.id).scalar_subquery()
    )

    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.job_id.in_(job_subquery),
        )
    )
    product = result.scalars().first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    editable_fields = {
        "name",
        "brand",
        "category",
        "subcategory",
        "barcode",
        "mrp",
        "selling_price",
        "unit",
        "weight_grams",
        "volume_ml",
        "hsn_code",
        "description",
        "ondc_category",
        "ondc_subcategory",
    }

    for field, value in updates.items():
        if field not in editable_fields:
            continue
        if hasattr(product, field):
            setattr(product, field, value)

        existing_field = await db.execute(
            select(ProductField).where(
                ProductField.product_id == product_id,
                ProductField.field_name == field,
            )
        )
        field_row = existing_field.scalars().first()

        if field_row:
            field_row.raw_value = str(value) if value else None
            field_row.normalized_value = str(value) if value else None
            field_row.confidence = 1.0
            field_row.source = "human"
            field_row.method = "manual"
        else:
            new_field = ProductField(
                product_id=product_id,
                field_name=field,
                raw_value=str(value) if value else None,
                normalized_value=str(value) if value else None,
                confidence=1.0,
                source="human",
                method="manual",
            )
            db.add(new_field)

    product.confidence_overall = 1.0
    await db.commit()
    await db.refresh(product)

    return await get_product(product_id, api_key, db)
