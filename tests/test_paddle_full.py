import pytest
PaddleOCR = pytest.importorskip("paddleocr").PaddleOCR


from pathlib import Path

sample_data_dir = Path(__file__).resolve().parents[2] / "sample_data"
IMAGE = str(sample_data_dir / "test_package_3.jpg")


print("Loading PaddleOCR...")

ocr = PaddleOCR(
    lang="en",
    device="cpu",
    enable_mkldnn=False
)

print("PaddleOCR loaded.")
print(f"Reading: {IMAGE}")


results = ocr.predict(IMAGE)


print()
print("=" * 70)
print("FULL IMAGE PADDLEOCR RESULTS")
print("=" * 70)


for result in results:

    data = result.json

    res = data["res"]

    texts = res.get("rec_texts", [])
    scores = res.get("rec_scores", [])
    boxes = res.get("rec_boxes", [])

    print()

    for i, text in enumerate(texts):

        score = scores[i] if i < len(scores) else None
        box = boxes[i] if i < len(boxes) else None

        print(f"TEXT       : {text}")
        print(f"CONFIDENCE : {score}")
        print(f"BOX        : {box}")
        print("-" * 50)


print()
print("=" * 70)
print("FULL IMAGE TEST COMPLETE")
print("=" * 70)
