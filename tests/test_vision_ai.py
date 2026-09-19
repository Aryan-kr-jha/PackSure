import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.vision_ai import FIELDS, extract_package_semantics


class FakeProvider:
    def extract(self, image_path, ocr_items):
        return {"status": "ok", "provider": "fake", "notes": "test", "fields": {key: {"value": None, "status": "MISSING", "confidence": 0, "evidence": [], "reason": "not visible"} for key in FIELDS}}


def test_vision_function_returns_explicit_missing_fields(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"fake")
    result = extract_package_semantics(image, [{"text": "MRP", "confidence": 0.9, "box": [0, 0, 10, 10]}], provider=FakeProvider())
    assert result["status"] == "ok"
    assert set(result["fields"]) == set(FIELDS)
    assert all(field["status"] == "MISSING" for field in result["fields"].values())

