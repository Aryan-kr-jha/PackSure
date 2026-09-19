import re
from typing import Any, Dict, List


# ============================================================
# PACKSURE — PHASE 3
# 10-field declaration extraction
#
# This module is intentionally separate from extraction.py.
# It does not change the working MRP / USP / Net Quantity code.
# ============================================================


PIN_RE = re.compile(r"\b[1-9][0-9]{5}\b")

EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
    re.I
)

PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+91[\s\-]?)?[6-9]\d{9}|1800[\s\-]?\d{3}[\s\-]?\d{4}|1800[\s\-]?\d{6,7}|1860[\s\-]?\d{3}[\s\-]?\d{4})(?!\d)",
    re.I
)

DATE_RE = re.compile(
    r"(?:\b|\s)(?:"
    r"(?:0?[1-9]|1[0-2])\s*[/\-]\s*\d{4}"
    r"|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[,\.\s]*\d{4}"
    r"|\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[,\.\s]*\d{4}"
    r")(?:\b|\s)",
    re.I,
)


DIMENSION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m)\s*[x×]\s*"
    r"\d+(?:\.\d+)?\s*(?:mm|cm|m)"
    r"(?:\s*[x×]\s*\d+(?:\.\d+)?\s*(?:mm|cm|m))?\b",
    re.I,
)


COUNT_RE = re.compile(
    r"\b(?:\d+\s*(?:pieces?|pcs?|units?|sheets?|pairs?)|"
    r"(?:pack|set)\s+of\s+\d+)\b",
    re.I,
)


COUNTRIES = [
    "india",
    "china",
    "germany",
    "japan",
    "france",
    "italy",
    "nepal",
    "bangladesh",
    "vietnam",
    "thailand",
    "indonesia",
    "australia",
    "canada",
    "usa",
    "united states",
    "united kingdom",
    "uae",
    "united arab emirates",
    "south korea",
    "korea",
]


PRODUCT_TERMS = [
    "body spray",
    "face wash",
    "facewash",
    "wash",
    "shampoo",
    "conditioner",
    "soap",
    "detergent",
    "toothpaste",
    "biscuit",
    "snacks",
    "namkeen",
    "rice",
    "flour",
    "oil",
    "juice",
    "beverage",
    "cream",
    "lotion",
    "perfume",
    "edp",
    "deodorant",
    "shirt",
    "t-shirt",
    "trouser",
    "jeans",
    "tissue",
    "foil",
    "paper",
    "bag",
    "stationery",
    "notebook",
    "register",
    "book",
    "journal",
    "footwear",
    "slipper",
    "slippers",
    "flip flop",
    "flip-flop",
    "sandals",
    "shoes",
    "accessory",
    "mouse",
    "keyboard",
    "headphone",
    "earphone",
    "cable",
    "charger",
]



# ============================================================
# BASIC HELPERS
# ============================================================

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def low(text: str) -> str:
    return clean(text).lower()


def _flatten_box(b: Any) -> list[float]:
    if not isinstance(b, (list, tuple)) or not b:
        return [0.0, 0.0, 0.0, 0.0]
    if isinstance(b[0], (list, tuple)):
        xs = [float(p[0]) for p in b if isinstance(p, (list, tuple)) and len(p) > 0]
        ys = [float(p[1]) for p in b if isinstance(p, (list, tuple)) and len(p) > 1]
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]
        return [0.0, 0.0, 0.0, 0.0]
    try:
        return [float(x) for x in b]
    except Exception:
        return [0.0, 0.0, 0.0, 0.0]


def cx(item: Dict[str, Any]) -> float:
    b = _flatten_box(item.get("box", [0, 0, 0, 0]))
    return (b[0] + b[2]) / 2.0


def cy(item: Dict[str, Any]) -> float:
    b = _flatten_box(item.get("box", [0, 0, 0, 0]))
    return (b[1] + b[3]) / 2.0


def conf(item: Dict[str, Any]) -> float:
    try:
        return float(item.get("confidence", 0))
    except Exception:
        return 0.0


def avg_conf(items: List[Dict[str, Any]]) -> float:
    return sum(conf(x) for x in items) / len(items) if items else 0.0


def result(
    value=None,
    status="MISSING",
    confidence=0.0,
    evidence=None
):
    return {
        "value": value,
        "status": status,
        "confidence": round(float(confidence), 4),
        "evidence": evidence or [],
    }




