"""
Vision Language Model integration for product extraction.

Uses Gemini 2.5 Flash with structured JSON output for product data extraction.
Supports both text-only and multimodal (image + OCR text) extraction.
Calibration: Gemini self-reported confidence × 0.85 to account for overconfidence.
"""

import json
import re
from pathlib import Path
from typing import TypedDict

import google.genai as genai
from google.genai import types

from app.config import settings
from app.core.logging import get_logger

CALIBRATION_FACTOR = 0.85

logger = get_logger(__name__)


class GeminiExtraction(TypedDict):
    name: str | None
    brand: str | None
    category: str | None
    subcategory: str | None
    mrp: float | None
    selling_price: float | None
    unit: str | None
    weight_grams: float | None
    volume_ml: float | None
    barcode: str | None
    description: str | None
    ondc_category: str | None
    ondc_subcategory: str | None
    confidence: float


def _load_prompt() -> str:
    prompt_path = Path(__file__).parent / "prompts" / "extract_product.txt"
    return prompt_path.read_text()


def _load_multimodal_prompt() -> str:
    prompt_path = Path(__file__).parent / "prompts" / "extract_product_multimodal.txt"
    return prompt_path.read_text()


def _parse_gemini_response(text: str) -> dict | None:
    """Parse JSON from Gemini response, handling potential markdown wrappers."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def _build_prompt(text: str, hints: dict[str, str]) -> str:
    """Build the text-only prompt with hints injected."""
    prompt_template = _load_prompt()

    hints_str = ", ".join(f"{k}: {v}" for k, v in hints.items()) if hints else "No hints available"
    prompt = prompt_template.replace("{{hints}}", hints_str)
    prompt = prompt.replace("{{text}}", text)

    return prompt


def _build_multimodal_prompt(ocr_text: str, hints: dict[str, str]) -> str:
    """Build the multimodal prompt with OCR text and hints."""
    prompt_template = _load_multimodal_prompt()

    ocr_section = ocr_text if ocr_text else "No text detected in image"
    hints_str = ", ".join(f"{k}: {v}" for k, v in hints.items()) if hints else "No hints available"

    prompt = prompt_template.replace("{{ocr_text}}", ocr_section)
    prompt = prompt.replace("{{hints}}", hints_str)

    return prompt


def _parse_extraction_result(
    extracted: dict,
    request_id: str,
) -> dict[str, tuple[str | None, float]]:
    """Parse Gemini extraction result into field dict."""
    raw_confidence = extracted.get("confidence", 0.5)
    calibrated_confidence = raw_confidence * CALIBRATION_FACTOR

    result: dict[str, tuple[str | None, float]] = {}

    field_mappings = {
        "name": "name",
        "brand": "brand",
        "category": "category",
        "subcategory": "subcategory",
        "unit": "unit",
        "barcode": "barcode",
        "description": "description",
        "ondc_category": "ondc_category",
        "ondc_subcategory": "ondc_subcategory",
    }

    for json_key, field_name in field_mappings.items():
        if value := extracted.get(json_key):
            result[field_name] = (str(value), calibrated_confidence)

    if mrp := extracted.get("mrp"):
        result["mrp"] = (str(mrp), calibrated_confidence)

    if sp := extracted.get("selling_price"):
        result["selling_price"] = (str(sp), calibrated_confidence)

    if weight := extracted.get("weight_grams"):
        result["weight_grams"] = (str(weight), calibrated_confidence)

    if vol := extracted.get("volume_ml"):
        result["volume_ml"] = (str(vol), calibrated_confidence)

    logger.info(
        "Gemini extraction completed",
        request_id=request_id,
        fields_extracted=len(result),
        raw_confidence=raw_confidence,
        calibrated_confidence=calibrated_confidence,
    )

    return result


async def extract_with_gemini(
    text: str,
    hints: dict[str, str],
    request_id: str,
) -> dict[str, tuple[str | None, float]]:
    """
    Extract product fields using Gemini 2.5 Flash (text only).

    Args:
        text: Product description text
        hints: Pre-extracted hints from regex (mrp, weight, etc.)
        request_id: Request ID for logging

    Returns:
        Dict mapping field names to (value, confidence) tuples
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, falling back to regex only", request_id=request_id)
        return {}

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        prompt = _build_prompt(text, hints)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )

        if not response.text:
            logger.error("Empty response from Gemini", request_id=request_id)
            return {}

        extracted = _parse_gemini_response(response.text)
        if not extracted:
            logger.error(
                "Failed to parse Gemini JSON response",
                request_id=request_id,
                response=response.text[:200],
            )
            return {}

        return _parse_extraction_result(extracted, request_id)

    except Exception as e:
        logger.error("Gemini extraction failed", request_id=request_id, error=str(e))
        return {}


async def extract_with_gemini_multimodal(
    image_bytes: bytes,
    ocr_text: str,
    hints: dict[str, str],
    request_id: str,
) -> dict[str, tuple[str | None, float]]:
    """
    Extract product fields using Gemini 2.5 Flash with image + OCR text.

    Uses structured JSON output mode - no free-text parsing.

    Args:
        image_bytes: Processed JPEG image bytes
        ocr_text: Text extracted from image via OCR
        hints: Pre-extracted hints (e.g., from text_parser)
        request_id: Request ID for logging

    Returns:
        Dict mapping field names to (value, confidence) tuples
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, cannot process image", request_id=request_id)
        return {}

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        prompt = _build_multimodal_prompt(ocr_text, hints)

        image_part = types.Part(
            inline_data=types.Blob(
                data=image_bytes,
                mime_type="image/jpeg",
            )
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )

        if not response.text:
            logger.error("Empty response from Gemini multimodal", request_id=request_id)
            return {}

        extracted = _parse_gemini_response(response.text)
        if not extracted:
            logger.error(
                "Failed to parse Gemini JSON response",
                request_id=request_id,
                response=response.text[:200],
            )
            return {}

        return _parse_extraction_result(extracted, request_id)

    except Exception as e:
        logger.error("Gemini multimodal extraction failed", request_id=request_id, error=str(e))
        return {}


def merge_extractions(
    regex_result: dict[str, tuple[str | None, float]],
    gemini_result: dict[str, tuple[str | None, float]],
) -> dict[str, tuple[str | None, float]]:
    """
    Merge regex and Gemini extractions.

    Rules:
    - Regex fields with confidence >= 0.95 are kept (clean match)
    - Gemini fills in missing fields
    - For overlapping fields, prefer higher confidence
    """
    merged: dict[str, tuple[str | None, float]] = {}

    regex_clean_confidence = 0.95

    for field, (value, conf) in regex_result.items():
        if value is not None:
            if conf >= regex_clean_confidence:
                merged[field] = (value, conf)
            elif field not in gemini_result:
                merged[field] = (value, conf)

    for field, (value, conf) in gemini_result.items():
        if value is not None:
            if field not in merged:
                merged[field] = (value, conf)
            elif conf > merged[field][1]:
                merged[field] = (value, conf)

    return merged
