import pytest
cv2 = pytest.importorskip("cv2")
easyocr = pytest.importorskip("easyocr")


from pathlib import Path

sample_data_dir = Path(__file__).resolve().parents[2] / "sample_data"
IMAGE = str(sample_data_dir / "original_package.jpg")


print("Loading EasyOCR...")

reader = easyocr.Reader(
    ["en"],
    gpu=False,
    verbose=False
)

print("EasyOCR loaded.")


image = cv2.imread(IMAGE)

if image is None:
    raise FileNotFoundError(
        IMAGE
    )


# ============================================================
# ORIGINAL IMAGE
# ============================================================

height, width = image.shape[:2]

print(
    f"Original image: {width} x {height}"
)


# ============================================================
# PRICE ONLY
#
# From the original image the MRP value is approximately:
#
#              ₹5.00
#
# We intentionally exclude "MRP".
# ============================================================

x1 = 290
x2 = 410

y1 = 810
y2 = 875


price = image[
    y1:y2,
    x1:x2
]


cv2.imwrite(
    "price_debug.jpg",
    price
)


# ============================================================
# UPSCALE
# ============================================================

price = cv2.resize(
    price,
    None,
    fx=8,
    fy=8,
    interpolation=cv2.INTER_CUBIC
)


gray = cv2.cvtColor(
    price,
    cv2.COLOR_BGR2GRAY
)


# ============================================================
# SHARPEN
# ============================================================

blur = cv2.GaussianBlur(
    gray,
    (0, 0),
    1
)

sharp = cv2.addWeighted(
    gray,
    1.7,
    blur,
    -0.7,
    0
)


# ============================================================
# CONTRAST
# ============================================================

clahe = cv2.createCLAHE(
    clipLimit=2.0,
    tileGridSize=(8, 8)
)

enhanced = clahe.apply(
    sharp
)


# ============================================================
# OCR
# ============================================================

variants = {
    "color_upscaled": price,
    "gray": gray,
    "sharp": sharp,
    "enhanced": enhanced
}


for name, img in variants.items():

    print()
    print("=" * 60)
    print(f"TEST: {name}")
    print("=" * 60)

    results = reader.readtext(
        img,
        detail=1,
        paragraph=False,
        allowlist="0123456789.,₹",
        text_threshold=0.15,
        low_text=0.05,
        link_threshold=0.05,
        mag_ratio=1.0
    )

    if not results:

        print("NO RESULT")
        continue

    for box, text, confidence in results:

        print(
            f"TEXT       : {text}"
        )

        print(
            f"CONFIDENCE : {confidence:.3f}"
        )


print()
print("=" * 60)
print("NUMERIC-ONLY MRP TEST COMPLETE")
print("=" * 60)

print(
    "\nDebug crop saved as price_debug.jpg"
)
