import re
import math


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    text = text.lower()

    # Common OCR substitutions
    text = text.replace("₹", " rs ")
    text = text.replace(":", " ")
    text = text.replace(".", " ")

    # Common OCR spelling mistakes
    text = text.replace("wolume", "volume")
    text = text.replace("quontity", "quantity")
    text = text.replace("quantlty", "quantity")
    text = text.replace("m.r.p", "mrp")
    text = text.replace("m r p", "mrp")
    text = text.replace("m8p", "mrp")
    text = text.replace("n.r.p", "mrp")
    text = text.replace("mr (r)", "mrp")
    text = text.replace("mr r", "mrp")
    text = text.replace("m r (r)", "mrp")
    text = text.replace("unit sales price", "unit sale price")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# FIELD LABEL DETECTION
# ============================================================

def is_mrp_label(text):
    if not text:
        return False
    normalized = normalize_text(text)
    t = normalized.replace(" ", "")
    return (
        "mrp" in t
        or "maximumretailprice" in t
        or "retailprice" in t
        # Common OCR corruption of “MRP (₹)” -> “MR (R)” / “MR (rs)”.
        or bool(re.search(r"\bmr\s*\(\s*(?:r|rs)\s*\)", normalized, re.I))
        or bool(re.search(r"\b(?:max|maximum)\s*(?:retail)?\s*price\b", normalized))
    )


def is_usp_label(text):
    if not text:
        return False
    t = normalize_text(text)
    return (
        "unit sale price" in t
        or "unit sales price" in t
        or "unit price" in t
        or "usp" in t
        or "sale price" in t
        or "unit price" in t
    )


def is_quantity_label(text):
    if not text:
        return False
    t = normalize_text(text)
    return (
        "net quantity" in t
        or "net qty" in t
        or "net volume" in t
        or "net wt" in t
        or "net weight" in t
        or "net content" in t
        or ("volume" in t and "net" in t)
        or ("quantity" in t and "net" in t)
    )


# ============================================================
# BOX UTILITIES
# ============================================================

def box_center(box):
    if not box:
        return (0.0, 0.0)
    if isinstance(box[0], (list, tuple)):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    elif len(box) >= 4:
        return ((float(box[0]) + float(box[2])) / 2.0, (float(box[1]) + float(box[3])) / 2.0)
    return (0.0, 0.0)


# ============================================================
# PRICE EXTRACTION
# ============================================================

def extract_price(text):
    if not text:
        return None

    cleaned = text.lower().replace(",", "")
    matches = re.findall(r"\d+(?:\.\d{1,2})?", cleaned)
    if not matches:
        return None

    # Prefer decimal values if present
    decimal_numbers = [x for x in matches if "." in x]
    candidate = decimal_numbers[0] if decimal_numbers else matches[0]

    try:
        return float(candidate)
    except ValueError:
        return None


# ============================================================
# UNIT SALE PRICE EXTRACTION
# ============================================================

def extract_usp(text, default_unit=None):
    if not text:
        return None

    cleaned = text.lower().replace(",", "")

    # Standard explicit format: 2.59/ml or ₹2.59 / ml or 14.98/ml
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:/\s*|per\s+)(kg|g|mg|l|ml|cl|n|pcs?|units?|pages?)\b", cleaned)
    if match:
        try:
            val = float(match.group(1))
            unit = match.group(2)
            if unit in ["pc", "pcs"]:
                unit = "pcs"
            elif unit in ["n", "unit", "units"]:
                unit = "units"
            elif unit in ["page", "pages"]:
                unit = "pages"
            return {"value": val, "unit": unit}
        except ValueError:
            return None

    # OCR-separated case with default unit from label
    if default_unit:
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", cleaned)
        if match:
            try:
                return {"value": float(match.group(1)), "unit": default_unit}
            except ValueError:
                return None

    return None


# ============================================================
# QUANTITY / VOLUME EXTRACTION
# ============================================================

