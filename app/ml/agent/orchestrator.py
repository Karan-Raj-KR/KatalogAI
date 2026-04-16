"""
Agentic extraction orchestrator.

ExtractionAgent uses the Gemini function-calling API to decide which tools
to call and in what order for product data extraction. After the first pass,
if overall confidence is below threshold, it runs a second self-correcting
pass with a diagnosis of what failed and suggested alternative strategies.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import google.genai as genai
from google.genai import types

from app.config import settings
from app.core.logging import get_logger
from app.ml.agent.prompts import build_retry_context, build_system_prompt
from app.ml.agent.tools import get_tool_declarations
from app.ml.confidence import aggregate_confidence
from app.ml.hsn.retriever import HSNMatch, retrieve_hsn
from app.ml.hsn.verifier import verify_hsn
from app.ml.ocr import extract_text_from_image
from app.ml.text_parser import extract_all, extract_hints
from app.ml.vlm import extract_with_gemini, extract_with_gemini_multimodal, merge_extractions

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_MODEL = "gemini-2.5-flash"
_MAX_TURNS = 8
_CONFIDENCE_THRESHOLD = 0.75

logger = get_logger(__name__)


class ExtractionAgent:
    """
    Gemini-orchestrated extraction agent with self-correction.

    Pass 1: agent calls tools in agent-chosen order.
    Pass 2 (if confidence < 0.75): agent retries with diagnosis of what
    failed and explicit suggestions for alternative strategies.

    The returned dict has the same shape as the old hardcoded pipeline:
        {field_name: (value_or_None, confidence_float)}
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        # Per-run state; reset in run()
        self._text: str | None = None
        self._image_bytes: bytes | None = None
        self._request_id: str = ""
        self._ocr_text: str = ""
        self._ocr_confidence: float | None = None
        self._hsn_candidates: list[HSNMatch] = []
        self._accumulated: dict[str, tuple[str | None, float]] = {}
        self._client: genai.Client | None = None

    @property
    def ocr_result(self) -> tuple[str, float]:
        """Returns (ocr_text, ocr_confidence) from the last run."""
        return (self._ocr_text, self._ocr_confidence or 0.0)

    async def run(
        self,
        *,
        input_type: str,
        text: str | None = None,
        image_bytes: bytes | None = None,
        request_id: str,
    ) -> dict[str, tuple[str | None, float]]:
        """
        Run agentic extraction. Returns field dict with (value, confidence) tuples.
        Returns empty dict if GEMINI_API_KEY is not configured.
        """
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set — agent cannot run", request_id=request_id)
            return {}

        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._text = text
        self._image_bytes = image_bytes
        self._request_id = request_id
        self._ocr_text = ""
        self._ocr_confidence = None
        self._hsn_candidates = []
        self._accumulated = {}

        logger.info(
            "Extraction agent starting",
            request_id=request_id,
            input_type=input_type,
            pass_num=1,
        )

        pass1_result = await self._agent_loop(input_type=input_type, pass_num=1)
        overall = aggregate_confidence(pass1_result)

        logger.info(
            "Agent pass 1 complete",
            request_id=request_id,
            overall_confidence=overall,
            fields_extracted=sum(1 for v, _ in pass1_result.values() if v is not None),
        )

        if overall >= _CONFIDENCE_THRESHOLD:
            return pass1_result

        logger.info(
            "Confidence below threshold — starting self-correction pass",
            request_id=request_id,
            confidence=overall,
            threshold=_CONFIDENCE_THRESHOLD,
        )

        # Reset for pass 2; OCR text is preserved so run_ocr returns cached result
        self._accumulated = {}
        self._hsn_candidates = []

        pass2_result = await self._agent_loop(
            input_type=input_type,
            pass_num=2,
            prior_result=pass1_result,
            prior_confidence=overall,
        )

        overall2 = aggregate_confidence(pass2_result)
        logger.info(
            "Agent pass 2 (self-correction) complete",
            request_id=request_id,
            overall_confidence=overall2,
        )

        # Merge: pass2 wins for any field it extracted at higher confidence
        merged: dict[str, tuple[str | None, float]] = dict(pass1_result)
        for field, (value, conf) in pass2_result.items():
            if value is not None:
                existing_conf = merged.get(field, (None, 0.0))[1]
                if conf > existing_conf:
                    merged[field] = (value, conf)

        return merged

    # ──────────────────────────────────────────────────────────── agent loop

    async def _agent_loop(
        self,
        input_type: str,
        pass_num: int,
        prior_result: dict | None = None,
        prior_confidence: float | None = None,
    ) -> dict[str, tuple[str | None, float]]:
        """Run a single agent pass with multi-turn Gemini function calling."""
        system_prompt = build_system_prompt(input_type, pass_num)

        if pass_num == 2 and prior_result is not None and prior_confidence is not None:
            retry_ctx = build_retry_context(
                prior_confidence=prior_confidence,
                prior_result=prior_result,
                ocr_confidence=self._ocr_confidence,
                input_type=input_type,
            )
            system_prompt = system_prompt + "\n\n" + retry_ctx

        contents: list[types.Content] = [
            types.Content(role="user", parts=self._build_initial_parts(input_type, pass_num))
        ]
        tool_declarations = get_tool_declarations(input_type)

        for turn in range(_MAX_TURNS):
            try:
                response = await self._client.aio.models.generate_content(
                    model=_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=[types.Tool(function_declarations=tool_declarations)],
                        temperature=0.1,
                        max_output_tokens=4096,
                    ),
                )
            except Exception as exc:
                logger.error(
                    "Agent Gemini call failed",
                    request_id=self._request_id,
                    turn=turn,
                    pass_num=pass_num,
                    error=str(exc),
                )
                break

            if not response.candidates or not response.candidates[0].content:
                logger.warning(
                    "Empty agent response",
                    request_id=self._request_id,
                    turn=turn,
                )
                break

            model_content = response.candidates[0].content
            contents.append(model_content)

            fc_parts = [
                p for p in model_content.parts if hasattr(p, "function_call") and p.function_call
            ]

            if not fc_parts:
                logger.info(
                    "Agent finished — no more tool calls",
                    request_id=self._request_id,
                    turn=turn,
                    pass_num=pass_num,
                )
                break

            logger.info(
                "Agent invoking tools",
                request_id=self._request_id,
                turn=turn,
                tools=[p.function_call.name for p in fc_parts],
            )

            fr_parts: list[types.Part] = []
            for part in fc_parts:
                fc = part.function_call
                result = await self._dispatch_tool(fc.name, dict(fc.args))
                fr_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response=result,
                        )
                    )
                )

            contents.append(types.Content(role="user", parts=fr_parts))

        return dict(self._accumulated)

    def _build_initial_parts(self, input_type: str, pass_num: int) -> list[types.Part]:
        parts: list[types.Part] = []

        if input_type == "image" and self._image_bytes:
            parts.append(
                types.Part(inline_data=types.Blob(data=self._image_bytes, mime_type="image/jpeg"))
            )
            msg = "Extract all product data from this product image."
        elif self._text:
            msg = f"Extract all product data from this text:\n\n{self._text}"
        else:
            msg = "No input provided."

        if pass_num == 2:
            msg += (
                "\n\nThis is a self-correction pass. The previous extraction had low confidence. "
                "See the RETRY CONTEXT in your system instructions for details on what to improve."
            )

        parts.append(types.Part(text=msg))
        return parts

    # ──────────────────────────────────────────────────────── tool dispatch

    async def _dispatch_tool(self, name: str, args: dict) -> dict:
        log_args = {k: v for k, v in args.items() if k != "candidates_json"}
        logger.info(
            "Tool dispatch",
            request_id=self._request_id,
            tool=name,
            args=log_args,
        )
        try:
            if name == "run_ocr":
                return await self._tool_run_ocr()
            elif name == "extract_text_fields":
                return await self._tool_extract_text_fields(args)
            elif name == "extract_image_fields":
                return await self._tool_extract_image_fields(args)
            elif name == "retrieve_hsn_candidates":
                return await self._tool_retrieve_hsn(args)
            elif name == "verify_hsn_code":
                return await self._tool_verify_hsn(args)
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            logger.error(
                "Tool execution failed",
                request_id=self._request_id,
                tool=name,
                error=str(exc),
            )
            return {"error": str(exc)}

    # ─────────────────────────────────────────────────── tool implementations

    async def _tool_run_ocr(self) -> dict:
        if not self._image_bytes:
            return {"text": "", "confidence": 0.0, "error": "No image in agent context"}

        # Return cached result — avoids re-running OCR on pass 2
        if self._ocr_confidence is not None:
            return {
                "text": self._ocr_text,
                "confidence": self._ocr_confidence,
                "text_length": len(self._ocr_text),
                "cached": True,
            }

        result = await extract_text_from_image(self._image_bytes)
        self._ocr_text = result.text
        self._ocr_confidence = result.confidence

        logger.info(
            "OCR tool completed",
            request_id=self._request_id,
            text_length=len(result.text),
            confidence=result.confidence,
        )

        return {
            "text": result.text,
            "confidence": result.confidence,
            "text_length": len(result.text),
        }

    async def _tool_extract_text_fields(self, args: dict) -> dict:
        text = self._text or self._ocr_text
        if not text:
            return {"fields": {}, "overall_confidence": 0.0, "error": "No text available"}

        strategy = args.get("strategy", "full")
        hints = extract_hints(text)
        regex_result = extract_all(text)
        regex_for_merge: dict[str, tuple[str | None, float]] = {
            f: (r["value"], r["confidence"]) for f, r in regex_result.items()
        }

        if strategy == "full":
            gemini_result = await extract_with_gemini(text, hints, self._request_id)
            merged = merge_extractions(regex_for_merge, gemini_result)
        else:
            merged = {f: (v, c) for f, (v, c) in regex_for_merge.items() if v is not None}

        self._accumulate(merged)

        fields_out = {
            f: {"value": v, "confidence": round(c, 3)}
            for f, (v, c) in merged.items()
            if v is not None
        }
        return {
            "fields": fields_out,
            "overall_confidence": round(aggregate_confidence(merged), 3),
            "fields_extracted": len(fields_out),
            "strategy_used": strategy,
        }

    async def _tool_extract_image_fields(self, args: dict) -> dict:
        if not self._image_bytes:
            return {"fields": {}, "overall_confidence": 0.0, "error": "No image in agent context"}

        strategy = args.get("strategy", "ocr_grounded")
        ocr_text_to_use = "" if strategy == "vision_only" else self._ocr_text

        result = await extract_with_gemini_multimodal(
            image_bytes=self._image_bytes,
            ocr_text=ocr_text_to_use,
            hints={},
            request_id=self._request_id,
        )

        self._accumulate(result)

        fields_out = {
            f: {"value": v, "confidence": round(c, 3)}
            for f, (v, c) in result.items()
            if v is not None
        }
        return {
            "fields": fields_out,
            "overall_confidence": round(aggregate_confidence(result), 3),
            "fields_extracted": len(fields_out),
            "strategy_used": strategy,
        }

    async def _tool_retrieve_hsn(self, args: dict) -> dict:
        product_name = args.get("product_name", "").strip()
        category = args.get("category", "")

        if not product_name:
            return {"candidates": [], "count": 0, "error": "product_name is required"}

        search_text = f"{product_name} {category}".strip() if category else product_name
        matches = await retrieve_hsn(search_text, self._db, top_k=5)
        self._hsn_candidates = matches

        logger.info(
            "HSN retrieve tool completed",
            request_id=self._request_id,
            query=search_text[:80],
            candidates_found=len(matches),
        )

        return {
            "candidates": [
                {"code": m.code, "description": m.description, "score": round(m.score, 4)}
                for m in matches
            ],
            "count": len(matches),
        }

    async def _tool_verify_hsn(self, args: dict) -> dict:
        product_name = args.get("product_name", "").strip()
        category = args.get("category")
        candidates_json_str = args.get("candidates_json", "[]")

        # Prefer candidates stored from the last retrieve call in this pass
        matches = self._hsn_candidates

        if not matches and candidates_json_str:
            try:
                raw = json.loads(candidates_json_str)
                matches = [
                    HSNMatch(
                        code=c["code"],
                        description=c["description"],
                        gst_rate=None,
                        score=float(c.get("score", 0.0)),
                    )
                    for c in raw
                    if "code" in c and "description" in c
                ]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                return {
                    "selected_code": None,
                    "confidence": 0.0,
                    "error": f"Invalid candidates_json: {exc}",
                }

        if not matches:
            return {"selected_code": None, "confidence": 0.0, "reason": "No candidates available"}

        code, confidence = await verify_hsn(
            product_name=product_name,
            category=category,
            matches=matches,
            request_id=self._request_id,
        )

        if code:
            self._accumulated["hsn_code"] = (code, confidence)

        logger.info(
            "HSN verify tool completed",
            request_id=self._request_id,
            selected_code=code,
            confidence=confidence,
        )

        return {
            "selected_code": code,
            "confidence": round(confidence, 3) if code else 0.0,
        }

    # ──────────────────────────────────────────────────────── accumulation

    def _accumulate(self, fields: dict[str, tuple[str | None, float]]) -> None:
        """Merge new field results into accumulated state, keeping higher confidence."""
        for field, (value, conf) in fields.items():
            if value is not None and not field.startswith("_"):
                existing_conf = self._accumulated.get(field, (None, -1.0))[1]
                if conf > existing_conf:
                    self._accumulated[field] = (value, conf)
