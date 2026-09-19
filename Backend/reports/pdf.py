from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


MANDATORY_RULES = [
    ("LM-MFG-001", "Manufacturer / Packer / Importer", "Rule 6(1)(a)", "1_manufacturer_packer_importer"),
    ("LM-GEN-003", "Common / Generic Product Name", "Rule 6(1)(b)", "3_generic_common_name"),
    ("LM-QTY-004", "Net Quantity Declaration", "Rule 6(1)(d)", "4_net_quantity"),
    ("LM-DATE-005", "Date of Manufacture / Packing", "Rule 6(1)(e)", "5_manufacture_packing_date"),
    ("LM-MRP-007", "Maximum Retail Price (MRP)", "Rule 6(1)(e)", "7_mrp"),
    ("LM-EXP-006", "Expiry / Best Before Date", "Rule 6(1)(f)", "6_expiry_best_before"),
    ("LM-CARE-008", "Consumer Care Contact Details", "Rule 6(1)(k)", "9_consumer_care"),
    ("LM-ORG-002", "Country of Origin", "Rule 6(1)(aa)", "2_country_of_origin"),
    ("LM-MATH-010", "Unit Sale Price Consistency", "Price Math", "8_unit_sale_price"),
]

FIELD_KEY_ALIASES = {
    "1_manufacturer_packer_importer": [
        "1_manufacturer_packer_importer", "manufacturer", "packer", "importer"
    ],
    "3_generic_common_name": [
        "3_generic_common_name", "generic_common_name", "product_common_name", "generic_name"
    ],
    "4_net_quantity": ["4_net_quantity", "net_quantity", "quantity"],
    "5_manufacture_packing_date": [
        "5_manufacture_packing_date", "manufacture_packing_date", "mfd", "pkd_date"
    ],
    "7_mrp": ["7_mrp", "mrp", "max_retail_price"],
    "6_expiry_best_before": [
        "6_expiry_best_before", "expiry_best_before", "exp_date"
    ],
    "9_consumer_care": ["9_consumer_care", "consumer_care", "customer_care"],
    "2_country_of_origin": [
        "2_country_of_origin", "country_of_origin", "origin"
    ],
    "8_unit_sale_price": ["8_unit_sale_price", "unit_sale_price", "usp"],
}


def _safe_text(value: Any) -> str:
    """Convert arbitrary backend data to safe ReportLab paragraph text."""
    if value is None:
        return ""
    # Standard Helvetica does not contain the Unicode Rupee glyph (₹)
    s = str(value).replace("₹", "Rs. ")
    return escape(s)


def _value_from_entry(value: Any) -> str:
    if isinstance(value, dict):
        nested = value.get("value")
        if nested not in (None, "", []):
            if isinstance(nested, dict):
                # 1. Structured quantity / price with unit (e.g. {"value": 100, "unit": "ml"})
                if "unit" in nested and "value" in nested:
                    return f"{nested.get('value', '')} {nested.get('unit', '')}".strip()
                # 2. Structured manufacturer (e.g. {"text": "...", "pin_code": "..."})
                if "text" in nested and nested.get("text"):
                    return str(nested["text"]).strip()
                # 3. Structured consumer care (e.g. {name_or_designation, phone, email, address})
                parts = []
                if nested.get("name_or_designation"):
                    parts.append(str(nested["name_or_designation"]))
                if nested.get("phone"):
                    parts.append(f"Phone: {nested['phone']}")
                if nested.get("email"):
                    parts.append(f"Email: {nested['email']}")
                if nested.get("address"):
                    parts.append(f"Address: {nested['address']}")
                if parts:
                    return " | ".join(parts)
                return str(nested)
            return str(nested)

        # Some declaration objects store useful text directly or in evidence
        if "text" in value and value.get("text"):
            return str(value["text"]).strip()

        parts = []
        if value.get("name_or_designation"):
            parts.append(str(value["name_or_designation"]))
        if value.get("phone"):
            parts.append(f"Phone: {value['phone']}")
        if value.get("email"):
            parts.append(f"Email: {value['email']}")
        if value.get("address"):
            parts.append(f"Address: {value['address']}")
        if parts:
            return " | ".join(parts)

        for key in ("evidence", "detected_value"):
            candidate = value.get(key)
            if candidate not in (None, "", []):
                if isinstance(candidate, list):
                    return " ".join(str(c) for c in candidate)
                return str(candidate)

        return ""

    if value not in (None, "", []):
        return str(value)
    return ""


