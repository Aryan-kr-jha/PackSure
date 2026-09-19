from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    code: str
    field: str
    description: str
    clause: str
    severity: str = "HIGH"
    weight: float = 10.0


RULES = (
    Rule("LM-MFG-001", "1_manufacturer_packer_importer", "Manufacturer, packer, or importer name and address is required.", "Packaged Commodities Rules, 2011, Rule 6(1)(a)"),
    Rule("LM-ORG-002", "2_country_of_origin", "Country of origin is required for imported packages.", "Packaged Commodities Rules, 2011, Rule 6(1)(aa)", "MEDIUM", 8),
    Rule("LM-GEN-003", "3_generic_common_name", "The common or generic name of the commodity is required.", "Packaged Commodities Rules, 2011, Rule 6(1)(b)", "HIGH", 10),
    Rule("LM-QTY-004", "4_net_quantity", "Net quantity with an appropriate unit is required.", "Packaged Commodities Rules, 2011, Rule 6(1)(d)", "HIGH", 12),
    Rule("LM-DATE-005", "5_manufacture_packing_date", "Month and year of manufacture, packing, or import is required.", "Packaged Commodities Rules, 2011, Rule 6(1)(e)", "HIGH", 10),
    Rule("LM-EXP-006", "6_expiry_best_before", "Expiry date or best-before declaration is required where applicable.", "Packaged Commodities Rules, 2011, Rule 6(1)(f)", "HIGH", 10),
    Rule("LM-MRP-007", "7_mrp", "Maximum retail price inclusive of all taxes is required.", "Packaged Commodities Rules, 2011, Rule 6(1)(e)", "HIGH", 12),
    Rule("LM-CARE-008", "9_consumer_care", "Consumer care contact details are required.", "Packaged Commodities Rules, 2011, Rule 6(1)(k)", "MEDIUM", 8),
    Rule("LM-BATCH-009", "batch_number", "Batch or lot identification should be traceable when present on the label.", "Legal Metrology Act, 2009, traceability control", "LOW", 5),
)


def _found(value: Any) -> bool:
    if isinstance(value, dict):
        status = str(value.get("status", "")).upper()
        return status == "FOUND" and value.get("value") not in (None, "", [])
    return value not in (None, "", [])


def _value(fields: dict[str, Any], key: str) -> Any:
    value = fields.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _violation(rule: Rule, message: str | None = None) -> dict[str, Any]:
    return {"rule_code": rule.code, "field": rule.field, "description": message or rule.description, "clause": rule.clause, "severity": rule.severity, "weight": rule.weight}


def evaluate_compliance(fields: dict[str, Any], declarations: dict[str, Any], *, tolerance: float = 0.05) -> dict[str, Any]:
    merged = dict(declarations or {})
    merged.update({k: v for k, v in (fields or {}).items() if v is not None})
    violations: list[dict[str, Any]] = []
    applicable_weight = sum(r.weight for r in RULES if r.field != "2_country_of_origin")
    for rule in RULES:
        if rule.field == "batch_number":
            continue
        if rule.field == "2_country_of_origin":
            # Country of origin is evaluated whenever origin/import language is available; for domestic labels this is a warning.
            if not _found(merged.get(rule.field)):
                violations.append(_violation(rule, "Country of origin was not detected; verify whether the package is imported."))
            continue
        if not _found(merged.get(rule.field)):
            violations.append(_violation(rule))
    # Cross-field math: USP is expected to be MRP divided by the declared quantity in the same base unit.
    mrp_raw = _value(merged, "7_mrp") or _value(merged, "mrp")
    usp_raw = _value(merged, "8_unit_sale_price") or _value(merged, "unit_sale_price")
    qty_raw = _value(merged, "4_net_quantity") or _value(merged, "net_quantity")

    try:
        mrp_num = float(mrp_raw) if isinstance(mrp_raw, (int, float, str)) and str(mrp_raw).replace(".", "", 1).isdigit() else None
    except (TypeError, ValueError):
        mrp_num = None

    try:
        if isinstance(usp_raw, dict) and "value" in usp_raw:
            usp_num = float(usp_raw["value"])
        elif isinstance(usp_raw, (int, float, str)) and str(usp_raw).replace(".", "", 1).isdigit():
            usp_num = float(usp_raw)
        else:
            usp_num = None
    except (TypeError, ValueError):
        usp_num = None

    try:
        if isinstance(qty_raw, dict) and "value" in qty_raw:
            qty_num = float(qty_raw["value"])
        elif isinstance(qty_raw, (int, float, str)) and str(qty_raw).replace(".", "", 1).isdigit():
            qty_num = float(qty_raw)
        else:
            qty_num = None
    except (TypeError, ValueError):
        qty_num = None

    usp_unit = str(usp_raw.get("unit", "")).lower() if isinstance(usp_raw, dict) else ""
    qty_unit = str(qty_raw.get("unit", "")).lower() if isinstance(qty_raw, dict) else ""

    if mrp_num and usp_num and qty_num and qty_num > 0:
        conversions = {("kg", "g"): 1000, ("l", "ml"): 1000}
        factor = conversions.get((qty_unit, usp_unit), 1) if qty_unit and usp_unit and qty_unit != usp_unit else 1
        expected = mrp_num / (qty_num * factor)
        if expected and abs(usp_num - expected) / expected > tolerance:
            rule = Rule("LM-MATH-010", "8_unit_sale_price", "Unit sale price does not reconcile with MRP and net quantity.", "Price consistency validation", "MEDIUM", 8)
            unit_disp = f"/{usp_unit}" if usp_unit else ""
            violations.append(_violation(rule, f"Expected approximately ₹{expected:.2f}{unit_disp}; detected ₹{usp_num:.2f}{unit_disp}."))

    score = max(0.0, round(100 * (1 - sum(float(v["weight"]) for v in violations) / max(applicable_weight, 1)), 2))
    status = "COMPLIANT" if not violations else "WARNING" if score >= 70 else "NON_COMPLIANT"
    return {"score": score, "status": status, "violations": violations, "rules_evaluated": len(RULES) - 1, "summary": f"{len(violations)} compliance issue(s) detected."}


__all__ = ["evaluate_compliance", "RULES"]