def extract_quantity(text):
    if not text:
        return None

    cleaned = text.lower()
    # Packaging often prints an OCR-sensitive metrology mark such as “e50ml”.
    # Strip only a standalone leading e before a quantity, while keeping
    # alphanumeric batch/model strings protected.
    cleaned = re.sub(r"(?<![a-z0-9])e(?=\d)", "", cleaned)

    # Match number followed by unit, ensuring no preceding letters/digits
    # (e.g. BHG337 and 123456 should not become quantities).
    match = re.search(
        r"(?<![a-zA-Z0-9])(\d+(?:\.\d+)?)\s*"
        r"(kg|gms?|grams?|g|mg|ml|cl|ltrs?|liters?|litres?|l|pages?|sheets?|pcs|pieces?|piece|nos?|no|n|units?)\b",
        cleaned
    )

    if not match:
        return None

    try:
        value = float(match.group(1))
    except ValueError:
        return None

    raw_unit = match.group(2)
    # Unit normalization
    if raw_unit in ["page", "pages"]:
        unit = "pages"
    elif raw_unit in ["sheet", "sheets"]:
        unit = "sheets"
    elif raw_unit in ["pc", "pcs", "piece", "pieces"]:
        unit = "pcs"
    elif raw_unit in ["unit", "units", "n", "no", "nos"]:
        unit = "units"
    elif raw_unit in ["gm", "gms", "gram", "grams"]:
        unit = "g"
    elif raw_unit in ["ltr", "ltrs", "liter", "liters", "litre", "litres"]:
        unit = "l"
    else:
        unit = raw_unit

    return {
        "value": value,
        "unit": unit
    }


# ============================================================
# SPATIAL CANDIDATE SCORING
# ============================================================

def distance_between(box1, box2):
    x1, y1 = box_center(box1)
    x2, y2 = box_center(box2)
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def score_candidate(label_box, candidate_box, candidate_type):
    lx, ly = box_center(label_box)
    cx, cy = box_center(candidate_box)

    dx = cx - lx
    dy = abs(cy - ly)

    distance = math.sqrt(dx ** 2 + dy ** 2)
    score = 0.0

    if dx > 0:
        score += 40
    else:
        score -= 40

    if dy < 20:
        score += 100
    elif dy < 45:
        score += 60
    elif dy < 80:
        score += 20
    elif dy < 130:
        score += 5
    else:
        score -= 30

    score -= distance * 0.01

    if candidate_type == "usp":
        score += 10
    elif candidate_type == "quantity":
        score += 10
    elif candidate_type == "mrp":
        score += 10

    return score


# ============================================================
# FIND BEST CANDIDATE
# ============================================================

