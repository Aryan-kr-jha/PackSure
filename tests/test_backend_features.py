import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.compliance import evaluate_compliance
from db.repository import ScanRepository
from reports.pdf import build_scan_report


def complete_declarations():
    return {k: {"value": "present", "status": "FOUND", "confidence": 0.95} for k in ["1_manufacturer_packer_importer", "2_country_of_origin", "3_generic_common_name", "4_net_quantity", "5_manufacture_packing_date", "6_expiry_best_before", "7_mrp", "8_unit_sale_price", "9_consumer_care"]}


def test_missing_mandatory_fields_are_reported():
    result = evaluate_compliance({}, {})
    assert result["status"] == "NON_COMPLIANT"
    assert {v["rule_code"] for v in result["violations"]} >= {"LM-MFG-001", "LM-MRP-007"}


def test_price_mismatch_is_detected():
    declarations = complete_declarations()
    declarations["7_mrp"] = {"value": 100, "status": "FOUND"}
    declarations["8_unit_sale_price"] = {"value": {"value": 1, "unit": "g"}, "status": "FOUND"}
    declarations["4_net_quantity"] = {"value": {"value": 10, "unit": "g"}, "status": "FOUND"}
    result = evaluate_compliance({}, declarations)
    assert any(v["rule_code"] == "LM-MATH-010" for v in result["violations"])


def test_memory_repository_history_and_analytics():
    repo = ScanRepository()
    record = repo.create(filename="x.jpg", image_url=None, ocr=[], fields={}, declarations={}, compliance={"score": 90, "status": "WARNING", "violations": []})
    assert repo.get(record["id"])["filename"] == "x.jpg"
    assert repo.list(status="WARNING")["total"] == 1
    assert repo.analytics()["total_packages_scanned"] == 1


def test_pdf_report_is_generated():
    pdf = build_scan_report({"id": "abc", "filename": "x.jpg", "compliance_score": 75, "compliance_status": "WARNING", "violations": []})
    assert pdf.startswith(b"%PDF")

