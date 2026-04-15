"""
Confidence aggregation for product fields.

Independent of DB - can be unit tested with no external dependencies.
Weighted mean with cross-source agreement bonus.
"""

from typing import TypedDict


class FieldConfidence(TypedDict):
    """Field confidence with source and method info."""

    value: str | None
    confidence: float
    source: str | None
    method: str | None


WEIGHTS: dict[str, float] = {
    "name": 2.0,
    "brand": 1.0,
    "category": 1.0,
    "subcategory": 0.8,
    "mrp": 2.0,
    "selling_price": 1.5,
    "unit": 1.5,
    "weight_grams": 2.0,
    "volume_ml": 2.0,
    "barcode": 1.2,
    "hsn_code": 2.0,
    "ondc_category": 1.2,
    "ondc_subcategory": 1.0,
    "description": 0.8,
}

REQUIRED_FIELDS = {"name", "mrp", "unit", "weight_grams", "volume_ml"}
CROSS_SOURCE_BONUS = 0.05
MAX_BONUS = 0.05


def aggregate_confidence(
    field_confidences: dict[str, FieldConfidence | tuple[str | None, float]],
) -> float:
    """
    Aggregate per-field confidences into an overall confidence score.

    Args:
        field_confidences: Dict mapping field names to confidence info.
            Values can be:
            - FieldConfidence dict with value, confidence, source, method
            - tuple of (value, confidence)

    Returns:
        Aggregate confidence between 0.0 and 1.0
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for field, info in field_confidences.items():
        if isinstance(info, tuple):
            value, confidence = info
        else:
            value = info.get("value")
            confidence = info.get("confidence", 0.0)

        if value is None or confidence == 0.0:
            continue

        weight = WEIGHTS.get(field, 1.0)
        total_weight += weight
        weighted_sum += confidence * weight

    if total_weight == 0.0:
        return 0.0

    base_confidence = weighted_sum / total_weight

    source_bonus = _calculate_source_agreement_bonus(field_confidences)

    final_confidence = min(base_confidence + source_bonus, 1.0)

    return round(final_confidence, 3)


def _calculate_source_agreement_bonus(
    field_confidences: dict[str, FieldConfidence | tuple[str | None, float]],
) -> float:
    """
    Calculate bonus for cross-source agreement.

    If multiple sources agree on a field value, add a small bonus.
    """
    source_values: dict[str, dict[str, float]] = {}

    for field, info in field_confidences.items():
        if isinstance(info, tuple):
            value, confidence = info
            if value is None or confidence == 0.0:
                continue
            source = "unknown"
        else:
            value = info.get("value")
            confidence = info.get("confidence", 0.0)
            source = info.get("source") or "unknown"

            if value is None or confidence == 0.0:
                continue

            if source not in source_values:
                source_values[source] = {}
            source_values[source][field] = value

    if len(source_values) < 2:
        return 0.0

    agreeing_fields = 0
    for field in source_values.get("text_parser", {}):
        if "vlm" in source_values:
            if field in source_values["vlm"]:
                v = source_values["vlm"][field]
                if v == source_values["text_parser"][field]:
                    agreeing_fields += 1

    return min(agreeing_fields * CROSS_SOURCE_BONUS, MAX_BONUS)


def check_required_fields(
    field_confidences: dict[str, FieldConfidence | tuple[str | None, float]],
) -> dict[str, bool]:
    """
    Check which required fields are present and have valid confidence.

    Args:
        field_confidences: Dict of field confidences

    Returns:
        Dict mapping field names to True if present, False otherwise
    """
    result = {}
    for field in REQUIRED_FIELDS:
        if field in field_confidences:
            info = field_confidences[field]
            if isinstance(info, tuple):
                value, confidence = info
                result[field] = value is not None and confidence > 0.0
            else:
                value = info.get("value")
                confidence = info.get("confidence", 0.0)
                result[field] = value is not None and confidence > 0.0
        else:
            result[field] = False
    return result


def has_low_confidence(
    field_confidences: dict[str, FieldConfidence | tuple[str | None, float]],
    threshold: float = 0.75,
) -> bool:
    """
    Check if overall confidence is below threshold.

    Args:
        field_confidences: Dict of field confidences
        threshold: Confidence threshold (default 0.75)

    Returns:
        True if aggregate confidence is below threshold
    """
    return aggregate_confidence(field_confidences) < threshold
