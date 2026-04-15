"""
PaddleOCR wrapper with timeout handling.

On timeout or failure, returns empty text + 0.0 confidence - never fails the job.
"""

import asyncio
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

OCR_TIMEOUT = 10.0


@dataclass
class OCRResult:
    """Result from OCR processing."""

    text: str
    confidence: float


_ocr_model = None


def _get_ocr_model():
    """Lazy-load PaddleOCR model."""
    global _ocr_model
    if _ocr_model is None:
        from paddleocr import PaddleOCR

        _ocr_model = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False,
            use_gpu=False,
        )
    return _ocr_model


async def extract_text_from_image(image_bytes: bytes) -> OCRResult:
    """
    Extract text from image using PaddleOCR.

    Time-boxed to 10 seconds. On timeout or failure:
    - Returns empty string + 0.0 confidence
    - Logs warning but does NOT fail the job

    Args:
        image_bytes: JPEG/PNG image bytes

    Returns:
        OCRResult with extracted text and mean confidence
    """
    try:
        ocr = _get_ocr_model()
    except Exception as e:
        logger.warning("Failed to load OCR model, skipping OCR", error=str(e))
        return OCRResult(text="", confidence=0.0)

    def _run_ocr():
        try:
            result = ocr.ocr(image_bytes, cls=True)
            if not result or not result[0]:
                return OCRResult(text="", confidence=0.0)

            texts = []
            confidences = []

            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0]
                    conf = line[1][1]
                    if text and text.strip():
                        texts.append(text.strip())
                        confidences.append(conf)

            if not texts:
                return OCRResult(text="", confidence=0.0)

            mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
            full_text = " ".join(texts)

            return OCRResult(text=full_text, confidence=mean_conf)

        except Exception as e:
            logger.warning("OCR processing failed", error=str(e))
            return OCRResult(text="", confidence=0.0)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_ocr),
            timeout=OCR_TIMEOUT,
        )
        logger.info(
            "OCR completed",
            text_length=len(result.text),
            confidence=result.confidence,
        )
        return result

    except TimeoutError:
        logger.warning("OCR timed out after 10 seconds, skipping OCR")
        return OCRResult(text="", confidence=0.0)
    except Exception as e:
        logger.warning("OCR failed unexpectedly", error=str(e))
        return OCRResult(text="", confidence=0.0)
