"""System and retry prompt builders for the extraction agent."""

from __future__ import annotations

_PERSONA = """You are an AI extraction agent for Indian kirana store products.
Your job is to extract structured product data by calling the available tools in the right sequence.
Think step-by-step about which tools to call based on the input type and what has been extracted so far.
Stop calling tools once you have extracted all the data you can — do not repeat tools unnecessarily."""

_TEXT_GUIDANCE = """
## Tool Usage for Text Input
1. Call `extract_text_fields` with strategy="full" — runs regex + AI extraction on the product text
2. If a product name was found, call `retrieve_hsn_candidates` with that name (add category if available)
3. If HSN candidates were returned, call `verify_hsn_code` to pick the best match
4. Stop — do not call `run_ocr` or `extract_image_fields` (no image is provided)
"""

_IMAGE_GUIDANCE = """
## Tool Usage for Image Input
1. Call `run_ocr` to extract text from the image
2. Call `extract_image_fields` with strategy="ocr_grounded" for multimodal AI extraction
3. If a product name was found, call `retrieve_hsn_candidates` with that name
4. If HSN candidates were returned, call `verify_hsn_code` to pick the best match
5. Stop when all fields have been extracted
"""

_RULES = """
## Rules
- Do NOT fabricate data. Only extract what is clearly present in the input.
- Call each tool at most once per pass unless retrying with a deliberately different strategy.
- After useful tool calls are complete, stop — do not repeat tools that already returned good results.
"""


def build_system_prompt(input_type: str, pass_num: int) -> str:
    guidance = _TEXT_GUIDANCE if input_type == "text" else _IMAGE_GUIDANCE
    return f"{_PERSONA}\n{guidance}\n{_RULES}"


def build_retry_context(
    prior_confidence: float,
    prior_result: dict,
    ocr_confidence: float | None,
    input_type: str,
) -> str:
    from app.ml.confidence import REQUIRED_FIELDS

    missing = [
        f for f in REQUIRED_FIELDS
        if f not in prior_result or prior_result[f][0] is None
    ]
    low_conf = [
        f for f, (v, c) in prior_result.items()
        if v is not None and c < 0.60 and not f.startswith("_")
    ]

    lines = [
        "## RETRY CONTEXT (Pass 2 — Self-Correction)",
        f"Pass 1 overall confidence: {prior_confidence:.0%} (below 0.75 threshold — retry required)",
        f"Missing required fields: {', '.join(missing) if missing else 'none'}",
        f"Low-confidence fields (<60%): {', '.join(low_conf) if low_conf else 'none'}",
        "",
        "## Suggested Alternative Strategies",
    ]

    suggestions: list[str] = []

    if input_type == "image" and ocr_confidence is not None and ocr_confidence < 0.50:
        suggestions.append(
            f"OCR confidence was low ({ocr_confidence:.0%}). Try extract_image_fields with "
            "strategy='vision_only' to let the AI read the image directly without OCR text."
        )
    if missing or low_conf:
        suggestions.append(
            "For fields that are missing or low-confidence, try calling the extraction tool "
            "again — the first pass may have lacked sufficient context."
        )
    if "hsn_code" not in prior_result:
        name_val = prior_result.get("name", (None,))[0]
        if name_val:
            suggestions.append(
                f"HSN was not found. Call retrieve_hsn_candidates with "
                f"product_name='{name_val[:60]}', then call verify_hsn_code with the results."
            )
    if not suggestions:
        suggestions.append(
            "Try calling extraction tools again with different strategies to improve coverage."
        )

    lines.extend(f"- {s}" for s in suggestions)
    lines.append("")
    lines.append(
        "Call any tools you need. Prioritise fields that were null or below 60% confidence in pass 1."
    )

    return "\n".join(lines)
