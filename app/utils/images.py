"""
Image processing utilities.

Validates MIME type, strips EXIF, resizes, encodes as JPEG.
"""

import io
from dataclasses import dataclass

from PIL import Image

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_MB = 5
MAX_LONGEST_SIDE = 1600
JPEG_QUALITY = 85


class ImageProcessingError(Exception):
    """Raised when image processing fails."""

    pass


@dataclass
class ProcessedImage:
    """Result of image processing."""

    bytes: bytes
    width: int
    height: int
    format: str


def validate_and_process(
    image_bytes: bytes,
    filename: str = "image",
) -> ProcessedImage:
    """
    Validate and process an image.

    Args:
        image_bytes: Raw image bytes
        filename: Original filename for MIME detection

    Returns:
        ProcessedImage with processed bytes and metadata

    Raises:
        ImageProcessingError: If validation or processing fails
    """
    if len(image_bytes) > MAX_SIZE_MB * 1024 * 1024:
        raise ImageProcessingError(f"Image exceeds {MAX_SIZE_MB}MB limit")

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise ImageProcessingError(f"Cannot open image: {e}")

    mime_type = _detect_mime(img, filename)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ImageProcessingError(f"Invalid MIME type: {mime_type}. Allowed: {ALLOWED_MIME_TYPES}")

    if img.mode == "RGBA" and mime_type == "image/jpeg":
        img = img.convert("RGB")

    img = _strip_exif(img)

    img = _resize_if_needed(img)

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    processed_bytes = output.getvalue()

    return ProcessedImage(
        bytes=processed_bytes,
        width=img.width,
        height=img.height,
        format="JPEG",
    )


def _detect_mime(img: Image.Image, filename: str) -> str:
    """Detect MIME type from PIL image or filename."""
    if hasattr(img, "format"):
        format_map = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
        if fmt := format_map.get(img.format.upper()):
            return fmt

    ext = filename.lower().split(".")[-1] if "." in filename else ""
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    return mime_map.get(ext, "application/octet-stream")


def _strip_exif(img: Image.Image) -> Image.Image:
    """Strip EXIF data from image."""
    data = list(img.getdata())
    img_without_exif = Image.new(img.mode, img.size)
    img_without_exif.putdata(data)
    return img_without_exif


def _resize_if_needed(img: Image.Image) -> Image.Image:
    """Resize if longest side exceeds max, maintaining aspect ratio."""
    width, height = img.size
    max_side = max(width, height)

    if max_side <= MAX_LONGEST_SIDE:
        return img

    scale = MAX_LONGEST_SIDE / max_side
    new_width = int(width * scale)
    new_height = int(height * scale)

    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