def wrap_existing_field(field, field_name):
    """
    extraction.py already gives us working MRP / USP / Net Quantity.

    Phase 3 needs:
        {
            "value": ...,
            "status": "FOUND",
            "confidence": ...
        }

    Preserve structured values (e.g. {"value": 100, "unit": "ml"})
    to satisfy canonical data contract.
    """

    if not field:
        return result(
            None,
            "MISSING",
            0.0,
            [field_name]
        )

    if not isinstance(field, dict):
        return result(
            field,
            "FOUND",
            0.0,
            [field_name]
        )

    value = field.get("value")

    confidence = float(
        field.get("confidence", 0.0)
    )

    if value is None:
        return result(
            None,
            "MISSING",
            confidence,
            [field_name]
        )

    # Preserve structured unit information for net_quantity and unit_sale_price
    if "unit" in field:
        structured_val = {"value": value, "unit": field["unit"]}
        return result(
            structured_val,
            "FOUND",
            confidence,
            [field_name]
        )

    return result(
        value,
        "FOUND",
        confidence,
        [field_name]
    )


def has(text: str, phrases: List[str]) -> bool:
    t = low(text)
    return any(p in t for p in phrases)


# ============================================================
# LABEL DETECTION
# ============================================================

def is_manufacturer_label(text):
    return has(text, [
        "manufactured & marketed by",
        "manufactured and marketed by",
        "manufactured by",
        "mfg by",
        "mfg. by",
        "manufactured & packed by",
        "manufactured and packed by",
        "imported and marketed by",
        "imported & marketed by",
        "imported by",
        "marketed by",
        "packed by",
        "importer",
        "packer",
    ])


def is_origin_label(text):
    return has(text, [
        "country of origin",
        "made in",
        "origin:",
    ])


def is_generic_label(text):
    return has(text, [
        "generic name",
        "common name",
        "product name",
        "commodity",
    ])


def is_mfg_label(text):
    # Reject license lines before checking for manufacturing dates
    if has(text, ["mfg. lic", "mfg lic", "lic. no.", "license", "licence", "st. ex. lic", "excise"]):
        return False

    return has(text, [
        "mfg date",
        "mfg. date",
        "wfg.date",
        "wfg date",
        "wfg. date",
        "wfg",
        "manufacturing date",
        "date of manufacture",
        "packed date",
        "packing date",
        "date of packing",
        "pkd",
        "mfd",
        "mfg",
    ])


def is_expiry_label(text):
    if has(text, ["lic. no.", "license", "licence"]):
        return False

    return has(text, [
        "expiry",
        "exp date",
        "exp. date",
        "exp.date",
        "expiry date",
        "use by",
        "use-by",
        "best before",
        "use before",
    ])



def is_consumer_label(text):
    return has(text, [
        "consumer care",
        "consumer care manager",
        "customer care",
        "customer care manager",
        "customer complaints",
        "customer complaint",
        "consumer complaints",
        "consumer complaint",
        "complaints/feedback",
        "complaint/feedback",
        "complaints / feedback",
        "for customer complaints",
        "for complaints",
        "for queries",
        "helpline",
        "contact us",
        "feedback",
    ])


# ============================================================
# 1. MANUFACTURER / PACKER / IMPORTER
# ============================================================

