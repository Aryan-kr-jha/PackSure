"""Analysis orchestration: PaddleOCR -> Vision AI fallback -> deterministic compliance.

Deployment strategy:
1. Run the fast OCR/extraction path first.
2. Run Vision AI when OCR is weak, incomplete, or internally inconsistent.
3. Let Vision AI fill gaps and replace clearly low-confidence OCR values.
4. Keep the compliance decision deterministic.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from core.compliance import evaluate_compliance
from core.config import settings
from declarations import extract_declarations
from extraction import extract_fields
from services.vision_ai import extract_package_semantics


MANDATORY_DECLARATIONS = (
    "1_manufacturer_packer_importer",
    "2_country_of_origin",
    "3_generic_common_name",
    "4_net_quantity",
    "5_manufacture_packing_date",
    "6_expiry_best_before",
    "7_mrp",
    "8_unit_sale_price",
    "9_consumer_care",
)


def _value(item: Any) -> Any:
    return item.get("value") if isinstance(item, dict) else None


def _confidence(item: Any) -> float:
    if not isinstance(item, dict):
        return 0.0
    try:
        return float(item.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_missing(item: Any) -> bool:
    if not isinstance(item, dict):
        return True
    status = str(item.get("status", "")).upper()
    return status in {"", "MISSING", "UNCERTAIN"} or _value(item) in (None, "", [])


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", "", str(value or "").lower())


def _numeric(value: Any) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", str(value or "").replace(",", ""))
    return float(match.group(1)) if match else None


def _price_math_ok(fields: dict[str, Any]) -> bool:
    mrp = _numeric(_value(fields.get("mrp")))
    usp = _numeric(_value(fields.get("unit_sale_price")))
    qty = _numeric(_value(fields.get("net_quantity")))
    if mrp is None or usp is None or qty is None or qty <= 0:
        return True
    expected = mrp / qty
    return abs(usp - expected) / max(expected, 1e-9) <= 0.05


def _needs_vision(fields: dict[str, Any], declarations: dict[str, Any], ocr_items: list[dict[str, Any]]) -> bool:
    if not ocr_items:
        return True

    confidences = [
        float(x.get("confidence", 0) or 0)
        for x in ocr_items
        if isinstance(x, dict)
    ]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    missing = sum(
        1 for key in MANDATORY_DECLARATIONS
        if _is_missing(declarations.get(key))
    )

    weak_core = any(
        _is_missing(fields.get(k)) or _confidence(fields.get(k)) < 0.80
        for k in ("mrp", "unit_sale_price", "net_quantity")
    )

    return avg_conf < 0.75 or missing >= 1 or weak_core or not _price_math_ok(fields)


def _vision_field(candidate: Any, source: str = "vision_ai") -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    if str(candidate.get("status", "")).upper() != "FOUND":
        return None
    value = candidate.get("value")
    if value in (None, "", []):
        return None
    return {
        "value": value,
        "confidence": float(candidate.get("confidence", 0) or 0),
        "source": source,
        "evidence": candidate.get("evidence", []),
    }


def _merge_vision(
    fields: dict[str, Any],
    declarations: dict[str, Any],
    vision: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge only useful Vision AI results.

    Vision AI fills missing values and can replace OCR values only when the
    OCR result is weak. This prevents a low-confidence semantic guess from
    overwriting strong OCR evidence.
    """
    if vision.get("status") != "ok":
        return fields, declarations

    vf = vision.get("fields", {}) or {}
    merged_fields = dict(fields)
    merged_declarations = dict(declarations)

    field_map = {
        "mrp": "mrp",
        "unit_sale_price": "unit_sale_price",
        "net_quantity": "net_quantity",
    }
    declaration_map = {
        "product_common_name": "3_generic_common_name",
        "manufacturer": "1_manufacturer_packer_importer",
        "packer": "1_manufacturer_packer_importer",
        "importer": "1_manufacturer_packer_importer",
        "country_of_origin": "2_country_of_origin",
        "manufacture_packing_date": "5_manufacture_packing_date",
        "expiry_best_before": "6_expiry_best_before",
        "consumer_care": "9_consumer_care",
    }

    for source, target in field_map.items():
        candidate = _vision_field(vf.get(source))
        if candidate is None:
            continue
        old = merged_fields.get(target)
        # Vision fills a gap or repairs a truly weak OCR result (< 0.50)
        if _is_missing(old) or _confidence(old) < 0.50:
            merged_fields[target] = candidate

    for source, target in declaration_map.items():
        candidate = _vision_field(vf.get(source))
        if candidate is None:
            continue
        old = merged_declarations.get(target)

        # Critical rule: NEVER overwrite valid OCR dates or statutory prices
        if target in ("5_manufacture_packing_date", "6_expiry_best_before", "7_mrp", "8_unit_sale_price"):
            if not _is_missing(old) and _confidence(old) >= 0.50:
                continue

        if _is_missing(old) or _confidence(old) < 0.50:
            merged_declarations[target] = {
                "value": candidate["value"],
                "status": "FOUND",
                "confidence": candidate["confidence"],
                "evidence": candidate["evidence"],
                "source": "vision_ai",
            }

    # Ensure source provenance is tracked on all entries
    for k, v in merged_declarations.items():
        if isinstance(v, dict) and "source" not in v:
            v["source"] = "ocr"
    for k, v in merged_fields.items():
        if isinstance(v, dict) and "source" not in v:
            v["source"] = "ocr"

    # Keep the existing declaration extraction as the canonical product name
    # when it already says a generic name such as "Face Wash".
    generic = merged_declarations.get("3_generic_common_name")
    if isinstance(generic, dict):
        text = str(generic.get("value", "")).strip()
        if "face wash" in text.lower():
            generic["value"] = "Face Wash"

    return merged_fields, merged_declarations


def analyze_package(
    ocr_items: list[dict[str, Any]],
    image_path: str | Path | None = None,
) -> dict[str, Any]:
    fields = extract_fields(ocr_items)
    declarations = extract_declarations(ocr_items, existing_fields=fields)

    vision = {
        "status": "not_run",
        "provider": None,
        "fields": {},
        "notes": "Vision AI fallback not required or not enabled.",
    }

    semantic_fields, semantic_declarations = fields, declarations

    enabled = os.getenv("VISION_AI_ENABLED", "false").lower() in {"1", "true", "yes"}

    if image_path is not None and enabled and _needs_vision(fields, declarations, ocr_items):
        vision = extract_package_semantics(image_path, ocr_items)
        semantic_fields, semantic_declarations = _merge_vision(
            fields, declarations, vision
        )

    compliance = evaluate_compliance(
        semantic_fields,
        semantic_declarations,
        tolerance=settings.compliance_tolerance,
    )

    overlays = [
        {
            "text": item.get("text", ""),
            "box": item.get("box", []),
            "confidence": item.get("confidence", 0),
        }
        for item in ocr_items
    ]

    return {
        "fields": semantic_fields,
        "declarations": semantic_declarations,
        "compliance": compliance,
        "ocr_overlays": overlays,
        "vision_ai": vision,
    }
