"""
Regex-based text extraction for product data.

This is the cheap pre-pass before Gemini — extracts high-confidence
fields that don't require LLM reasoning.
"""

import re
from typing import TypedDict


class ExtractionResult(TypedDict):
    value: str | None
    confidence: float


def extract_name(text: str) -> ExtractionResult:
    """Use full text as product name."""
    cleaned = text.strip()[:500]
    return ExtractionResult(value=cleaned, confidence=0.85)


def extract_brand(text: str) -> ExtractionResult:
    """Look for known Indian kirana brands."""
    brands = [
        "Tata",
        "Amul",
        "Nestle",
        "Nestlé",
        "Britannia",
        "HUL",
        "ITC",
        "Dabur",
        "Parle",
        "MDH",
        "Haldirams",
        "Patanjali",
        "Mohan",
        "Basmati",
        "Kohinoor",
        "Daawat",
        "India Gate",
        "Lijjat",
        "Mother Dairy",
        "Kwality",
        "Venky",
        "PRISTINE",
        "Biovet",
    ]
    for brand in brands:
        match = re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE)
        if match:
            return ExtractionResult(value=match.group(0).title(), confidence=0.90)
    return ExtractionResult(value=None, confidence=0.0)


def extract_mrp(text: str) -> ExtractionResult:
    """Extract MRP: ₹ or Rs. followed by digits."""
    patterns = [
        r"mrp[:\s]*₹?\s*(\d+(?:\.\d{1,2})?)",
        r"mrp[:\s]*₹?\s*(\d+(?:\.\d{1,2})?)",
        r"(?:₹|Rs\.?|Rs)\s*(\d+(?:\.\d{1,2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return ExtractionResult(value=match.group(1), confidence=0.95)
    return ExtractionResult(value=None, confidence=0.0)


def extract_weight(text: str) -> ExtractionResult:
    """Extract weight in grams."""
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(kg|kilo)",
        r"(\d+(?:\.\d+)?)\s*(g|gm|gram|grams?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            qty = float(match.group(1))
            unit = match.group(2).lower()
            grams = qty * 1000 if unit.startswith("k") else qty
            return ExtractionResult(value=str(grams), confidence=0.95)
    return ExtractionResult(value=None, confidence=0.0)


def extract_volume(text: str) -> ExtractionResult:
    """Extract volume in ml."""
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(litre|liter|l)",
        r"(\d+(?:\.\d+)?)\s*(ml|millilitre)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            qty = float(match.group(1))
            unit = match.group(2).lower()
            ml = qty * 1000 if unit.startswith("l") else qty
            return ExtractionResult(value=str(ml), confidence=0.95)
    return ExtractionResult(value=None, confidence=0.0)


def extract_unit(text: str) -> ExtractionResult:
    """Extract unit string (kg, g, ml, pcs)."""
    weight = extract_weight(text)
    if weight["value"]:
        unit = "kg" if float(weight["value"]) >= 1000 else "g"
        return ExtractionResult(value=unit, confidence=weight["confidence"])

    vol = extract_volume(text)
    if vol["value"]:
        unit = "l" if float(vol["value"]) >= 1000 else "ml"
        return ExtractionResult(value=unit, confidence=vol["confidence"])

    if re.search(r"\b(pcs|pieces|pack|bottle|box|sachet|jar)\b", text, re.IGNORECASE):
        match = re.search(r"\b(pcs|pieces|pack|bottle|box|sachet|jar)\b", text, re.IGNORECASE)
        return ExtractionResult(value=match.group(0).lower(), confidence=0.85)

    return ExtractionResult(value=None, confidence=0.0)


def extract_barcode(text: str) -> ExtractionResult:
    """Extract barcode: 8, 12, or 13 digit numeric string."""
    match = re.search(r"\b(\d{8}|\d{12}|\d{13})\b", text)
    if match:
        return ExtractionResult(value=match.group(1), confidence=0.95)
    return ExtractionResult(value=None, confidence=0.0)


def extract_category(text: str) -> ExtractionResult:
    """Infer category from keywords."""
    keywords = {
        "Grocery & Staples": [
            "salt",
            "sugar",
            "oil",
            "flour",
            "atta",
            "rice",
            "dal",
            "pulses",
            "wheat",
            "masala",
            "spices",
            "tea",
            "coffee",
        ],
        "Personal Care": [
            "soap",
            "shampoo",
            "detergent",
            "toothpaste",
            "cream",
            "lotion",
            "deodorant",
            "razor",
            "shaving",
        ],
        "Snacks & Beverages": [
            "biscuit",
            "chips",
            "namkeen",
            "snack",
            "chocolate",
            "candy",
            "juice",
            "soda",
            "namkeen",
        ],
        "Dairy & Eggs": ["milk", "curd", "yogurt", "paneer", "butter", "cheese", "egg", "eggs"],
        "Household": ["cleaner", "mosquito", "coil", "battery", "bulb", "match"],
        "Frozen & Ready to Eat": ["frozen", "ready to eat", "instant", "popcorn"],
    }
    for category, words in keywords.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE):
                return ExtractionResult(value=category, confidence=0.70)
    return ExtractionResult(value=None, confidence=0.0)


def extract_all(text: str) -> dict[str, ExtractionResult]:
    """Run all extractors and return dict of results."""
    return {
        "name": extract_name(text),
        "brand": extract_brand(text),
        "mrp": extract_mrp(text),
        "weight_grams": extract_weight(text),
        "volume_ml": extract_volume(text),
        "unit": extract_unit(text),
        "barcode": extract_barcode(text),
        "category": extract_category(text),
    }


def extract_hints(text: str) -> dict[str, str]:
    """Extract only values that should be passed as hints to Gemini."""
    results = extract_all(text)
    hints = {}
    if mrp := results.get("mrp", {}).get("value"):
        hints["mrp"] = mrp
    if weight := results.get("weight_grams", {}).get("value"):
        hints["weight_grams"] = weight
    if volume := results.get("volume_ml", {}).get("value"):
        hints["volume_ml"] = volume
    if unit := results.get("unit", {}).get("value"):
        hints["unit"] = unit
    return hints