def find_best_candidate(label_item, ocr_items, candidate_type):
    candidates = []
    label_box = label_item["box"]

    for candidate in ocr_items:
        if candidate is label_item:
            continue

        text = candidate["text"]

        # MRP candidate evaluation
        if candidate_type == "mrp":
            value = extract_price(text)
            if value is None:
                continue

            if extract_usp(text) is not None:
                continue

            if re.search(r"\d+(?:\.\d+)?\s*/\s*(kg|g|mg|ml|l|cl|n|pcs?)\b", text.lower()):
                continue

            low_text = text.lower()
            digits_only = re.sub(r"\D", "", text)
            if re.search(r"\b\d{1,2}[/-]\d{4}\b|\b\d{4}[/-]\d{1,2}\b", low_text):
                continue
            if len(digits_only) >= 8 and not re.search(r"(?:₹|rs\.?|inr|/-)", low_text):
                continue
            # Guard against address fractions (e.g. 17/18) and dates/pincodes
            if re.search(r"\b\d+\s*/\s*\d+\b", text) and not re.search(r"(?:₹|rs\.?|inr|/-)", low_text):
                continue
            if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", low_text):
                continue
            if re.fullmatch(r"[1-9]\d{5}", digits_only) and not re.search(r"(?:₹|rs\.?|inr)", low_text):
                continue

            score = score_candidate(label_box, candidate["box"], "mrp")

            if re.search(r"(?:₹|rs\.?|inr|/-)", low_text):
                score += 90.0
            if re.fullmatch(r"\s*(?:₹|rs\.?|inr)?\s*\d+(?:\.\d{1,2})?\s*(?:/-)?\s*", low_text):
                score += 30.0

            candidates.append((score, value, candidate))

        # USP candidate evaluation
        elif candidate_type == "usp":
            label_text = normalize_text(label_item["text"])
            default_unit = None
            unit_match = re.search(r"/\s*(kg|g|mg|ml|l|cl|n|pcs?)\b", label_text)
            if unit_match:
                default_unit = unit_match.group(1)

            value = extract_usp(text)

            if value is None and default_unit:
                candidate_clean = text.strip()
                digits_only = re.sub(r"\D", "", candidate_clean)
                if len(digits_only) >= 8 and "." not in candidate_clean and not re.search(r"/\s*(?:kg|g|mg|ml|l|cl)", candidate_clean, re.I):
                    continue

                if re.fullmatch(r"(?:₹|rs\.?)?\s*\d+(?:\.\d+)?", candidate_clean, re.IGNORECASE):
                    value = extract_usp(candidate_clean, default_unit)

            if value is None:
                continue

            score = score_candidate(label_box, candidate["box"], "usp")
            if extract_usp(text) is not None:
                score += 100.0

            candidates.append((score, value, candidate))

        # Quantity candidate evaluation
        elif candidate_type == "quantity":
            value = extract_quantity(text)
            if value is None:
                continue

            score = score_candidate(label_box, candidate["box"], "quantity")
            candidates.append((score, value, candidate))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_fields(ocr_items):
    result = {
        "mrp": None,
        "unit_sale_price": None,
        "net_quantity": None
    }

    # 1. MRP
    mrp_candidates = []
    for item in ocr_items:
        if not is_mrp_label(item["text"]):
            continue

        inline_val = extract_price(item["text"])
        if inline_val is not None and extract_usp(item["text"]) is None:
            result["mrp"] = {
                "value": inline_val,
                "currency": "INR",
                "confidence": float(item["confidence"]),
                "association_score": 150.0
            }
            break

        best = find_best_candidate(item, ocr_items, "mrp")
        if best:
            mrp_candidates.append(best)

    if result["mrp"] is None and mrp_candidates:
        mrp_candidates.sort(key=lambda x: x[0], reverse=True)
        score, value, candidate = mrp_candidates[0]
        result["mrp"] = {
            "value": value,
            "currency": "INR",
            "confidence": float(candidate["confidence"]),
            "association_score": round(score, 2)
        }

    # 2. UNIT SALE PRICE
    usp_candidates = []
    for item in ocr_items:
        if not is_usp_label(item["text"]):
            continue

        inline_usp = extract_usp(item["text"])
        if inline_usp is not None:
            result["unit_sale_price"] = {
                "value": inline_usp["value"],
                "unit": inline_usp["unit"],
                "currency": "INR",
                "confidence": float(item["confidence"]),
                "association_score": 150.0
            }
            break

        best = find_best_candidate(item, ocr_items, "usp")
        if best:
            usp_candidates.append(best)

    if result["unit_sale_price"] is None and usp_candidates:
        usp_candidates.sort(key=lambda x: x[0], reverse=True)
        score, value, candidate = usp_candidates[0]
        result["unit_sale_price"] = {
            "value": value["value"],
            "unit": value["unit"],
            "currency": "INR",
            "confidence": float(candidate["confidence"]),
            "association_score": round(score, 2)
        }

    # 3. NET QUANTITY
    qty_candidates = []
    for item in ocr_items:
        if not is_quantity_label(item["text"]):
            continue

        inline_qty = extract_quantity(item["text"])
        if inline_qty is not None:
            qtype = "mass"
            if inline_qty["unit"] in ["ml", "l", "cl"]:
                qtype = "volume"
            elif inline_qty["unit"] in ["pages", "sheets", "pcs", "units"]:
                qtype = "count"

            result["net_quantity"] = {
                "value": inline_qty["value"],
                "unit": inline_qty["unit"],
                "type": qtype,
                "confidence": float(item["confidence"]),
                "association_score": 150.0
            }
            break

        best = find_best_candidate(item, ocr_items, "quantity")
        if best:
            qty_candidates.append(best)

    if result["net_quantity"] is None and qty_candidates:
        qty_candidates.sort(key=lambda x: x[0], reverse=True)
        score, value, candidate = qty_candidates[0]
        qtype = "mass"
        if value["unit"] in ["ml", "l", "cl"]:
            qtype = "volume"
        elif value["unit"] in ["pages", "sheets", "pcs", "units"]:
            qtype = "count"

        result["net_quantity"] = {
            "value": value["value"],
            "unit": value["unit"],
            "type": qtype,
            "confidence": float(candidate["confidence"]),
            "association_score": round(score, 2)
        }

    # Fallback for standalone quantity (e.g. "180 Pages", "100 ml", "2 N")
    if result["net_quantity"] is None:
        for item in ocr_items:
            standalone_qty = extract_quantity(item["text"])
            if (
                standalone_qty is not None
                and not is_mrp_label(item["text"])
                and not is_usp_label(item["text"])
            ):
                qtype = "mass"
                if standalone_qty["unit"] in ["ml", "l", "cl"]:
                    qtype = "volume"
                elif standalone_qty["unit"] in ["pages", "sheets", "pcs", "units"]:
                    qtype = "count"

                result["net_quantity"] = {
                    "value": standalone_qty["value"],
                    "unit": standalone_qty["unit"],
                    "type": qtype,
                    "confidence": float(item["confidence"]),
                    "association_score": 80.0
                }
                break

    return result
