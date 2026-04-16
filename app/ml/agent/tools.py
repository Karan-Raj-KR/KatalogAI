"""Gemini FunctionDeclaration schemas for the extraction agent tools."""

from google.genai import types

RUN_OCR = types.FunctionDeclaration(
    name="run_ocr",
    description=(
        "Extract text from the product image using OCR. "
        "Call this first for image inputs to get raw text before running AI extraction. "
        "Returns the extracted text and a confidence score."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={},
        required=[],
    ),
)

EXTRACT_TEXT_FIELDS = types.FunctionDeclaration(
    name="extract_text_fields",
    description=(
        "Extract structured product fields (name, brand, MRP, weight, category, etc.) from text "
        "using regex patterns and Gemini AI. "
        "strategy='full' runs both regex and AI for best accuracy. "
        "strategy='hints_only' runs regex only — use this on retry if AI extraction was unreliable."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "strategy": types.Schema(
                type=types.Type.STRING,
                description="'full' for regex + AI extraction, 'hints_only' for regex only",
                enum=["full", "hints_only"],
            ),
        },
        required=["strategy"],
    ),
)

EXTRACT_IMAGE_FIELDS = types.FunctionDeclaration(
    name="extract_image_fields",
    description=(
        "Extract structured product fields from the product image using multimodal Gemini vision. "
        "strategy='ocr_grounded' combines OCR text with visual analysis — best when OCR quality is good. "
        "strategy='vision_only' ignores OCR and uses pure visual analysis — use this when OCR quality was poor."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "strategy": types.Schema(
                type=types.Type.STRING,
                description="'ocr_grounded' uses OCR text as context; 'vision_only' uses vision only",
                enum=["ocr_grounded", "vision_only"],
            ),
        },
        required=["strategy"],
    ),
)

RETRIEVE_HSN_CANDIDATES = types.FunctionDeclaration(
    name="retrieve_hsn_candidates",
    description=(
        "Search the HSN (Harmonized System of Nomenclature) tax code database for a product. "
        "Returns up to 5 candidates ranked by similarity score. "
        "Call this after extracting the product name. Providing category improves accuracy."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "product_name": types.Schema(
                type=types.Type.STRING,
                description="Product name or description to search for",
            ),
            "category": types.Schema(
                type=types.Type.STRING,
                description="Product category (optional) — improves search accuracy",
            ),
        },
        required=["product_name"],
    ),
)

VERIFY_HSN_CODE = types.FunctionDeclaration(
    name="verify_hsn_code",
    description=(
        "Select the best HSN code from retrieved candidates using AI reasoning. "
        "Call this after retrieve_hsn_candidates. "
        "Pass candidates_json as the JSON string from the previous retrieve_hsn_candidates result."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "product_name": types.Schema(
                type=types.Type.STRING,
                description="Product name for context",
            ),
            "category": types.Schema(
                type=types.Type.STRING,
                description="Product category for context (optional)",
            ),
            "candidates_json": types.Schema(
                type=types.Type.STRING,
                description="JSON string of candidates from retrieve_hsn_candidates",
            ),
        },
        required=["product_name", "candidates_json"],
    ),
)

# Tools available per input type — image gets all tools; text skips OCR and image tools
TEXT_TOOLS = [EXTRACT_TEXT_FIELDS, RETRIEVE_HSN_CANDIDATES, VERIFY_HSN_CODE]
IMAGE_TOOLS = [RUN_OCR, EXTRACT_TEXT_FIELDS, EXTRACT_IMAGE_FIELDS, RETRIEVE_HSN_CANDIDATES, VERIFY_HSN_CODE]


def get_tool_declarations(input_type: str) -> list[types.FunctionDeclaration]:
    return TEXT_TOOLS if input_type == "text" else IMAGE_TOOLS
