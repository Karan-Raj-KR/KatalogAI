"""
HSN verifier using Gemini for ambiguous matches.

Rules:
- If top-1 score > 0.80 AND gap to top-2 > 0.05 → accept directly
- Else send top-5 to Gemini Flash with product info → pick best or return unknown
"""

import json
import re
from pathlib import Path

import google.genai as genai
from google.genai import types

from app.config import settings
from app.core.logging import get_logger
from app.ml.hsn.retriever import HSNMatch

logger = get_logger(__name__)

CLEAR_MATCH_THRESHOLD = 0.80
GAP_THRESHOLD = 0.05


def _load_prompt() -> str:
    prompt_path = Path(__file__).parent / ".." / "prompts" / "verify_hsn.txt"
    return prompt_path.read_text()


def _parse_gemini_response(text: str) -> dict | None:
    """Parse JSON from Gemini response."""
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


async def verify_hsn(
    product_name: str,
    category: str | None,
    matches: list[HSNMatch],
    request_id: str,
) -> tuple[str | None, float]:
    """
    Verify and select the best HSN code from retrieval results.

    Args:
        product_name: Product name/description
        category: Extracted category
        matches: Top-5 matches from retriever
        request_id: Request ID for logging

    Returns:
        Tuple of (selected_code or None, confidence)
    """
    if not matches:
        logger.info("No HSN matches found", request_id=request_id)
        return None, 0.0

    top_1 = matches[0]

    if len(matches) >= 2:
        gap = top_1.score - matches[1].score
        if top_1.score > CLEAR_MATCH_THRESHOLD and gap > GAP_THRESHOLD:
            logger.info(
                "HSN match clear, accepting directly",
                request_id=request_id,
                code=top_1.code,
                score=top_1.score,
                gap=gap,
            )
            return top_1.code, top_1.score

    if not settings.GEMINI_API_KEY:
        logger.warning(
            "GEMINI_API_KEY not set, returning top match",
            request_id=request_id,
        )
        return top_1.code, top_1.score * 0.85

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        prompt_template = _load_prompt()

        options_text = "\n".join(
            [
                f"{i + 1}. {m.code} - {m.description} (score: {m.score:.2f})"
                for i, m in enumerate(matches[:5])
            ]
        )

        product_context = product_name
        if category:
            product_context += f" | Category: {category}"

        prompt = prompt_template.replace("{{product_context}}", product_context)
        prompt = prompt.replace("{{options}}", options_text)

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_tokens=512,
            ),
        )

        if not response.text:
            logger.error("Empty response from Gemini", request_id=request_id)
            return top_1.code, top_1.score * 0.85

        parsed = _parse_gemini_response(response.text)
        if not parsed:
            logger.error(
                "Failed to parse Gemini response",
                request_id=request_id,
                response=response.text[:200],
            )
            return top_1.code, top_1.score * 0.85

        selected_code = parsed.get("selected_code")
        if selected_code and selected_code in [m.code for m in matches]:
            confidence = parsed.get("confidence", 0.7)
            logger.info(
                "HSN verified via Gemini",
                request_id=request_id,
                code=selected_code,
                confidence=confidence,
            )
            return selected_code, confidence

        logger.info(
            "Gemini returned unknown, using top match",
            request_id=request_id,
        )
        return top_1.code, top_1.score * 0.85

    except Exception as e:
        logger.error(
            "HSN verification failed, using top match",
            request_id=request_id,
            error=str(e),
        )
        return top_1.code, top_1.score * 0.85