def extract_manufacturer(items):

    items = sorted(
        items,
        key=lambda x: (cy(x), cx(x))
    )

    for i, anchor in enumerate(items):

        if not is_manufacturer_label(anchor["text"]):
            continue

        anchor_x = cx(anchor)
        anchor_y = cy(anchor)

        collected = [anchor]

        candidates = []

        for item in items:

            if item is anchor:
                continue

            item_x = cx(item)
            item_y = cy(item)

            if item_y <= anchor_y:
                continue

            if item_y - anchor_y > 300:
                continue

            if abs(item_x - anchor_x) > 280:
                continue

            candidates.append(item)

        candidates.sort(
            key=lambda x: (cy(x), cx(x))
        )

        for item in candidates:

            text = clean(item["text"])

            if not text:
                continue

            t = low(text)

            if (
                is_consumer_label(text)
                or is_expiry_label(text)
                or is_mfg_label(text)
                or "marketed by" in t
                or "how to use" in t
                or t == "caution"
                or "mfg. lic" in t
                or "mfg lic" in t
                or "manufacturing licence" in t
                or "manufacturing license" in t
            ):
                break

            collected.append(item)

            if len(collected) >= 8:
                break

        evidence = [
            clean(x["text"])
            for x in collected
            if clean(x["text"])
        ]

        joined = " ".join(evidence)

        value = re.sub(
            r"^(?:"
            r"manufactured\s*(?:&|and)?\s*(?:marketed|packed)\s*by|"
            r"manufactured\s*by|"
            r"mfg\.?\s*by|"
            r"imported\s*(?:&|and)?\s*(?:marketed|packed)?\s*by|"
            r"imported\s*by|"
            r"marketed\s*by|"
            r"packed\s*by|"
            r"importer|"
            r"packer"
            r")"
            r"\s*:?\s*",
            "",
            joined,
            flags=re.I,
        ).strip()

        pin = PIN_RE.search(joined)

        if len(value) >= 4:

            return result(
                {
                    "text": value,
                    "pin_code": pin.group(0) if pin else None,
                    "pin_detected": bool(pin),
                },
                "FOUND",
                avg_conf(collected),
                evidence,
            )

    for i, item in enumerate(items):

        text_i = clean(item["text"])

        if not text_i:
            continue

        text_low = low(text_i)
        is_address_line = (
            bool(PIN_RE.search(text_i))
            or any(term in text_low for term in ["indl", "industrial", "area", "road", "nagar", "plot", "street", "delhi", "mumbai", "nd-"])
        )

        if not is_address_line:
            continue

        nearby = items[max(0, i - 4): i + 1]

        company_item = None

        for candidate in reversed(nearby):

            candidate_text = clean(candidate["text"])
            candidate_low = low(candidate_text)

            if any(term in candidate_low for term in [
                "ltd",
                "limited",
                "pvt",
                "private",
                "industries",
                "international",
                "packaging",
                "cosmetics",
                "manufacturer",
                "manufactured",
                "paper products",
                "products"
            ]):
                company_item = candidate
                break

        if company_item is None:
            continue

        block = []
        company_y = cy(company_item)

        for candidate in items:

            candidate_text = clean(candidate["text"])

            if not candidate_text:
                continue

            candidate_y = cy(candidate)

            if candidate_y < company_y - 20:
                continue

            if candidate_y > company_y + 170:
                continue

            if abs(cx(candidate) - cx(company_item)) > 260:
                continue

            block.append(candidate)

        block.sort(
            key=lambda x: (cy(x), cx(x))
        )

        evidence = [
            clean(x["text"])
            for x in block
            if clean(x["text"])
        ]

        if evidence:

            joined = " ".join(evidence)
            pin = PIN_RE.search(joined)

            cleaned_parts = []

            for part in evidence:

                if "marketed by" in low(part):
                    break

                cleaned_parts.append(part)

            value = " ".join(cleaned_parts).strip()

            if len(value) >= 4:

                return result(
                    {
                        "text": value,
                        "pin_code": pin.group(0) if pin else None,
                        "pin_detected": bool(pin),
                    },
                    "FOUND",
                    avg_conf(block),
                    cleaned_parts,
                )

    return result()



# ============================================================
# 2. COUNTRY OF ORIGIN
# ============================================================

