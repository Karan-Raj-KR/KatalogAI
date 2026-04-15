"""
Ingestion service — orchestrates job creation, extraction, and persistence.

The service layer has zero FastAPI imports — it handles business logic
and can be tested standalone.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, request_id_var
from app.ml.confidence import aggregate_confidence
from app.ml.hsn.retriever import retrieve_hsn
from app.ml.hsn.verifier import verify_hsn
from app.ml.ocr import extract_text_from_image
from app.ml.text_parser import extract_all, extract_hints
from app.ml.vlm import extract_with_gemini, extract_with_gemini_multimodal, merge_extractions
from app.models.ingestion_job import IngestionJob
from app.models.product import Product
from app.models.product_field import ProductField
from app.models.review_item import ReviewItem
from app.schemas.ingest import IngestResponse, IngestTextRequest
from app.schemas.product import FieldValue, ProductOut
from app.schemas.review import ReviewItemOut
from app.services.review_service import evaluate_review_triggers, should_require_review
from app.utils.images import ImageProcessingError, validate_and_process

logger = get_logger(__name__)

_REVIEW_THRESHOLD = 0.70


async def _run_extraction(
    text: str,
    request_id: str,
    db: AsyncSession,
) -> dict[str, tuple[str | None, float]]:
    """
    Run the full extraction pipeline:
    1. Regex pre-pass (text_parser) for hints and high-confidence fields
    2. Gemini 2.5 Flash for complex fields
    3. Retrieve and verify HSN code
    4. Merge results
    """
    hints = extract_hints(text)
    logger.info("Regex pre-pass completed", request_id=request_id, hints=list(hints.keys()))

    regex_result = extract_all(text)

    regex_for_merge: dict[str, tuple[str | None, float]] = {}
    for field, result in regex_result.items():
        regex_for_merge[field] = (result["value"], result["confidence"])

    gemini_result = await extract_with_gemini(text, hints, request_id)

    merged = merge_extractions(regex_for_merge, gemini_result)

    has_gemini = any(
        conf > 0.5 and (value is not None)
        for field, (value, conf) in gemini_result.items()
        if field not in ["mrp", "weight_grams", "volume_ml", "unit"]
    )

    if has_gemini:
        for field, (value, conf) in gemini_result.items():
            if field not in regex_for_merge or regex_for_merge[field][0] is None:
                merged[field] = (value, conf)

    name_val = merged.get("name", (None, 0.0))[0]
    category_val = merged.get("category", (None, 0.0))[0]

    if name_val:
        hsn_matches = await retrieve_hsn(name_val, db, top_k=5)
        if hsn_matches:
            hsn_code, hsn_conf = await verify_hsn(
                product_name=name_val,
                category=category_val,
                matches=hsn_matches,
                request_id=request_id,
            )
            if hsn_code:
                merged["hsn_code"] = (hsn_code, hsn_conf)
                logger.info(
                    "HSN assigned",
                    request_id=request_id,
                    hsn_code=hsn_code,
                    confidence=hsn_conf,
                )

    overall = aggregate_confidence(merged)

    merged["_overall_confidence"] = (str(overall), overall)

    logger.info("Extraction pipeline completed", request_id=request_id, fields=len(merged))
    return merged


def _build_field_rows(
    product_id: uuid.UUID,
    extraction: dict[str, tuple[str | None, float]],
    source: str,
    method: str,
) -> list[ProductField]:
    rows = []
    for field_name, (value, confidence) in extraction.items():
        if value is None and confidence == 0.0:
            continue
        rows.append(
            ProductField(
                product_id=product_id,
                field_name=field_name,
                raw_value=value,
                normalized_value=value,
                confidence=confidence,
                source=source,
                method=method,
            )
        )
    return rows


def _build_review_items(
    job_id: uuid.UUID,
    product_id: uuid.UUID,
    extraction: dict[str, tuple[str | None, float]],
) -> list[ReviewItem]:
    items = []
    for field_name, (value, confidence) in extraction.items():
        if value is not None and confidence < _REVIEW_THRESHOLD:
            items.append(
                ReviewItem(
                    job_id=job_id,
                    product_id=product_id,
                    field_name=field_name,
                    extracted_value=value,
                    confidence=confidence,
                    reason=f"confidence {confidence:.0%} below threshold {_REVIEW_THRESHOLD:.0%}",
                    status="pending",
                )
            )
    return items


def _overall_confidence(extraction: dict[str, tuple[str | None, float]]) -> float:
    scored = [c for _, (v, c) in extraction.items() if v is not None]
    return round(sum(scored) / len(scored), 3) if scored else 0.0


def _field_value(
    extraction: dict[str, tuple[str | None, float]],
    key: str,
    default_source: str = "text_parser",
    default_method: str = "regex",
) -> FieldValue | None:
    if key not in extraction:
        return None
    value, confidence = extraction[key]
    if value is None and confidence == 0.0:
        return None

    method = default_method
    source = default_source

    if key in (
        "name",
        "brand",
        "category",
        "subcategory",
        "description",
        "ondc_category",
        "ondc_subcategory",
    ):
        if key in extraction and confidence > 0.5:
            method = "gemini-2.5-flash"
            source = "vlm"

    return FieldValue(value=value, confidence=confidence, source=source, method=method)


def _product_to_schema(
    product: Product,
    extraction: dict[str, tuple[str | None, float]],
) -> ProductOut:
    return ProductOut(
        id=product.id,
        job_id=product.job_id,
        name=_field_value(extraction, "name")
        or FieldValue(value=product.name, confidence=0.85, source="text_parser", method="regex"),
        brand=_field_value(extraction, "brand"),
        category=_field_value(extraction, "category"),
        subcategory=_field_value(extraction, "subcategory"),
        barcode=_field_value(extraction, "barcode"),
        mrp=_field_value(extraction, "mrp"),
        selling_price=_field_value(extraction, "selling_price"),
        currency=product.currency,
        unit=_field_value(extraction, "unit"),
        weight_grams=_field_value(extraction, "weight_grams"),
        volume_ml=_field_value(extraction, "volume_ml"),
        hsn_code=_field_value(extraction, "hsn_code"),
        ondc_category=_field_value(extraction, "ondc_category"),
        ondc_subcategory=_field_value(extraction, "ondc_subcategory"),
        description=_field_value(extraction, "description"),
        confidence_overall=float(product.confidence_overall),
        created_at=product.created_at,
    )


async def ingest_text(
    request: IngestTextRequest,
    api_key_id: uuid.UUID,
    db: AsyncSession,
) -> IngestResponse:
    request_id = request_id_var.get() or str(uuid.uuid4())
    t0 = time.monotonic()

    logger.info("Starting text ingestion", request_id=request_id, text_length=len(request.text))

    job = IngestionJob(
        api_key_id=api_key_id,
        input_type="text",
        input_payload={"text": request.text, "locale": request.locale},
        status="processing",
        idempotency_key=request.idempotency_key,
    )
    db.add(job)
    await db.flush()

    extraction = await _run_extraction(request.text, request_id, db)
    overall_raw = extraction.get("_overall_confidence", (None, 0.0))
    overall = float(overall_raw[1]) if overall_raw[0] else aggregate_confidence(extraction)

    name_value, _ = extraction.get("name", (request.text[:500], 0.85))
    mrp_raw, _ = extraction.get("mrp", (None, 0.0))
    brand_val, _ = extraction.get("brand", (None, 0.0))
    category_val, _ = extraction.get("category", (None, 0.0))
    barcode_val, _ = extraction.get("barcode", (None, 0.0))
    unit_val, _ = extraction.get("unit", (None, 0.0))
    weight_val, _ = extraction.get("weight_grams", (None, 0.0))
    volume_val, _ = extraction.get("volume_ml", (None, 0.0))
    hsn_val, _ = extraction.get("hsn_code", (None, 0.0))

    product = Product(
        job_id=job.id,
        name=name_value or request.text[:500],
        brand=brand_val,
        category=category_val,
        barcode=barcode_val,
        unit=unit_val,
        weight_grams=float(weight_val) if weight_val else None,
        volume_ml=float(volume_val) if volume_val else None,
        mrp=float(mrp_raw) if mrp_raw else None,
        hsn_code=hsn_val,
        confidence_overall=overall,
    )
    db.add(product)
    await db.flush()

    source = "vlm"
    method = "gemini-2.5-flash"

    field_rows = _build_field_rows(product.id, extraction, source, method)
    db.add_all(field_rows)

    review_rows = _build_review_items(job.id, product.id, extraction)

    hsn_conf = extraction.get("hsn_code", (None, 0.0))[1] if extraction.get("hsn_code") else None
    hsn_verified = hsn_conf is not None and hsn_conf >= 0.65

    triggers = evaluate_review_triggers(extraction, hsn_conf, hsn_verified)
    review_needed = should_require_review(extraction, hsn_conf, hsn_verified)

    if triggers:
        for trigger in triggers:
            logger.info(
                "Review trigger",
                request_id=request_id,
                reason=trigger.reason,
                severity=trigger.severity,
            )

    if review_needed and not review_rows:
        job.status = "needs_review"
        logger.info(
            "Product flagged for review",
            request_id=request_id,
            triggers=[t.reason for t in triggers],
        )
    db.add_all(review_rows)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    status = "needs_review" if review_rows else "completed"
    job.status = status
    job.completed_at = datetime.now(datetime.UTC)
    job.processing_ms = elapsed_ms

    await db.commit()
    await db.refresh(product)
    await db.refresh(job)

    logger.info(
        "Text ingestion completed",
        request_id=request_id,
        status=status,
        fields_extracted=len(extraction),
        review_items=len(review_rows),
        processing_ms=elapsed_ms,
    )

    product_out = _product_to_schema(product, extraction)
    review_out = [
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
        for r in review_rows
    ]

    return IngestResponse(
        job_id=job.id,
        status=status,
        product=product_out,
        review_items=review_out,
        processing_ms=elapsed_ms,
        created_at=job.created_at,
    )


async def process_image_pipeline(
    job: IngestionJob,
    db: AsyncSession,
    request_id: str,
) -> Product | None:
    """
    Process an image ingestion job (called from ARQ worker).

    Pipeline:
    1. Load image from job payload
    2. Validate and process image
    3. Run OCR (with timeout, graceful degradation on failure)
    4. Run multimodal Gemini extraction
    5. Persist product and fields

    Returns:
        Product if successful, None on failure
    """
    t0 = time.monotonic()

    logger.info("Starting image pipeline", request_id=request_id, job_id=str(job.id))

    image_b64 = job.input_payload.get("image_base64")
    if not image_b64:
        raise ValueError("No image data in job payload")

    import base64

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise ValueError(f"Invalid base64 image: {e}")

    try:
        processed = validate_and_process(image_bytes, "image.jpg")
        logger.info(
            "Image validated and processed",
            request_id=request_id,
            size_bytes=len(processed.bytes),
            dimensions=f"{processed.width}x{processed.height}",
        )
    except ImageProcessingError as e:
        raise ValueError(f"Image processing failed: {e}")

    ocr_result = await extract_text_from_image(processed.bytes)
    ocr_text = ocr_result.text
    ocr_confidence = ocr_result.confidence

    logger.info(
        "OCR completed",
        request_id=request_id,
        ocr_text_length=len(ocr_text),
        ocr_confidence=ocr_confidence,
    )

    hints: dict[str, str] = {}

    gemini_result = await extract_with_gemini_multimodal(
        image_bytes=processed.bytes,
        ocr_text=ocr_text,
        hints=hints,
        request_id=request_id,
    )

    merged = gemini_result

    name_val = merged.get("name", (None, 0.0))[0]
    category_val = merged.get("category", (None, 0.0))[0]

    if name_val:
        hsn_matches = await retrieve_hsn(name_val, db, top_k=5)
        if hsn_matches:
            hsn_code, hsn_conf = await verify_hsn(
                product_name=name_val,
                category=category_val,
                matches=hsn_matches,
                request_id=request_id,
            )
            if hsn_code:
                merged["hsn_code"] = (hsn_code, hsn_conf)

    overall_raw = merged.get("_overall_confidence", (None, 0.0))
    overall = float(overall_raw[1]) if overall_raw[0] else aggregate_confidence(merged)

    name_value, _ = merged.get("name", (None, 0.0))
    mrp_raw, _ = merged.get("mrp", (None, 0.0))
    brand_val, _ = merged.get("brand", (None, 0.0))
    category_val, _ = merged.get("category", (None, 0.0))
    barcode_val, _ = merged.get("barcode", (None, 0.0))
    unit_val, _ = merged.get("unit", (None, 0.0))
    weight_val, _ = merged.get("weight_grams", (None, 0.0))
    volume_val, _ = merged.get("volume_ml", (None, 0.0))
    hsn_val, _ = merged.get("hsn_code", (None, 0.0))

    product = Product(
        job_id=job.id,
        name=name_value or "Unknown Product",
        brand=brand_val,
        category=category_val,
        barcode=barcode_val,
        unit=unit_val,
        weight_grams=float(weight_val) if weight_val else None,
        volume_ml=float(volume_val) if volume_val else None,
        mrp=float(mrp_raw) if mrp_raw else None,
        hsn_code=hsn_val,
        confidence_overall=overall,
    )
    db.add(product)
    await db.flush()

    source = "vlm"
    method = "gemini-2.5-flash-multimodal"

    field_rows = _build_field_rows(product.id, merged, source, method)

    if ocr_text:
        field_rows.append(
            ProductField(
                product_id=product.id,
                field_name="ocr_text",
                raw_value=ocr_text,
                normalized_value=ocr_text,
                confidence=ocr_confidence,
                source="ocr",
                method="paddleocr",
            )
        )

    db.add_all(field_rows)

    review_rows = _build_review_items(job.id, product.id, merged)

    hsn_conf = merged.get("hsn_code", (None, 0.0))[1] if merged.get("hsn_code") else None
    hsn_verified = hsn_conf is not None and hsn_conf >= 0.65

    triggers = evaluate_review_triggers(merged, hsn_conf, hsn_verified)
    review_needed = should_require_review(merged, hsn_conf, hsn_verified)

    if triggers:
        for trigger in triggers:
            logger.info(
                "Review trigger (image)",
                request_id=request_id,
                reason=trigger.reason,
                severity=trigger.severity,
            )

    if review_needed and not review_rows:
        from sqlalchemy import update

        from app.models.ingestion_job import IngestionJob

        await db.execute(
            update(IngestionJob).where(IngestionJob.id == job.id).values(status="needs_review")
        )
        logger.info(
            "Image product flagged for review",
            request_id=request_id,
            triggers=[t.reason for t in triggers],
        )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "Image pipeline completed",
        request_id=request_id,
        job_id=str(job.id),
        status="completed",
        fields_extracted=len(merged),
        review_items=len(review_rows),
        processing_ms=elapsed_ms,
    )

    return product
