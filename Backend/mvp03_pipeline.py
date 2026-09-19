try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None

from extraction import extract_fields
from declarations import extract_declarations, print_declaration_report

import sys
import cv2

def preprocess_image(image_path):
    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError(
            f"Could not read image: {image_path}"
        )

    # Upscale image
    image = cv2.resize(
        image,
        None,
        fx=2.0,
        fy=2.0,
        interpolation=cv2.INTER_CUBIC
    )

    # Convert to grayscale
    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    # Improve local contrast
    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    enhanced = clahe.apply(gray)

    # Convert back to 3-channel image for PaddleOCR
    enhanced = cv2.cvtColor(
        enhanced,
        cv2.COLOR_GRAY2BGR
    )

    return enhanced


# ============================================================
# INPUT IMAGE
# ============================================================

IMAGE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "original_package.jpg"
)


# ============================================================
# PADDLEOCR
# ============================================================

if __name__ == "__main__":
    print("Loading PaddleOCR...")

ocr_items = []
if PaddleOCR is not None:
    try:
        ocr = PaddleOCR(
            lang="en",
            device="cpu",
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False
        )
        preprocessed = preprocess_image(IMAGE)
        results = ocr.predict(preprocessed)
    except Exception:
        results = []
else:
    results = []


# ============================================================
# CONVERT PADDLEOCR OUTPUT
# INTO OUR STANDARD FORMAT
# ============================================================

ocr_items = []

for result in results:

    data = result.json
    res = data["res"]

    texts = res.get("rec_texts", [])
    scores = res.get("rec_scores", [])
    boxes = res.get("rec_boxes", [])

    for i, text in enumerate(texts):

        confidence = float(scores[i])

        box = boxes[i]

        if isinstance(box, list) and len(box) > 0 and isinstance(box[0], (list, tuple)):
            box = [[float(p[0]), float(p[1])] for p in box]
        else:
            box = [float(x) for x in box]

        ocr_items.append({
            "text": text,
            "confidence": confidence,
            "box": box
        })


# ============================================================
# EXISTING EXTRACTION
# ============================================================

fields = extract_fields(
    ocr_items
)





declarations = extract_declarations(
    ocr_items,
    existing_fields=fields
)




if __name__ == "__main__":
    print()
    print("=" * 70)
    print("COUNTRY DEBUG")
    print("=" * 70)

    for item in ocr_items:
        text = str(item.get("text", ""))
        if "made" in text.lower() or "india" in text.lower() or "origin" in text.lower():
            print("TEXT:", repr(text), "| CONF:", item.get("confidence"), "| BOX:", item.get("box"))

    print("=" * 70)
    print()
    print("=" * 70)
    print("CONSUMER CARE DEBUG")
    print("=" * 70)

    for item in ocr_items:
        text = str(item.get("text", ""))
        if any(word in text.lower() for word in ["consumer", "customer", "complaint", "contact", "email", "mail", "tel", "phone", "care", "helpline", "query", "quer"]):
            print(f"TEXT: {text!r} | CONF: {item.get('confidence')} | BOX: {item.get('box')}")

    print("=" * 70)
    print()
    print("=" * 70)
    print("MANUFACTURER DEBUG")
    print("=" * 70)

    for item in ocr_items:
        text = str(item.get("text", ""))
        if any(word in text.lower() for word in ["manufact", "mfg", "packed", "packer", "import", "ltd", "limited", "pvt", "private", "industr", "address"]):
            print(f"TEXT: {text!r} | CONF: {item.get('confidence')} | BOX: {item.get('box')}")

    print("=" * 70)
    print()
    print("=" * 70)
    print("METROLOGYSHIELD MVP-03")
    print("=" * 70)
    print()
    print("MRP:")
    print(fields["mrp"])
    print()
    print("UNIT SALE PRICE:")
    print(fields["unit_sale_price"])
    print()
    print("NET QUANTITY:")
    print(fields["net_quantity"])

    print_declaration_report(declarations)

