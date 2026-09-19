import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from extraction import extract_fields


ocr_items = [
    {
        "text": "MRP:",
        "confidence": 0.9981513,
        "box": [96, 834, 199, 866]
    },
    {
        "text": "5.00",
        "confidence": 0.9998496,
        "box": [231, 835, 314, 867]
    },
    {
        "text": "(INCL. OF ALL TAXES)",
        "confidence": 0.9585,
        "box": [103, 863, 263, 883]
    },
    {
        "text": "UNIT SALE PRICE :",
        "confidence": 0.9866867,
        "box": [105, 898, 367, 935]
    },
    {
        "text": "Rs.0.25/g",
        "confidence": 0.9993505,
        "box": [426, 936, 514, 972]
    },
    {
        "text": "NET QUANTITY:",
        "confidence": 0.9968701,
        "box": [112, 970, 336, 1010]
    },
    {
        "text": "20g",
        "confidence": 0.9999854,
        "box": [422, 975, 477, 1016]
    }
]


result = extract_fields(ocr_items)


print()
print("=" * 60)
print("METROLOGYSHIELD MVP-02")
print("=" * 60)

print()

print("MRP:")
print(result["mrp"])

print()

print("UNIT SALE PRICE:")
print(result["unit_sale_price"])

print()

print("NET QUANTITY:")
print(result["net_quantity"])

print()
print("=" * 60)