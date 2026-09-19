import pytest
PaddleOCR = pytest.importorskip("paddleocr").PaddleOCR

from pathlib import Path

sample_data_dir = Path(__file__).resolve().parents[2] / "sample_data"
IMAGE = str(sample_data_dir / "test_package_6.jpg")

print("Loading PaddleOCR...")

ocr = PaddleOCR(
    lang="en",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="cpu"
)

print("PaddleOCR loaded.")
print(f"Scanning: {IMAGE}")
print("=" * 80)

results = ocr.predict(IMAGE)

print("=" * 80)
print("RAW PADDLEOCR OUTPUT")
print("=" * 80)

for result in results:
    print(result)
