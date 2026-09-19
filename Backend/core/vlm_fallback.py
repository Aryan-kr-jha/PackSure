from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

MANDATORY_KEYS = [
    "1_manufacturer_packer_importer", "2_country_of_origin", "3_generic_common_name",
    "4_net_quantity", "5_manufacture_packing_date", "6_expiry_best_before",
    "7_mrp", "8_unit_sale_price", "9_consumer_care",
]


def _value(obj: Any):
    if isinstance(obj, dict):
        return obj.get("value")
    return obj


def _status(obj: Any) -> str:
    return str((obj or {}).get("status", "")).upper() if isinstance(obj, dict) else ""


def should_fallback(
    ocr_items: list[dict[str, Any]],
    declarations: dict[str, Any],
    fields: dict[str, Any] | None = None,
    threshold: float = 0.70,
) -> bool:
    """Trigger VLM for missing/weak fields OR an internally inconsistent price block."""
    fields = fields or {}
    confidences = [float(x.get("confidence", 0) or 0) for x in ocr_items]
    average = sum(confidences) / len(confidences) if confidences else 0.0

    missing = sum(
        1 for key in MANDATORY_KEYS
        if _status(declarations.get(key)) not in {"FOUND", "PARTIAL"}
    )
    if average < threshold or missing >= 1:
        return True

    mrp = _value(fields.get("mrp"))
    usp_obj = fields.get("unit_sale_price")
    qty_obj = fields.get("net_quantity")
    usp = _value(usp_obj)
    qty = _value(qty_obj)
    if isinstance(mrp, (int, float)) and isinstance(usp, (int, float)) and isinstance(qty, (int, float)):
        unit = str((usp_obj or {}).get("unit", "")).lower() if isinstance(usp_obj, dict) else ""
        qunit = str((qty_obj or {}).get("unit", "")).lower() if isinstance(qty_obj, dict) else ""
        factor = 1000 if (qunit, unit) in {("kg", "g"), ("l", "ml")} else 1
        expected = mrp / (qty * factor) if qty else 0
        if expected and abs(usp - expected) / expected > 0.05:
            return True

    return False


def extract_with_vlm(image_path: str | Path) -> dict[str, Any] | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        from openai import OpenAI

        data_url = "data:image/jpeg;base64," + base64.b64encode(
            Path(image_path).read_bytes()
        ).decode("ascii")

        schema = {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "properties": {
                        "mrp": {"type": ["number", "null"]},
                        "unit_sale_price": {"type": ["object", "null"]},
                        "net_quantity": {"type": ["object", "null"]},
                    },
                    "required": ["mrp", "unit_sale_price", "net_quantity"],
                    "additionalProperties": True,
                },
                "declarations": {"type": "object", "additionalProperties": True},
                "confidence": {"type": "number"},
                "notes": {"type": "string"},
            },
            "required": ["fields", "declarations", "confidence", "notes"],
            "additionalProperties": False,
        }

        prompt = (
            "Read the physical package label exactly. Do not infer or invent. "
            "Pay special attention to MRP, USP/unit sale price, net quantity, "
            "Mfg/Pkd date, expiry/best-before, batch, manufacturer, country of origin, "
            "consumer phone/email, and product/common name. If OCR-looking digits conflict, "
            "trust the visibly printed label. Return null when unreadable or absent. "
            "For USP preserve the unit, e.g. 2.59/ml; for quantity preserve the unit, e.g. 100 ml."
        )

        response = OpenAI().chat.completions.create(
            model=os.getenv("VLM_MODEL", "gpt-4.1-mini"),
            messages=[
                {"role": "system", "content": "You are a package-label verification model. Extract only visible printed text."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ]},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "label_verification", "strict": True, "schema": schema}},
            max_tokens=2500,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as exc:
        return {"error": str(exc), "fields": {}, "declarations": {}, "confidence": 0.0, "notes": "VLM verification failed; OCR result retained."}
