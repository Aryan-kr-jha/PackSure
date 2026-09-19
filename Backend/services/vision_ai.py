"""Provider-neutral multimodal semantic extraction after PaddleOCR.

This module never computes legal compliance. It only associates visible label
values with declaration fields and marks absent/uncertain values explicitly.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Protocol

FIELDS = (
    "product_common_name", "manufacturer", "packer", "importer", "country_of_origin",
    "net_quantity", "mrp", "unit_sale_price", "manufacture_packing_date",
    "expiry_best_before", "consumer_care",
)

FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {},
        "status": {"type": "string", "enum": ["FOUND", "MISSING", "UNCERTAIN"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["value", "status", "confidence", "evidence", "reason"],
    "additionalProperties": False,
}

VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {"type": "object", "properties": {key: FIELD_SCHEMA for key in FIELDS}, "required": list(FIELDS), "additionalProperties": False},
        "provider": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["fields", "provider", "notes"],
    "additionalProperties": False,
}


def _strip_additional_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *schema* with all 'additionalProperties' keys removed.

    The Gemini REST API does not recognise the ``additional_properties`` proto
    field that the Python SDK generates from ``additionalProperties``, so we
    must strip it before sending.
    """
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_additional_properties(value)
        elif isinstance(value, list):
            cleaned[key] = [_strip_additional_properties(v) if isinstance(v, dict) else v for v in value]
        else:
            cleaned[key] = value
    return cleaned


class VisionProvider(Protocol):
    def extract(self, image_path: str | Path, ocr_items: list[dict[str, Any]]) -> dict[str, Any]: ...


def _normalise(result: dict[str, Any], provider: str) -> dict[str, Any]:
    fields = result.get("fields") if isinstance(result, dict) else {}
    safe: dict[str, Any] = {}
    for key in FIELDS:
        item = fields.get(key, {}) if isinstance(fields, dict) else {}
        status = str(item.get("status", "MISSING")).upper()
        if status not in {"FOUND", "MISSING", "UNCERTAIN"}:
            status = "UNCERTAIN"
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        safe[key] = {"value": item.get("value"), "status": status, "confidence": confidence, "evidence": item.get("evidence", []) if isinstance(item.get("evidence", []), list) else [], "reason": str(item.get("reason", ""))}
    return {"provider": provider, "fields": safe, "notes": str(result.get("notes", "")), "status": "ok"}


class OpenAIVisionProvider:
    def __init__(self, *, model: str | None = None, timeout: float = 25.0, client: Any = None) -> None:
        self.model = model or os.getenv("VISION_AI_MODEL", "gemini-3-flash-preview")
        self.timeout = timeout
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY")) or self._client is not None

    def extract(self, image_path: str | Path, ocr_items: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "provider": self.model, "fields": {}, "notes": "OPENAI_API_KEY is not configured."}
        try:
            from openai import OpenAI
            client = self._client or OpenAI(timeout=self.timeout, max_retries=1)
            image_url = "data:image/jpeg;base64," + base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            ocr_context = json.dumps([{"text": x.get("text", ""), "confidence": x.get("confidence", 0), "box": x.get("box", [])} for x in ocr_items], ensure_ascii=False)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a cautious package-label semantic extractor. PaddleOCR has already detected text and boxes. Use the image only to associate visible values with fields. Never invent, repair, or infer text. If a field is not visible, return MISSING. If evidence conflicts or is unreadable, return UNCERTAIN. Do not make a compliance decision."},
                    {"role": "user", "content": [{"type": "text", "text": "Return every requested field. OCR context follows:\n" + ocr_context}, {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}]},
                ],
                response_format={"type": "json_schema", "json_schema": {"name": "package_label_semantic_extraction", "strict": True, "schema": VISION_SCHEMA}},
                max_tokens=4000,
            )
            return _normalise(json.loads(response.choices[0].message.content), self.model)
        except Exception as exc:
            return {"status": "error", "provider": self.model, "fields": {}, "notes": f"Vision AI unavailable: {type(exc).__name__}: {exc}"}


class GeminiVisionProvider:
    """Native Google Gemini provider; PaddleOCR remains the OCR authority."""

    def __init__(self, *, model: str | None = None, timeout: float = 90.0, client: Any = None) -> None:
        self.model = model or os.getenv("VISION_AI_MODEL", "gemini-3.6-flash")
        self.timeout = timeout
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY")) or self._client is not None

    def extract(self, image_path: str | Path, ocr_items: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "provider": self.model, "fields": {}, "notes": "GEMINI_API_KEY is not configured."}
        last_exc: Exception | None = None
        for attempt in range(2):  # retry once on timeout
            try:
                from google import genai
                from google.genai import types
                client = self._client or genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options=types.HttpOptions(timeout=int(self.timeout * 1000)))
                ocr_context = json.dumps([{"text": x.get("text", ""), "confidence": x.get("confidence", 0), "box": x.get("box", [])} for x in ocr_items], ensure_ascii=False)
                prompt = """Extract package-label declarations using the image and OCR context. Use only text visibly supported by the image or OCR. Never invent or infer. Return MISSING when absent and UNCERTAIN when unreadable or conflicting. Do not make a legal compliance decision.\nOCR CONTEXT:\n""" + ocr_context
                response = client.models.generate_content(
                    model=self.model,
                    contents=[prompt, types.Part.from_bytes(data=Path(image_path).read_bytes(), mime_type="image/jpeg")],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=_strip_additional_properties(VISION_SCHEMA),
                        temperature=0,
                    ),
                )
                return _normalise(json.loads(response.text), self.model)
            except Exception as exc:
                last_exc = exc
                # Only retry on timeout-related errors
                if attempt == 0 and "timeout" in str(exc).lower():
                    continue
                break
        return {"status": "error", "provider": self.model, "fields": {}, "notes": f"Gemini Vision unavailable: {type(last_exc).__name__}: {last_exc}"}


def get_vision_provider() -> VisionProvider:
    provider = os.getenv("VISION_AI_PROVIDER", "gemini").lower()
    return GeminiVisionProvider() if provider == "gemini" else OpenAIVisionProvider()


def extract_package_semantics(image_path: str | Path, ocr_items: list[dict[str, Any]], provider: VisionProvider | None = None) -> dict[str, Any]:
    """Small testable entry point; returns structured semantic extraction only."""
    return (provider or get_vision_provider()).extract(image_path, ocr_items)
