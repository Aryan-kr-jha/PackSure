"""Digital E-Commerce Legal Metrology compliance orchestration.

Compares declarations from the online listing with declarations recovered from
the physical packaging images. It deliberately does not treat a retailer's
current sale price as MRP.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ocr.ocr_engine import run_ocr
from services.analyzer import analyze_package
from services.web_scraper import scrape_product_url

logger = logging.getLogger(__name__)

REQUIRED_ECOM_DECLARATIONS = [
    "mrp",
    "net_quantity",
    "country_of_origin",
    "manufacturer",
    "consumer_care",
    "generic_name",
]

KEY_MAP = {
    "mrp": ("mrp", "7_mrp"),
    "net_quantity": ("net_quantity", "4_net_quantity"),
    "country_of_origin": ("country_of_origin", "2_country_of_origin"),
    "manufacturer": ("manufacturer", "1_manufacturer_packer_importer"),
    "consumer_care": ("consumer_care", "9_consumer_care"),
    "generic_name": ("generic_name", "generic_common_name", "3_generic_common_name"),
}


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _present(value: Any) -> bool:
    value = _unwrap(value)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def _normalise_text(value: Any) -> str:
    value = _unwrap(value)
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _first_present(mapping: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if _present(mapping.get(key)):
            return _unwrap(mapping[key])
    return None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"(?<!\d)(\d+(?:,\d{3})*(?:\.\d+)?)(?!\d)", str(value or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _quantity(value: Any) -> tuple[Optional[float], Optional[str]]:
    text = str(_unwrap(value) or "").lower().replace(",", "")
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|kgs|g|gm|gms|mg|l|ltr|litre|litres|ml|"
        r"unit|units|pc|pcs|piece|pieces|count|n)\b",
        text,
    )
    if not m:
        return None, None
    n = float(m.group(1))
    unit = m.group(2).lower()
    aliases = {
        "kgs": "kg", "gm": "g", "gms": "g",
        "ltr": "l", "litre": "l", "litres": "l",
        "units": "unit", "pc": "unit", "pcs": "unit",
        "piece": "unit", "pieces": "unit", "count": "unit", "n": "unit",
    }
    return n, aliases.get(unit, unit)


def _normalise_country(value: Any) -> str:
    text = _normalise_text(value)
    text = re.sub(r"^country\s+of\s+origin\s*[:\-]\s*", "", text)
    return text.strip(" .,:;-")


def _normalise_name(value: Any) -> str:
    text = _normalise_text(value)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def _same_country(a: Any, b: Any) -> bool:
    return _normalise_country(a) == _normalise_country(b)


def _same_mrp(a: Any, b: Any) -> bool:
    na, nb = _number(a), _number(b)
    return na is not None and nb is not None and abs(na - nb) <= max(1.0, nb * 0.005)


def _quantity_compatible(a: Any, b: Any) -> bool:
    na, ua = _quantity(a)
    nb, ub = _quantity(b)
    if na is None or nb is None or ua is None or ub is None:
        return False
    if ua == ub:
        return abs(na - nb) <= max(0.01, nb * 0.01)
    # Convert mass/volume only when the unit families are directly convertible.
    factors = {
        ("kg", "g"): 1000.0, ("g", "kg"): 0.001,
        ("l", "ml"): 1000.0, ("ml", "l"): 0.001,
    }
    factor = factors.get((ua, ub))
    return factor is not None and abs(na * factor - nb) <= max(0.01, nb * 0.01)


def _consumer_care_present(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_present(value.get(k)) for k in ("phone", "email", "address", "name_or_designation"))
    return _present(value)


def _image_declarations(image_analyses: list[dict[str, Any]]) -> Dict[str, Any]:
    """Merge image declarations without allowing a later weak image to erase a strong one."""
    combined: Dict[str, Any] = {}
    confidence: Dict[str, float] = {}

    for analysis in image_analyses:
        declarations = analysis.get("declarations", {}) or {}
        fields = analysis.get("fields", {}) or {}

        # Include both declaration keys and direct fields because MRP/quantity
        # are represented in both parts of the existing pipeline.
        candidates = dict(declarations)
        for key, value in fields.items():
            if key not in candidates or not _present(candidates.get(key)):
                candidates[key] = value

        for key, raw in candidates.items():
            if not _present(raw):
                continue
            conf = 0.0
            if isinstance(raw, dict):
                try:
                    conf = float(raw.get("confidence", 0) or 0)
                except (TypeError, ValueError):
                    conf = 0.0
                value = raw.get("value")
            else:
                value = raw
                conf = 0.5

            if key not in combined or conf >= confidence.get(key, -1):
                combined[key] = value
                confidence[key] = conf

    return combined


def _get_field(source: Dict[str, Any], field: str) -> Any:
    return _first_present(source, KEY_MAP[field])


def _compare_field(field: str, web_value: Any, image_value: Any) -> Optional[dict[str, Any]]:
    if not (_present(web_value) and _present(image_value)):
        return None

    if field == "mrp":
        if not _same_mrp(web_value, image_value):
            return {
                "field": field, "type": "MISMATCH",
                "web_listing_value": web_value,
                "packaging_label_value": image_value,
                "severity": "HIGH",
                "rule": "Online listing MRP should agree with the physical package MRP.",
            }
    elif field == "net_quantity":
        if not _quantity_compatible(web_value, image_value):
            return {
                "field": field, "type": "MISMATCH",
                "web_listing_value": web_value,
                "packaging_label_value": image_value,
                "severity": "HIGH",
                "rule": "Online listing net quantity should agree with the physical package.",
            }
    elif field == "country_of_origin":
        if not _same_country(web_value, image_value):
            return {
                "field": field, "type": "MISMATCH",
                "web_listing_value": web_value,
                "packaging_label_value": image_value,
                "severity": "HIGH",
                "rule": "Country of origin on the listing should agree with the package.",
            }
    elif field == "manufacturer":
        a, b = _normalise_name(web_value), _normalise_name(image_value)
        if a and b and not (a in b or b in a):
            return {
                "field": field, "type": "MISMATCH",
                "web_listing_value": web_value,
                "packaging_label_value": image_value,
                "severity": "MEDIUM",
                "rule": "Manufacturer/importer identity should be consistent with the package.",
            }
    elif field == "generic_name":
        a, b = _normalise_name(web_value), _normalise_name(image_value)
        # Do not penalise a longer retail title for containing the package name.
        if a and b and a not in b and b not in a:
            return {
                "field": field, "type": "MISMATCH",
                "web_listing_value": web_value,
                "packaging_label_value": image_value,
                "severity": "MEDIUM",
                "rule": "The listing generic/common name should describe the same commodity.",
            }
    return None


def analyze_digital_product_url(url: str) -> Dict[str, Any]:
    scraped = scrape_product_url(url)

    if not scraped.get("success"):
        return {
            "status": "error",
            "url": url,
            "error": scraped.get("error", "Unable to fetch product page"),
            "compliance_score": 0,
            "compliance_status": "UNABLE_TO_ANALYZE",
            "violations": ["Unable to fetch product page"],
            "discrepancies": [],
            "images_scanned": 0,
        }

    web = scraped.get("extracted_declarations", {}) or {}
    image_analyses: list[dict[str, Any]] = []
    errors: list[str] = []

    for image_path in scraped.get("image_paths", []) or []:
        path = Path(image_path)
        if not path.exists():
            continue
        try:
            ocr_items = run_ocr(path)
            image_analyses.append(analyze_package(ocr_items, image_path=path))
        except Exception as exc:
            logger.exception("Digital image analysis failed for %s", path)
            errors.append(f"{path.name}: image analysis failed")

    image = _image_declarations(image_analyses)

    field_audit: Dict[str, Any] = {}
    missing: list[str] = []
    found_count = 0

    for field in REQUIRED_ECOM_DECLARATIONS:
        web_value = _first_present(web, KEY_MAP[field])
        image_value = _get_field(image, field)

        if _present(web_value) or _present(image_value):
            found_count += 1
            status = "FOUND"
        else:
            missing.append(field)
            status = "MISSING"

        field_audit[field] = {
            "status": status,
            "web_value": web_value,
            "image_value": image_value,
            "evidence_source": (
                "web+image" if _present(web_value) and _present(image_value)
                else "web" if _present(web_value) else "image" if _present(image_value)
                else None
            ),
        }

    discrepancies: list[dict[str, Any]] = []
    for field in ("mrp", "net_quantity", "country_of_origin", "manufacturer", "generic_name"):
        mismatch = _compare_field(
            field,
            field_audit[field]["web_value"],
            field_audit[field]["image_value"],
        )
        if mismatch:
            discrepancies.append(mismatch)

    # Consumer care is a presence requirement, not an exact-string requirement.
    # Retailer formatting commonly differs from the package.
    web_care = field_audit["consumer_care"]["web_value"]
    img_care = field_audit["consumer_care"]["image_value"]
    if _present(web_care) and _present(img_care):
        if isinstance(web_care, dict) and isinstance(img_care, dict):
            web_email = _normalise_text(web_care.get("email"))
            img_email = _normalise_text(img_care.get("email"))
            if web_email and img_email and web_email != img_email:
                discrepancies.append({
                    "field": "consumer_care",
                    "type": "MISMATCH",
                    "web_listing_value": web_care,
                    "packaging_label_value": img_care,
                    "severity": "MEDIUM",
                    "rule": "Consumer-care information should be consistent where both sources provide it.",
                })

    # Critical safety check: if both MRP and an explicit package value exist,
    # detect online price above the package MRP. Never compare sale price from
    # JSON-LD as MRP.
    web_mrp = _number(field_audit["mrp"]["web_value"])
    image_mrp = _number(field_audit["mrp"]["image_value"])
    sale_price = _number(web.get("sale_price"))
    if web_mrp is not None and image_mrp is not None and web_mrp > image_mrp + max(1.0, image_mrp * 0.005):
        discrepancies.append({
            "field": "mrp",
            "type": "OVERCHARGING_RISK",
            "web_listing_value": web_mrp,
            "packaging_label_value": image_mrp,
            "severity": "CRITICAL",
            "rule": "Listing MRP must not exceed the package MRP.",
        })

    # Do not award a perfect score merely because the webpage contains six
    # strings. A full score requires all mandatory declarations and no detected
    # web-vs-package discrepancy.
    base_score = round(found_count / len(REQUIRED_ECOM_DECLARATIONS) * 100)
    critical = sum(1 for d in discrepancies if d["severity"] == "CRITICAL")
    high = sum(1 for d in discrepancies if d["severity"] == "HIGH")
    medium = sum(1 for d in discrepancies if d["severity"] == "MEDIUM")

    penalty = critical * 35 + high * 20 + medium * 10
    final_score = max(0, min(100, base_score - penalty))

    if not scraped.get("image_paths"):
        status = "PARTIALLY_COMPLIANT" if base_score >= 50 else "NON_COMPLIANT"
        if base_score == 100:
            status = "REVIEW_REQUIRED"
    elif final_score == 100:
        status = "COMPLIANT"
    elif final_score >= 50:
        status = "PARTIALLY_COMPLIANT"
    else:
        status = "NON_COMPLIANT"

    return {
        "status": "success",
        "url": url,
        "final_url": scraped.get("final_url"),
        "product_title": scraped.get("title"),
        "compliance_score": final_score,
        "compliance_status": status,
        "mandatory_fields_audit": field_audit,
        "missing_declarations": missing,
        "discrepancies": discrepancies,
        "scraped_metadata": web,
        "extracted_image_declarations": image,
        "images_scanned": len(image_analyses),
        "image_errors": errors,
        "sale_price_detected": sale_price,
        "notes": [
            "JSON-LD/current retailer offer price is treated as sale price, not MRP.",
            "A 100% score requires all mandatory fields and no detected source discrepancy.",
        ],
    }