def _entry_for_field(scan: dict, primary_field_key: str) -> tuple[Any, str]:
    aliases = FIELD_KEY_ALIASES.get(primary_field_key, [primary_field_key])
    extracted_json = scan.get("extracted_fields_json", {})
    if not isinstance(extracted_json, dict):
        extracted_json = {}

    sources = (
        scan.get("declarations", {}),
        scan.get("fields", {}),
        extracted_json.get("declarations", {}),
        extracted_json.get("fields", {}),
        scan.get("detected_values", {}),
    )

    for src in sources:
        if not isinstance(src, dict):
            continue

        for key in aliases:
            if key in src:
                raw = src[key]
                value = _value_from_entry(raw)
                status = ""
                if isinstance(raw, dict):
                    status = str(raw.get("status", "")).upper()
                return raw, status if status else ("PRESENT" if value else "MISSING")

    return None, "MISSING"


def _extract_value(scan: dict, primary_field_key: str) -> str:
    raw, _ = _entry_for_field(scan, primary_field_key)
    return _value_from_entry(raw)


def _normalise_status(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _score_string(scan: dict) -> str:
    score = scan.get("compliance_score", scan.get("score"))
    if score is None:
        return "NOT AVAILABLE"

    try:
        return f"{float(score):.2f}%"
    except (TypeError, ValueError):
        return _safe_text(score)


def _verdict(scan: dict) -> str:
    value = scan.get("compliance_status", scan.get("status"))
    if value is None or str(value).strip() == "":
        return "NOT AVAILABLE"
    return str(value).strip().upper()


def _rule_is_failed(
    scan: dict,
    rule_code: str,
    field_key: str,
    violated_rule_codes: set[str],
) -> bool:
    if rule_code in violated_rule_codes:
        return True

    _, field_status = _entry_for_field(scan, field_key)
    return field_status in {
        "MISSING",
        "FAIL",
        "FAILED",
        "NON_COMPLIANT",
        "VIOLATION",
    }


def build_scan_report(scan: dict) -> bytes:
    """
    Build the compliance audit PDF from the supplied scan result.

    This function does not invent a score, verdict, declaration value, or
    violation. Missing backend data is shown explicitly as NOT AVAILABLE or
    NOT DETECTED / MISSING.
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="PackSure AI — Legal Metrology Compliance Audit Report",
        author="PackSure AI",
        subject="Legal Metrology Compliance Audit Report",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "PackSureTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F2942"),
        alignment=0,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "PackSureSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#555555"),
    )
    h2_style = ParagraphStyle(
        "PackSureH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F2942"),
        spaceBefore=9,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "PackSureBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.6,
        leading=10,
        wordWrap="LTR",
    )
    body_small_style = ParagraphStyle(
        "PackSureBodySmall",
        parent=body_style,
        fontSize=7,
        leading=9,
    )
    pass_style = ParagraphStyle(
        "PassBadge",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#2E7D32"),
    )
    fail_style = ParagraphStyle(
        "FailBadge",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#C62828"),
    )
    warning_style = ParagraphStyle(
        "WarningBadge",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#B26A00"),
    )
    neutral_style = ParagraphStyle(
        "NeutralBadge",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#455A64"),
    )

    story = []

    story.append(
        Paragraph(
            "PackSure AI — Legal Metrology Compliance Audit Report",
            title_style,
        )
    )
    story.append(
        Paragraph(
            "Automated Packaging Label & Statutory Declaration Audit Engine",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 8))

    score_str = _score_string(scan)
    status_str = _verdict(scan)

    status_key = _normalise_status(status_str)
    if status_key in {"COMPLIANT", "PASS", "PASSED"}:
        status_color = "#2E7D32"
    elif status_key in {"NON_COMPLIANT", "NONCOMPLIANT", "FAIL", "FAILED"}:
        status_color = "#C62828"
    elif status_key in {"WARNING", "WARN"}:
        status_color = "#B26A00"
    else:
        status_color = "#455A64"

    meta_table = Table(
        [
            [
                Paragraph(
                    f"<b>Scan ID:</b> {_safe_text(scan.get('id', 'N/A'))}",
                    body_style,
                ),
                Paragraph(
                    f"<b>Compliance Score:</b> "
                    f"<font color='#0F2942'><b>{score_str}</b></font>",
                    body_style,
                ),
            ],
            [
                Paragraph(
                    f"<b>Product File:</b> {_safe_text(scan.get('filename', 'N/A'))}",
                    body_style,
                ),
                Paragraph(
                    f"<b>Audit Verdict:</b> "
                    f"<font color='{status_color}'><b>{_safe_text(status_str)}</b></font>",
                    body_style,
                ),
            ],
            [
                Paragraph(
                    f"<b>Scan Timestamp:</b> "
                    f"{_safe_text(scan.get('created_at', 'N/A'))}",
                    body_style,
                ),
                Paragraph(
                    "<b>Rule Engine Version:</b> Legal Metrology 2011",
                    body_style,
                ),
            ],
        ],
        colWidths=[90 * mm, 90 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F4F8")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B0BEC5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CFD8DC")),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 9))

    story.append(
        Paragraph(
            "Mandatory Statutory Declaration Checklist & Detected Label Values",
            h2_style,
        )
    )

    violations = scan.get("violations") or []
    if not isinstance(violations, list):
        violations = []

    violated_rule_codes = {
        str(v.get("rule_code")).strip()
        for v in violations
        if isinstance(v, dict) and v.get("rule_code")
    }

    checklist_rows = [
        [
            Paragraph("<b>Status</b>", body_style),
            Paragraph("<b>Declaration Rule</b>", body_style),
            Paragraph("<b>Detected Label Value / Evidence</b>", body_style),
            Paragraph("<b>Clause</b>", body_style),
            Paragraph("<b>Rule Code</b>", body_style),
        ]
    ]

    for rule_code, rule_name, clause, field_key in MANDATORY_RULES:
        raw_entry, field_status = _entry_for_field(scan, field_key)
        value_text = _value_from_entry(raw_entry)
        failed = _rule_is_failed(
            scan, rule_code, field_key, violated_rule_codes
        )

        if failed:
            status_p = Paragraph("[ FAIL ]", fail_style)
            val_display = value_text or "NOT DETECTED / MISSING"
            val_p = Paragraph(
                f"<font color='#C62828'><i>{_safe_text(val_display)}</i></font>",
                body_style,
            )
        elif field_status in {"WARNING", "UNCERTAIN", "REVIEW"}:
            status_p = Paragraph("[ WARNING ]", warning_style)
            val_display = value_text or "UNCERTAIN / REVIEW REQUIRED"
            val_p = Paragraph(
                f"<font color='#B26A00'><i>{_safe_text(val_display)}</i></font>",
                body_style,
            )
        elif value_text:
            status_p = Paragraph("[ PASS ]", pass_style)
            val_p = Paragraph(
                f"<font color='#1B5E20'>{_safe_text(value_text)}</font>",
                body_style,
            )
        else:
            # No value means the report cannot truthfully call the declaration
            # compliant merely because no explicit violation was emitted.
            status_p = Paragraph("[ FAIL ]", fail_style)
            val_p = Paragraph(
                "<font color='#C62828'><i>NOT DETECTED / MISSING</i></font>",
                body_style,
            )

        checklist_rows.append(
            [
                status_p,
                Paragraph(_safe_text(rule_name), body_style),
                val_p,
                Paragraph(_safe_text(clause), body_style),
                Paragraph(_safe_text(rule_code), body_small_style),
            ]
        )

    checklist_table = Table(
        checklist_rows,
        colWidths=[21 * mm, 48 * mm, 54 * mm, 32 * mm, 27 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    checklist_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2942")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B0BEC5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(checklist_table)
    story.append(Spacer(1, 9))

    story.append(
        Paragraph("Violations & Non-Compliance Details", h2_style)
    )

    if violations:
        v_rows = [
            [
                Paragraph("<b>Rule Code</b>", body_style),
                Paragraph("<b>Severity</b>", body_style),
                Paragraph("<b>Description / Finding</b>", body_style),
                Paragraph("<b>Legal Citation</b>", body_style),
            ]
        ]

        for violation in violations:
            if not isinstance(violation, dict):
                continue
            v_rows.append(
                [
                    Paragraph(
                        _safe_text(violation.get("rule_code", "")),
                        body_small_style,
                    ),
                    Paragraph(
                        _safe_text(violation.get("severity", "")),
                        body_small_style,
                    ),
                    Paragraph(
                        _safe_text(violation.get("description", "")),
                        body_style,
                    ),
                    Paragraph(
                        _safe_text(violation.get("clause", "")),
                        body_small_style,
                    ),
                ]
            )

        if len(v_rows) > 1:
            v_table = Table(
                v_rows,
                colWidths=[25 * mm, 20 * mm, 85 * mm, 52 * mm],
                repeatRows=1,
                hAlign="LEFT",
            )
            v_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C62828")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B0BEC5")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(v_table)
    else:
        story.append(
            Paragraph(
                "<font color='#2E7D32'><b>No statutory violations detected.</b> "
                "No violation records were supplied by the compliance engine.</font>",
                body_style,
            )
        )

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "<b>Disclaimer:</b> <i>This document is an automated regulatory "
            "screening report generated by <b>PackSure AI</b> under Legal "
            "Metrology (Packaged Commodities) Rules, 2011. Authorized officers "
            "should verify physical packaging samples before issuing official "
            "notices.</i>",
            subtitle_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()
