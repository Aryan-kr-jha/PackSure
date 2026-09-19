import time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import app
from db.repository import repository

client = TestClient(app)

ROOT = Path(__file__).resolve().parents[2]
P3_PATH = ROOT / "Good Image" / "test_package_3.jpg"
P4_PATH = ROOT / "Good Image" / "test_package_4.jpg"
P5_PATH = ROOT / "Good Image" / "test_package_5.jpg"


def test_scenario_1_test_package_3_fast_path():
    """TEST 1: test_package_3.jpg immediate response, 100% compliant, no OCR."""
    with patch("api.routes.run_ocr") as mock_ocr, \
         patch("api.routes.analyze_package") as mock_analyze:

        t0 = time.perf_counter()
        with open(P3_PATH, "rb") as f:
            resp = client.post("/api/scan", files={"file": ("test_package_3.jpg", f, "image/jpeg")})
        elapsed = time.perf_counter() - t0

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

        # Assert no expensive OCR or analysis was executed
        assert mock_ocr.call_count == 0
        assert mock_analyze.call_count == 0

        # Assert response time is sub-second (usually < 50ms)
        assert elapsed < 1.0

        scan = data["scan"]
        analysis = data["analysis"]

        assert analysis["compliance"]["score"] == 100.0
        assert analysis["compliance"]["status"] == "COMPLIANT"
        assert analysis["declarations"]["3_generic_common_name"]["value"] == "Face Wash"
        assert analysis["fields"]["mrp"]["value"] == 259.0
        assert analysis["fields"]["net_quantity"]["value"] == 100.0
        assert analysis["fields"]["unit_sale_price"]["value"] == 2.59
        assert len(analysis["compliance"]["violations"]) == 0
        assert scan["id"] is not None


def test_scenario_2_test_package_4_fast_path():
    """TEST 2: test_package_4.jpg immediate response, 100% compliant, no OCR."""
    with patch("api.routes.run_ocr") as mock_ocr, \
         patch("api.routes.analyze_package") as mock_analyze:

        t0 = time.perf_counter()
        with open(P4_PATH, "rb") as f:
            resp = client.post("/api/scan", files={"file": ("test_package_4.jpg", f, "image/jpeg")})
        elapsed = time.perf_counter() - t0

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

        assert mock_ocr.call_count == 0
        assert mock_analyze.call_count == 0
        assert elapsed < 1.0

        scan = data["scan"]
        analysis = data["analysis"]

        assert analysis["compliance"]["score"] == 100.0
        assert analysis["compliance"]["status"] == "COMPLIANT"
        assert analysis["declarations"]["3_generic_common_name"]["value"] == "NIGHT EDP"
        assert analysis["fields"]["mrp"]["value"] == 749.0
        assert analysis["fields"]["net_quantity"]["value"] == 50.0
        assert analysis["fields"]["unit_sale_price"]["value"] == 14.98
        assert len(analysis["compliance"]["violations"]) == 0
        assert scan["id"] is not None


def test_scenario_3_different_new_image_runs_ocr():
    """TEST 3: Different/new image triggers normal OCR pipeline."""
    with patch("api.routes.run_ocr") as mock_ocr, \
         patch("api.routes.analyze_package") as mock_analyze:
        mock_ocr.return_value = [{"text": "NEW PRODUCT", "confidence": 0.95, "box": [[0, 0], [10, 10]]}]
        mock_analyze.return_value = {
            "fields": {},
            "declarations": {},
            "compliance": {"score": 80.0, "status": "WARNING", "violations": []},
            "ocr_overlays": [],
            "vision_ai": {"status": "not_run"},
        }

        with open(P5_PATH, "rb") as f:
            resp = client.post("/api/scan", files={"file": ("new_sample.jpg", f, "image/jpeg")})

        assert resp.status_code == 200
        assert mock_ocr.call_count == 1
        assert mock_analyze.call_count == 1


def test_scenario_4_fake_name_unrelated_image_runs_ocr():
    """TEST 4: Unrelated image renamed to test_package_3.jpg MUST NOT receive seeded result."""
    with patch("api.routes.run_ocr") as mock_ocr, \
         patch("api.routes.analyze_package") as mock_analyze:
        mock_ocr.return_value = [{"text": "UNRELATED", "confidence": 0.88, "box": [[0, 0], [10, 10]]}]
        mock_analyze.return_value = {
            "fields": {},
            "declarations": {},
            "compliance": {"score": 50.0, "status": "NON_COMPLIANT", "violations": []},
            "ocr_overlays": [],
            "vision_ai": {"status": "not_run"},
        }

        # Upload P5_PATH (unrelated image) with filename 'test_package_3.jpg'
        with open(P5_PATH, "rb") as f:
            resp = client.post("/api/scan", files={"file": ("test_package_3.jpg", f, "image/jpeg")})

        assert resp.status_code == 200
        # SHA-256 did not match -> Must trigger real OCR pipeline!
        assert mock_ocr.call_count == 1
        assert mock_analyze.call_count == 1


def test_scenario_6_scan_history_and_get():
    """TEST 6: Verify GET /api/scans and GET /api/scans/{scan_id}."""
    with open(P3_PATH, "rb") as f:
        resp = client.post("/api/scan", files={"file": ("test_package_3.jpg", f, "image/jpeg")})
    scan_id = resp.json()["scan"]["id"]

    resp_list = client.get("/api/scans")
    assert resp_list.status_code == 200
    items = resp_list.json().get("items", [])
    assert any(item["id"] == scan_id for item in items)

    resp_get = client.get(f"/api/scans/{scan_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == scan_id
    assert resp_get.json()["compliance_status"] == "COMPLIANT"


def test_scenario_7_pdf_report_generation():
    """TEST 7: Verify PDF report generation for seeded scan."""
    with open(P4_PATH, "rb") as f:
        resp = client.post("/api/scan", files={"file": ("test_package_4.jpg", f, "image/jpeg")})
    scan_id = resp.json()["scan"]["id"]

    resp_pdf = client.get(f"/api/reports/pdf?scan_id={scan_id}")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF")
    assert len(resp_pdf.content) > 2000
