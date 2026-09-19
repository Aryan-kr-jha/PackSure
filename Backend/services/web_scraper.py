"""Production-safe e-commerce listing scraper for Legal Metrology checks.

Design goals:
- Prefer structured page data, but never mistake an online sale price for MRP.
- Be resilient to Amazon/Shopify/other common HTML layouts.
- Download several distinct product/packaging images for OCR.
- Never fail the complete scan because one image or one parser failed.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from core.config import settings

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MRP_LABEL_RE = re.compile(
    r"(?:maximum\s+retail\s+price|m\.?r\.?p\.?)", re.I
)
QTY_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(kg|kgs|g|gm|gms|mg|l|ltr|litre|litres|ml|"
    r"unit|units|pc|pcs|piece|pieces|count|n)\b",
    re.I,
)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+91[\s-]?)?(?:0?1800[\s-]?\d{3,4}[\s-]?\d{3,4}|"
    r"[6-9]\d{9})(?!\d)"
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)


def _valid_public_http_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False, "Only HTTP/HTTPS URLs are supported."
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"}:
            return False, "Local/private URLs are not allowed."
        try:
            infos = socket.getaddrinfo(host, None)
            for info in infos:
                addr = ipaddress.ip_address(info[4][0])
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    return False, "Private/local network URLs are not allowed."
        except socket.gaierror:
            return False, "Product host could not be resolved."
        return True, ""
    except Exception:
        return False, "Invalid URL."


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(?<!\d)(\d+(?:,\d{3})*(?:\.\d+)?)(?!\d)", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _normalise_image_url(url: str, base_url: str) -> Optional[str]:
    if not url:
        return None
    url = urljoin(base_url, url.strip())
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _iter_json_objects(data: Any):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _iter_json_objects(value)
    elif isinstance(data, list):
        for value in data:
            yield from _iter_json_objects(value)


def _find_product_jsonld(soup: BeautifulSoup) -> Dict[str, Any]:
    best: Dict[str, Any] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        content = script.string or script.get_text()
        if not content:
            continue
        try:
            data = json.loads(content)
        except Exception:
            continue
        for obj in _iter_json_objects(data):
            typ = obj.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if any(str(t).lower() in {"product", "individualproduct"} for t in types):
                if not best:
                    best = obj
                # Prefer the object with an actual name/image/offers.
                if obj.get("name") and (obj.get("image") or obj.get("offers")):
                    return obj
    return best


def _extract_title(soup: BeautifulSoup, json_ld: Dict[str, Any]) -> Optional[str]:
    candidates = [
        soup.find(id="productTitle"),
        soup.find("h1"),
        soup.find("meta", property="og:title"),
    ]
    for elem in candidates:
        if not elem:
            continue
        value = elem.get("content") if elem.name == "meta" else elem.get_text(" ", strip=True)
        value = _clean_text(value)
        if value:
            return value
    return _clean_text(json_ld.get("name")) or (_clean_text(soup.title.get_text()) if soup.title else None)


def _extract_specs(soup: BeautifulSoup) -> Dict[str, str]:
    specs: Dict[str, str] = {}

    selectors = [
        "#detailBullets_feature_div li",
        "#productDetails_db_sections tr",
        "#productDetails_techSpec_section_1 tr",
        ".prodDetTable tr",
        "table.a-keyvalue tr",
        "[class*='specification'] tr",
        "[class*='specs'] tr",
        "dl",
    ]
    for elem in soup.select(", ".join(selectors)):
        if elem.name == "dl":
            dts = elem.find_all("dt")
            dds = elem.find_all("dd")
            for dt, dd in zip(dts, dds):
                k, v = _clean_text(dt.get_text(" ", strip=True)), _clean_text(dd.get_text(" ", strip=True))
                if k and v:
                    specs[re.sub(r"[^a-z0-9 ]", "", k.lower()).strip()] = v
            continue

        cells = elem.find_all(["th", "td"])
        if len(cells) >= 2:
            k = _clean_text(cells[0].get_text(" ", strip=True))
            v = _clean_text(cells[1].get_text(" ", strip=True))
            if k and v:
                specs[re.sub(r"[^a-z0-9 ]", "", k.lower()).strip()] = v
        else:
            text = _clean_text(elem.get_text(" ", strip=True))
            if ":" in text:
                k, v = [x.strip() for x in text.split(":", 1)]
                if k and v:
                    specs[re.sub(r"[^a-z0-9 ]", "", k.lower()).strip()] = v

    return specs


def _first_spec(specs: Dict[str, str], *terms: str) -> Optional[str]:
    for key, value in specs.items():
        if any(term in key for term in terms):
            return value
    return None


def _extract_explicit_mrp(text: str) -> Optional[float]:
    # Only accept a number close to an explicit MRP label. This intentionally
    # does NOT treat JSON-LD offers.price as MRP because that is usually sale price.
    patterns = [
        r"(?:maximum\s+retail\s+price|m\.?\s*r\.?\s*p\.?)"
        r"\s*(?:\([^)]*\))?\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*"
        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:mrp)\s*(?:inclusive[^₹\d]{0,30})?(?:₹|rs\.?|inr)?\s*"
        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return _as_float(m.group(1))
    return None


def _extract_country(text: str) -> Optional[str]:
    patterns = [
        r"country\s+of\s+origin\s*[:\-]\s*([A-Za-z][A-Za-z .&'-]{2,40}?)(?=<|[\r\n]|$)",
        r"\bmade\s+in\s+([A-Za-z][A-Za-z .&'-]{2,30}?)(?=<|[\r\n]|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = _clean_text(m.group(1))
            value = re.split(r"\b(?:for|manufacturer|importer|generic|mrp|net quantity)\b", value, flags=re.I)[0]
            return value.strip(" .,:;-") or None
    return None


def _extract_manufacturer(text: str) -> Optional[str]:
    patterns = [
        r"(?:manufacturer|manufactured\s+by|mfd\.?\s+by|packer)\s*[:\-]\s*"
        r"([A-Za-z0-9][A-Za-z0-9 &.,'()/\-]{2,140}?)(?=<|[\r\n]|$)",
        r"(?:imported\s+and\s+marketed\s+by|marketed\s+by)\s*[:\-]?\s*"
        r"([A-Za-z0-9][A-Za-z0-9 &.,'()/\-]{2,140}?)(?=<|[\r\n]|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return _clean_text(m.group(1)).strip(" .,:;-") or None
    return None


def _extract_consumer_care(text: str) -> Optional[Dict[str, Any]]:
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    if not emails and not phones:
        return None
    return {
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
    }


def parse_text_declarations(
    soup: BeautifulSoup,
    json_ld: Dict[str, Any],
    title: Optional[str],
    description: str,
    raw_html: str,
) -> Dict[str, Any]:
    text = _clean_text(soup.get_text(" ", strip=True))
    specs = _extract_specs(soup)

    declarations: Dict[str, Any] = {
        "mrp": None,
        "net_quantity": None,
        "country_of_origin": None,
        "manufacturer": None,
        "importer": None,
        "consumer_care": None,
        "expiry_date": None,
        "generic_name": None,
        "sale_price": None,
    }

    declarations["generic_name"] = (
        _first_spec(specs, "generic name", "generic product name", "common name", "product type")
        or _clean_text(json_ld.get("category"))
        or None
    )

    declarations["country_of_origin"] = (
        _first_spec(specs, "country of origin", "country origin")
        or _extract_country(text)
    )

    declarations["manufacturer"] = (
        _first_spec(specs, "manufacturer", "manufactured by", "manufactured")
        or _extract_manufacturer(text)
    )

    declarations["importer"] = _first_spec(
        specs, "importer", "imported and marketed by", "imported by", "marketed by"
    )

    declarations["net_quantity"] = _first_spec(
        specs, "net quantity", "net qty", "net weight", "net volume",
        "item weight", "quantity"
    )
    if not declarations["net_quantity"]:
        # Restrict title fallback to an explicit quantity-like token.
        m = QTY_RE.search(title or "")
        if m:
            declarations["net_quantity"] = m.group(0)

    # Explicit MRP only. Never use offers.price as MRP.
    declarations["mrp"] = _extract_explicit_mrp(text)

    # Some retailer pages expose a labelled "MRP" in an attribute/spec value.
    if declarations["mrp"] is None:
        for key, value in specs.items():
            if "mrp" in key or "maximum retail price" in key:
                declarations["mrp"] = _as_float(value)
                if declarations["mrp"] is not None:
                    break

    # JSON-LD offer price is sale/current price, not statutory MRP.
    offers = json_ld.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict):
        declarations["sale_price"] = _as_float(offers.get("price"))

    if not declarations["consumer_care"]:
        declarations["consumer_care"] = _extract_consumer_care(text)

    # Expiry/best-before is useful when explicitly present.
    expiry_match = re.search(
        r"(?:expiry|best\s*before|use\s*before)\s*[:\-]?\s*"
        r"([A-Za-z0-9 ./,\-]{3,80})",
        text,
        re.I,
    )
    if expiry_match:
        declarations["expiry_date"] = _clean_text(expiry_match.group(1))

    return declarations


def extract_image_urls(
    soup: BeautifulSoup,
    json_ld: Dict[str, Any],
    raw_html: str,
    base_url: str,
) -> List[str]:
    urls: List[str] = []

    def add(value: Any):
        if isinstance(value, str):
            u = _normalise_image_url(value, base_url)
            if u:
                urls.append(u)
        elif isinstance(value, list):
            for x in value:
                add(x)

    add(json_ld.get("image"))

    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in {"og:image", "twitter:image"}:
            add(meta.get("content"))

    for img in soup.find_all("img"):
        for attr in ("data-old-hires", "data-src", "data-lazy-src", "src"):
            add(img.get(attr))
        srcset = img.get("srcset")
        if srcset:
            for part in srcset.split(","):
                add(part.strip().split(" ")[0])

    # Common Amazon embedded image JSON.
    for pattern in (
        r'"hiRes"\s*:\s*"([^"]+)"',
        r'"large"\s*:\s*"([^"]+)"',
        r'"landingImageUrl"\s*:\s*"([^"]+)"',
    ):
        for match in re.findall(pattern, raw_html):
            add(match)

    clean: List[str] = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            clean.append(u)
    return clean[:8]


def download_product_images(urls: List[str], referer_url: str) -> List[str]:
    downloaded: List[str] = []
    headers = {**BROWSER_HEADERS, "Referer": referer_url}

    for url in urls[:5]:
        try:
            with httpx.Client(headers=headers, timeout=12.0, follow_redirects=True) as client:
                res = client.get(url)
                if res.status_code != 200 or len(res.content) < 5000:
                    continue
                content_type = (res.headers.get("content-type") or "").lower()
                if not (content_type.startswith("image/") or urlparse(url).path.lower().endswith(IMAGE_EXTENSIONS)):
                    continue
                suffix = ".jpg"
                if "png" in content_type:
                    suffix = ".png"
                elif "webp" in content_type:
                    suffix = ".webp"
                filename = f"digital_product_{uuid.uuid4().hex[:10]}{suffix}"
                filepath = settings.upload_dir / filename
                filepath.write_bytes(res.content)
                downloaded.append(str(filepath))
        except Exception as exc:
            logger.warning("Could not download product image %s: %s", url, exc)

    return downloaded


def scrape_product_url(url: str) -> Dict[str, Any]:
    """Fetch a product page, extract listing declarations, and collect images."""
    ok, error = _valid_public_http_url(url)
    if not ok:
        return {
            "success": False, "url": url, "error": error,
            "title": None, "description": None,
            "extracted_declarations": {}, "image_urls": [], "image_paths": [],
        }

    try:
        with httpx.Client(
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(20.0, connect=8.0),
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "html" not in content_type:
                return {
                    "success": False, "url": url,
                    "error": "URL did not return an HTML product page.",
                    "title": None, "description": None,
                    "extracted_declarations": {}, "image_urls": [], "image_paths": [],
                }
            html = response.text
    except Exception as exc:
        return {
            "success": False, "url": url,
            "error": f"Failed to fetch page: {exc}",
            "title": None, "description": None,
            "extracted_declarations": {}, "image_urls": [], "image_paths": [],
        }

    soup = BeautifulSoup(html, "html.parser")
    json_ld = _find_product_jsonld(soup)
    title = _extract_title(soup, json_ld)

    meta_desc = (
        soup.find("meta", attrs={"name": "description"})
        or soup.find("meta", property="og:description")
    )
    description = _clean_text(meta_desc.get("content")) if meta_desc else ""

    declarations = parse_text_declarations(
        soup, json_ld, title, description, html
    )
    image_urls = extract_image_urls(soup, json_ld, html, url)
    image_paths = download_product_images(image_urls, url)

    return {
        "success": True,
        "url": url,
        "title": title or "Digital Product Listing",
        "description": description,
        "extracted_declarations": declarations,
        "image_urls": image_urls,
        "image_paths": image_paths,
        "json_ld": json_ld,
        "http_status": response.status_code,
        "final_url": str(response.url),
    }
