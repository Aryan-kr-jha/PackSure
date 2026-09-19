"""Integration test for POST /api/scan endpoint with cache and OCR fallback."""
from __future__ import annotations

import io
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parents[1] / "Backend"
PROJECT_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_scan_api_endpoints():
    print("=== TESTING POST /api/scan WITH TEST CLIENT ===")

    # 1. Test Demo Package 3
    p3 = PROJECT_ROOT / "data" / "Good Image" / "test_package_3.jpg"
    with open(p3, "rb") as f:
        resp = client.post("/api/scan", files={"file": ("test_package_3.jpg", f, "image/jpeg")})
    assert resp.status_code == 200, f"Error: {resp.text}"
    data3 = resp.json()
    assert data3["status"] == "success"
    assert data3["cached"] is True
    assert data3["analysis"]["compliance"]["status"] == "COMPLIANT"
    print("PASS: POST /api/scan (test_package_3.jpg) -> status 200, cached=True, COMPLIANT")

    # 2. Test Demo Package 7
    p7 = PROJECT_ROOT / "data" / "Sample Image" / "test_package_7.jpg"
    with open(p7, "rb") as f:
        resp7 = client.post("/api/scan", files={"file": ("test_package_7.jpg", f, "image/jpeg")})
    assert resp7.status_code == 200, f"Error: {resp7.text}"
    data7 = resp7.json()
    assert data7["status"] == "success"
    assert data7["cached"] is True
    assert data7["analysis"]["compliance"]["status"] == "WARNING"
    print("PASS: POST /api/scan (test_package_7.jpg) -> status 200, cached=True, WARNING")

    # 3. Test GET /api/scans
    scans_resp = client.get("/api/scans")
    assert scans_resp.status_code == 200
    scans_data = scans_resp.json()
    assert "items" in scans_data
    assert len(scans_data["items"]) >= 2
    print(f"PASS: GET /api/scans -> status 200, {len(scans_data['items'])} items returned")

    # 4. Test PDF report generation
    scan_id = data3["scan"]["id"]
    pdf_resp = client.get(f"/api/reports/pdf?scan_id={scan_id}")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000
    print(f"PASS: GET /api/reports/pdf?scan_id={scan_id} -> status 200, valid PDF payload ({len(pdf_resp.content)} bytes)")

    print("\nALL API SCAN AND REPORT INTEGRATION TESTS PASSED.")

if __name__ == "__main__":
    test_scan_api_endpoints()
