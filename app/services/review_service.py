"""
Review trigger logic - determines when products need human review.

Zero FastAPI imports - purely business logic.
"""

from dataclasses import dataclass

from app.ml.confidence import aggregate_confidence, check_required_fields


@dataclass
class ReviewTrigger:
    """A trigger that causes a product to need review."""

    reason: str
    severity: str  # "low" | "medium" | "high"


def evaluate_review_triggers(
    field_confidences: dict[str, tuple[str | None, float]],
    hsn_score: float | None = None,
    hsn_verified: bool = True,
) -> list[ReviewTrigger]:
    """
    Evaluate all review triggers for a product.

    Triggers:
    - overall < 0.75 → low_overall_conf
    - missing name/mrp/pack_size (unit + weight/volume) → missing_required
    - HSN top-1 in [0.65, 0.80] or verifier returned unknown → hsn_ambiguous

    Args:
        field_confidences: Dict of field confidences
        hsn_score: HSN confidence score from verifier (None if no HSN)
        hsn_verified: Whether HSN was verified (False = unknown/ambiguous)

    Returns:
        List of ReviewTrigger objects
    """
    triggers = []

    overall = aggregate_confidence(field_confidences)
    if overall < 0.75:
        triggers.append(
            ReviewTrigger(
                reason=f"low_overall_conf: {overall:.2f} < 0.75",
                severity="high",
            )
        )

    required_check = check_required_fields(field_confidences)
    missing = [k for k, v in required_check.items() if not v]
    if missing:
        triggers.append(
            ReviewTrigger(
                reason=f"missing_required: {', '.join(missing)}",
                severity="high",
            )
        )

    if hsn_score is not None:
        if 0.65 <= hsn_score <= 0.80:
            triggers.append(
                ReviewTrigger(
                    reason=f"hsn_ambiguous: score {hsn_score:.2f} in [0.65, 0.80]",
                    severity="medium",
                )
            )

    if not hsn_verified and hsn_score is not None:
        triggers.append(
            ReviewTrigger(
                reason="hsn_ambiguous: verifier returned unknown",
                severity="medium",
            )
        )

    return triggers


def should_require_review(
    field_confidences: dict[str, tuple[str | None, float]],
    hsn_score: float | None = None,
    hsn_verified: bool = True,
) -> bool:
    """
    Determine if a product should require human review.

    Returns True if any high-severity trigger fires.
    """
    triggers = evaluate_review_triggers(field_confidences, hsn_score, hsn_verified)
    return any(t.severity == "high" for t in triggers)