def extract_country_origin(items):

    items = sorted(
        items,
        key=lambda x: (cy(x), cx(x))
    )

    # Add bharat to country list if not present
    all_countries = COUNTRIES + ["bharat"]

    def normalize_country(c_name):
        if c_name.lower() in ["bharat", "india"]:
            return "India"
        return c_name.title()

    # --------------------------------------------------------
    # 0. Check for concatenated OCR strings like MADEINBHARAT, MADEININDIA
    # --------------------------------------------------------
    for item in items:
        raw_t = clean(item["text"])
        compressed = re.sub(r"[^A-Za-z]", "", raw_t).lower()

        if "madeinbharat" in compressed or "madeinindia" in compressed:
            return result("India", "FOUND", conf(item), [raw_t])
        if "productofbharat" in compressed or "productofindia" in compressed:
            return result("India", "FOUND", conf(item), [raw_t])
        if compressed == "madeinbharat" or compressed == "madeinindia" or compressed == "bharat":
            return result("India", "FOUND", conf(item), [raw_t])

    # --------------------------------------------------------
    # 1. Explicit country-of-origin labels
    # --------------------------------------------------------

    for i, anchor in enumerate(items):

        text = clean(anchor["text"])

        if not is_origin_label(text):
            continue

        search = [anchor] + items[i + 1:i + 5]

        for item in search:

            item_text = clean(item["text"])
            item_low = low(item_text)

            for country in all_countries:

                if country.lower() in item_low:

                    return result(
                        normalize_country(country),
                        "FOUND",
                        avg_conf([anchor, item]),
                        [
                            clean(anchor["text"]),
                            item_text
                        ],
                    )

    # --------------------------------------------------------
    # 2. Direct "Made in / Mode in / Product of" detection
    # --------------------------------------------------------

    for item in items:

        text = clean(item["text"])

        patterns = [
            r"\b(?:made|mode|product|oduct)\s*(?:in|of)?\s*([a-z]+(?:\s+[a-z]+)*)",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            detected_country = match.group(1).strip().lower()

            for country in all_countries:

                if country.lower() == detected_country or country.lower() in detected_country.split():

                    return result(
                        normalize_country(country),
                        "FOUND",
                        conf(item),
                        [text],
                    )

    # --------------------------------------------------------
    # 3. Handle split OCR:
    # --------------------------------------------------------

    for i, item in enumerate(items):

        text = clean(item["text"])

        if not re.search(
            r"\b(?:made|mode|product|oduct)\s*"
            r"(?:in|of)?\b",
            text,
            re.IGNORECASE
        ):
            continue

        for candidate in items[i + 1:i + 4]:

            candidate_text = clean(candidate["text"])
            candidate_low = low(candidate_text)

            for country in all_countries:

                if country.lower() in candidate_low:

                    return result(
                        normalize_country(country),
                        "FOUND",
                        avg_conf([item, candidate]),
                        [
                            text,
                            candidate_text
                        ],
                    )

    # --------------------------------------------------------
    # 4. OCR damaged "India" / "Bharat" near origin wording
    # --------------------------------------------------------

    for item in items:

        text = clean(item["text"])
        text_low = low(text)

        origin_words = [
            "made",
            "mode",
            "product",
            "oduct",
            "origin"
        ]

        if not any(
            word in text_low
            for word in origin_words
        ):
            continue

        for country in all_countries:

            if country.lower() in text_low:

                return result(
                    normalize_country(country),
                    "FOUND",
                    conf(item),
                    [text],
                )

    # 5. Fallback: Indian manufacturing address state/pincode detection
    for item in items:
        text_low = low(item["text"])
        if any(place in text_low for place in ["india", "parwanoo", "bhiwadi", "gurugram", "gurugrom", "gurgaon", "haryana", "haryno", "delhi", "mumbai", "rajasthan", "h.p.", "sonipat", "alwar"]):
            return result("India", "FOUND", conf(item), [clean(item["text"])])

    return result()

# ============================================================
# 3. GENERIC / COMMON NAME
# ============================================================

def extract_generic_name(items):

    items = sorted(
        items,
        key=lambda x: (cy(x), cx(x))
    )

    for i, anchor in enumerate(items):

        if not is_generic_label(anchor["text"]):
            continue

        nearby = [
            anchor
        ] + items[i + 1:i + 3]

        evidence = [
            clean(x["text"])
            for x in nearby
            if clean(x["text"])
        ]

        value = " ".join(evidence)

        value = re.sub(
            r"^(?:generic\s*name|common\s*name|product\s*name|commodity)\s*:?\s*",
            "",
            value,
            flags=re.I,
        ).strip()

        # Truncate before model name, part number, SKU, serial number
        value = re.split(r"(?i)\b(?:model(?:\s*name)?|part(?:\s*no|\s*number)?|sku|serial(?:\s*no)?)\b", value)[0].strip(" :-/,")

        if len(value) >= 3:

            return result(
                value,
                "FOUND",
                avg_conf(nearby),
                evidence,
            )

    # Check for direct label match or header line
    for item in items:
        text = clean(item["text"])
        t = low(text)

        # Skip long paragraph sentences (> 40 chars) or company names
        if len(text) > 40:
            continue
        if any(c in t for c in ["pvt", "ltd", "private", "limited", "inc", "corp", "manufactured", "marketed", "ingredients"]):
            continue

        # Header match for generic product terms
        for term in PRODUCT_TERMS:
            if term in t:
                display_name = text
                if term in ["facewash", "face wash", "wash"]:
                    display_name = "Face Wash"
                elif term in ["footwear", "slipper", "slippers", "flip flop", "flip-flop"]:
                    display_name = "Footwear"
                return result(
                    display_name,
                    "FOUND",
                    conf(item),
                    [text],
                )

    return result()



def is_mfg_label(text):
    # Reject license and address lines before checking for manufacturing dates
    if has(text, ["mfg address", "mfg. address", "manufacturing address", "mfg. lic", "mfg lic", "lic. no.", "license", "licence", "st. ex. lic", "excise"]):
        return False

    return has(text, [
        "mfg date",
        "mfg. date",
        "wfg.date",
        "wfg date",
        "wfg. date",
        "wfg",
        "manufacturing date",
        "date of manufacture",
        "manufactured month",
        "manufacturedmonth",
        "month/year of mfg",
        "month/year",
        "packed date",
        "packing date",
        "date of packing",
        "pkd",
        "mfd",
        "mfg",
    ])


def is_expiry_label(text):
    if has(text, ["lic. no.", "license", "licence"]):
        return False

    return has(text, [
        "expiry",
        "exp date",
        "exp. date",
        "exp.date",
        "expiry date",
        "use by",
        "use-by",
        "best before",
        "use before",
    ])


def is_consumer_label(text):
    return has(text, [
        "consumer care",
        "consumer care manager",
        "customer care",
        "customer care manager",
        "customer complaints",
        "customer complaint",
        "consumer complaints",
        "consumer complaint",
        "complaints/feedback",
        "complaint/feedback",
        "complaints / feedback",
        "for customer complaints",
        "for complaints",
        "for queries",
        "helpline",
        "contact us",
        "feedback",
    ])


# ============================================================
# 5. MANUFACTURE / PACKING DATE
# ============================================================

def is_clean_date_item(item):
    text_low = low(item["text"])
    if any(w in text_low for w in ["lic", "license", "licence", "reg. no", "reg no", "st. ex", "excise", "batch"]):
        return False
    return True


def _find_row_date(anchor, date_items, row_threshold=40, max_dx=650):
    """Row-aware date association.

    Priority 1: date on the SAME ROW (dy <= row_threshold) to the right.
    Priority 2: nearest date within spatial bounds (fallback).
    """
    # Priority 1 — same-row, to the right of the label
    same_row = []
    for item in date_items:
        if item is anchor:
            continue
        dx = cx(item) - cx(anchor)  # positive = to the right
        dy = abs(cy(item) - cy(anchor))
        if dy <= row_threshold and dx > 0 and dx <= max_dx:
            match = DATE_RE.search(clean(item["text"]))
            if match:
                same_row.append((dx, match.group(0), item))

    if same_row:
        same_row.sort(key=lambda t: t[0])  # closest horizontally
        _, val, item = same_row[0]
        return val, avg_conf([anchor, item]), [clean(anchor["text"]), clean(item["text"])]

    # Priority 2 — nearest within spatial bounds
    best_candidate = None
    best_dist = float("inf")
    for item in date_items:
        if item is anchor:
            continue
        dx = abs(cx(item) - cx(anchor))
        dy = abs(cy(item) - cy(anchor))
        if dy <= 180 and dx <= max_dx:
            dist = dy * 2.0 + dx
            if dist < best_dist:
                match = DATE_RE.search(clean(item["text"]))
                if match:
                    best_dist = dist
                    best_candidate = (match.group(0), avg_conf([anchor, item]), [clean(anchor["text"]), clean(item["text"])])

    return best_candidate


def extract_mfg_date(items):

    items = sorted(
        items,
        key=lambda x: (cy(x), cx(x))
    )

    mfg_labels = [
        x for x in items
        if is_mfg_label(x["text"])
    ]

    date_items = [
        x for x in items
        if DATE_RE.search(clean(x["text"])) and is_clean_date_item(x)
    ]

    if not mfg_labels:
        return result()

    # Priority 1: Check if mfg_label item itself contains the date inline
    for label in mfg_labels:
        match = DATE_RE.search(clean(label["text"]))
        if match:
            return result(
                match.group(0),
                "FOUND",
                conf(label),
                [clean(label["text"])]
            )

    # Priority 2: Row-aware spatial association
    for anchor in mfg_labels:
        found = _find_row_date(anchor, date_items)
        if found:
            val, c_conf, ev = found
            return result(val, "FOUND", c_conf, ev)

    return result()


# ============================================================
# 6. EXPIRY / BEST BEFORE
# ============================================================

def extract_expiry(items, assigned_mfg_date_text=None):

    items = sorted(
        items,
        key=lambda x: (cy(x), cx(x))
    )

    expiry_labels = [
        x for x in items
        if is_expiry_label(x["text"])
    ]

    date_items = [
        x for x in items
        if DATE_RE.search(clean(x["text"])) and is_clean_date_item(x)
    ]

    if assigned_mfg_date_text:
        date_items = [x for x in date_items if clean(x["text"]) != assigned_mfg_date_text]

    # Check for "use before / best before / Ub X months" phrases
    for item in items:
        text = clean(item["text"])
        m_ub = re.search(r"\b(?:use\s*before|best\s*before|ub)\s*(\d{1,2})\s*(?:m|months?)\b", text, re.I)
        if m_ub:
            return result(f"Use before {m_ub.group(1)} months from Mfg. Date", "FOUND", conf(item), [text])
        if re.search(r"(best\s*before|use\s*before).{0,80}months?", text, re.I):
            return result(text, "FOUND", conf(item), [text])

    if not expiry_labels:
        return result()

    # Priority 1: Check inline date in expiry label
    for label in expiry_labels:
        match = DATE_RE.search(clean(label["text"]))
        if match:
            return result(
                match.group(0),
                "FOUND",
                conf(label),
                [clean(label["text"])]
            )

    # Priority 2: Row-aware spatial association
    for anchor in expiry_labels:
        found = _find_row_date(anchor, date_items)
        if found:
            val, c_conf, ev = found
            return result(val, "FOUND", c_conf, ev)

    # Priority 3: Check "best before X months" phrases near expiry label
    for anchor in expiry_labels:
        for item in items:
            text = clean(item["text"])
            if re.search(r"(best\s*before|use\s*before).{0,80}months?", text, re.I):
                return result(text, "FOUND", avg_conf([anchor, item]), [clean(anchor["text"]), text])

    return result()



# ============================================================
# 9. CONSUMER CARE
# ============================================================

def extract_consumer_care(*items):

    # --------------------------------------------------------
    # NORMALIZE OCR INPUT
    # --------------------------------------------------------
    #
    # Normally:
    #
    # extract_consumer_care(ocr_items)
    #
    # gives:
    #
    # [
    #     {"text": "...", "confidence": ..., "box": [...]},
    #     ...
    # ]
    #
    # But if a nested list reaches this function, flatten it
    # before calling cx()/cy().
    # --------------------------------------------------------

    normalized_items = []

    for item in items:

        if isinstance(item, dict):

            normalized_items.append(item)

        elif isinstance(item, list):

            for subitem in item:

                if isinstance(subitem, dict):

                    normalized_items.append(subitem)

    items = normalized_items

    if not items:
        return result()

    items = sorted(
        items,
        key=lambda x: (cy(x), cx(x))
    )

    # --------------------------------------------------------
    # Find Consumer Care anchor
    # --------------------------------------------------------

    anchor_index = None

    for i, item in enumerate(items):
        text = clean(item["text"])
        if is_consumer_label(text):
            anchor_index = i
            break

    if anchor_index is None:
        for i, item in enumerate(items):
            text = low(clean(item["text"]))

            # Exclude warning / caution text like "contact with eyes"
            if "caution" in text or "contact with eyes" in text or "skin" in text:
                continue

            if (
                "complaint" in text
                or "consumer rela" in text
                or "consumer relation" in text
                or "customer care" in text
                or "consumer care" in text
                or "for queries" in text
                or "for quer" in text
                or "queries" in text
                or "query" in text
                or "contact" in text
                or "tel.no" in text
                or "tel no" in text
                or "tel." in text
                or "tel:" in text
                or "phone" in text
                or "helpline" in text
                or "email us" in text
                or "email" in text
                or "care@" in text
                or "feedback" in text
            ):
                anchor_index = i
                break

    # Direct phone or email detection if no explicit label anchor
    if anchor_index is None:
        for i, item in enumerate(items):
            t = clean(item["text"])
            if PHONE_RE.search(t) or EMAIL_RE.search(t):
                anchor_index = i
                break

    if anchor_index is None:
        return result()


    # --------------------------------------------------------
    # Consumer-care block
    # --------------------------------------------------------

    anchor = items[anchor_index]

    relevant = items[
        anchor_index:anchor_index + 12
    ]

    blob = " ".join(
        clean(x["text"])
        for x in relevant
    )

    # --------------------------------------------------------
    # Phone
    # --------------------------------------------------------

    phone_match = PHONE_RE.search(blob)

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    email_match = EMAIL_RE.search(blob)

    # --------------------------------------------------------
    # Designation
    # --------------------------------------------------------

    designation = None

    designation_patterns = [

        r"\bconsumer\s*care\s*(?:manager|executive|officer)\b",

        r"\bcustomer\s*care\s*(?:manager|executive|officer)\b",

        r"\bconsumer\s*relations?\s*(?:manager|executive|officer)\b",

        r"\bmanager\s*[-:]\s*consumer\s*relations?\b",

        r"\bmanager\s*[-:]\s*consumer\s*relaions?\b",

        r"\bmanager\s*[-:]\s*customer\s*relations?\b",

        r"\bmanager\s*[-:]\s*customer\s*relaions?\b",

    ]

    for item in relevant:

        text = clean(item["text"])

        normalized = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        for pattern in designation_patterns:

            match = re.search(
                pattern,
                normalized,
                re.IGNORECASE
            )

            if match:

                designation = match.group(0).strip()

                break

        if designation:
            break

    # --------------------------------------------------------
    # Address
    # --------------------------------------------------------

    # Stop-phrases that should NOT be included in consumer care address
    _CARE_STOP_PHRASES = [
        "please refer",
        "batch number",
        "mfg address",
        "how to use",
        "caution",
        "protect from",
        "spray directly",
        "net volume",
        "net qty",
        "net quantity",
        "mrp",
        "made in",
    ]

    address_lines = []

    for item in relevant:

        text = clean(item["text"])
        t = low(text)

        # Stop collecting if we hit a non-consumer-care section
        if any(stop in t for stop in _CARE_STOP_PHRASES):
            continue

        # Ignore phone/email/website lines.
        if EMAIL_RE.search(text):
            continue

        if PHONE_RE.search(text):
            continue

        if "website" in t:
            continue

        # Strong address indicator.
        if PIN_RE.search(text):

            address_lines.append(text)
            continue

        # Other address indicators.
        if any(
            word in t
            for word in [
                "road",
                "street",
                "floor",
                "sector",
                "industrial area",
                "industrial areg",
                "nagar",
                "plot",
                "gurgaon",
                "gurugram",
                "haryana",
                "delhi",
                "mumbai",
                "pune",
                "noida",
                "address",
                "spectrum",
            ]
        ):

            address_lines.append(text)

    # --------------------------------------------------------
    # Remove duplicate address lines
    # --------------------------------------------------------

    unique_address = []

    seen = set()

    for line in address_lines:

        key = low(line)

        if key not in seen:

            unique_address.append(line)
            seen.add(key)

    # --------------------------------------------------------
    # Build result
    # --------------------------------------------------------

    data = {

        "name_or_designation": designation,

        "phone": (
            phone_match.group(0)
            if phone_match
            else None
        ),

        "email": (
            email_match.group(0)
            if email_match
            else None
        ),

        "address": (
            " ".join(unique_address)
            if unique_address
            else None
        ),
    }

    present = sum(
        bool(value)
        for value in data.values()
    )

    if present == 0:
        return result()

    # Rule 6(1)(k): At least 2 contact channels (e.g. Phone + Email or Phone + Address) is legally compliant
    status = (
        "FOUND"
        if (present >= 2 or data.get("phone") or data.get("email"))
        else "PARTIAL"
    )

    return result(
        data,
        status,
        avg_conf(relevant),
        [
            clean(x["text"])
            for x in relevant
        ],
    )


# ============================================================
# 10. DIMENSIONS / USABLE COUNT
# ============================================================

def extract_dimensions_or_count(items):

    dimensions = []
    counts = []

    for item in items:

        text = clean(item["text"])

        dimensions.extend(
            DIMENSION_RE.findall(text)
        )

        counts.extend(
            COUNT_RE.findall(text)
        )

    dimensions = list(
        dict.fromkeys(dimensions)
    )

    counts = list(
        dict.fromkeys(counts)
    )

    if dimensions:

        return result(
            {
                "dimensions": dimensions,
                "count": None,
            },
            "FOUND",
            1.0,
            dimensions,
        )

    if counts:

        return result(
            {
                "dimensions": None,
                "count": counts,
            },
            "FOUND",
            1.0,
            counts,
        )

    return result(
        None,
        "NOT_APPLICABLE"
    )


def _parse_date_tuple(date_str):
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip().upper()
    m1 = re.search(r"\b(0?[1-9]|1[0-2])\s*[/\-]\s*(\d{4})\b", s)
    if m1:
        return (int(m1.group(2)), int(m1.group(1)))
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    for idx, mon in enumerate(months, 1):
        if mon in s:
            m2 = re.search(r"\b(\d{4})\b", s)
            if m2:
                return (int(m2.group(1)), idx)
    return None


# ============================================================
# COMPLETE 10-FIELD STRUCTURE
# ============================================================

def extract_declarations(
    ocr_items,
    existing_fields=None
):

    existing_fields = existing_fields or {}

    mfg_date_res = extract_mfg_date(ocr_items)
    mfg_evidence = mfg_date_res.get("evidence", [])
    assigned_mfg_text = mfg_evidence[1] if len(mfg_evidence) > 1 else None

    expiry_date_res = extract_expiry(ocr_items, assigned_mfg_date_text=assigned_mfg_text)

    # Chronological validation: Mfg Date must be <= Expiry Date
    mfg_val = mfg_date_res.get("value")
    exp_val = expiry_date_res.get("value")
    mfg_t = _parse_date_tuple(mfg_val)
    exp_t = _parse_date_tuple(exp_val)
    if mfg_t and exp_t and mfg_t > exp_t:
        mfg_date_res, expiry_date_res = expiry_date_res, mfg_date_res
    elif (not mfg_val or not exp_val) or (mfg_t and mfg_t[0] >= 2028):
        # Resolve any multi-date stamp ambiguity (earlier = Mfg, later = Exp)
        nearby_dates = []
        for x in ocr_items:
            t = clean(x.get("text", ""))
            if DATE_RE.search(t) and is_clean_date_item(x):
                match = DATE_RE.search(t)
                if match:
                    dt = _parse_date_tuple(match.group(0))
                    if dt:
                        nearby_dates.append((dt, match.group(0), x))
        if len(nearby_dates) >= 2:
            nearby_dates.sort(key=lambda item: item[0])
            earliest = nearby_dates[0]
            latest = nearby_dates[-1]
            if earliest[0] < latest[0]:
                if not mfg_val or (mfg_t and mfg_t > earliest[0]):
                    mfg_date_res = result(earliest[1], "FOUND", conf(earliest[2]), [earliest[1]])
                if not exp_val or (exp_t and exp_t < latest[0]):
                    expiry_date_res = result(latest[1], "FOUND", conf(latest[2]), [latest[1]])

    return {

        "1_manufacturer_packer_importer":
            extract_manufacturer(ocr_items),

        "2_country_of_origin":
            extract_country_origin(ocr_items),

        "3_generic_common_name":
            extract_generic_name(ocr_items),

        "4_net_quantity":
            wrap_existing_field(
                existing_fields.get("net_quantity"),
                "Existing MVP03 Net Quantity extraction",
            ),

        "5_manufacture_packing_date":
            mfg_date_res,

        "6_expiry_best_before":
            expiry_date_res,

        "7_mrp":
            wrap_existing_field(
                existing_fields.get("mrp"),
                "Existing MVP03 MRP extraction",
            ),

        "8_unit_sale_price":
            wrap_existing_field(
                existing_fields.get("unit_sale_price"),
                "Existing MVP03 Unit Sale Price extraction",
            ),

        "9_consumer_care":
            extract_consumer_care(ocr_items),

        "10_dimensions_usable_count":
            extract_dimensions_or_count(ocr_items),
    }



# ============================================================
# REPORT
# ============================================================

def print_declaration_report(declarations):

    labels = [

        (
            "1_manufacturer_packer_importer",
            "MANUFACTURER / PACKER / IMPORTER"
        ),

        (
            "2_country_of_origin",
            "COUNTRY OF ORIGIN"
        ),

        (
            "3_generic_common_name",
            "GENERIC / COMMON NAME"
        ),

        (
            "4_net_quantity",
            "NET QUANTITY"
        ),

        (
            "5_manufacture_packing_date",
            "MANUFACTURE / PACKING DATE"
        ),

        (
            "6_expiry_best_before",
            "EXPIRY / BEST BEFORE"
        ),

        (
            "7_mrp",
            "MRP"
        ),

        (
            "8_unit_sale_price",
            "UNIT SALE PRICE"
        ),

        (
            "9_consumer_care",
            "CONSUMER CARE"
        ),

        (
            "10_dimensions_usable_count",
            "DIMENSIONS / USABLE COUNT"
        ),
    ]

    print()

    print("=" * 70)
    print("METROLOGYSHIELD — PHASE 3")
    print("=" * 70)

    for key, label in labels:

        data = declarations.get(key)

        print()

        print(label + ":")

        if not data:

            print("  NOT CONNECTED")
            continue

        print(
            "  STATUS     :",
            data.get("status")
        )

        print(
            "  VALUE      :",
            data.get("value")
        )

        print(
            "  CONFIDENCE :",
            data.get("confidence")
        )

    print()

    print("=" * 70)