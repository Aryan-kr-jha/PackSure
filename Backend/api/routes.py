"""HTTP API for package compliance analysis and inspector history."""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from core.config import settings
from db.repository import repository
from ocr.ocr_engine import run_ocr
from reports.pdf import build_scan_report
from services.analyzer import analyze_package
from services.demo_cache import get_demo_result
from services.digital_compliance import analyze_digital_product_url

from services.result_cache import (
    calculate_image_hash,
    get_cached_analysis,
    save_cached_analysis,
)

logger = logging.getLogger(__name__)

class UrlScanRequest(BaseModel):
    url: str


router = APIRouter()
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg"}
_ALLOWED_SUFFIXES = {".jpg", ".jpeg"}


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "database": "supabase" if settings.supabase_enabled else "unconfigured",
    }


@router.post("/api/scan")
async def scan_package(file: UploadFile = File(...)) -> dict[str, Any]:
    original_filename = file.filename or "upload.jpg"
    logger.info(f"[SCAN] Image received: {original_filename}")
    suffix = Path(original_filename).suffix.lower()
    if (
        file.content_type not in _ALLOWED_CONTENT_TYPES
        or suffix not in _ALLOWED_SUFFIXES
    ):
        raise HTTPException(400, "Only JPG/JPEG images are allowed")
    contents = await file.read()
    if (
        not contents
        or len(contents) > settings.max_upload_bytes
        or not contents.startswith(b"\xff\xd8\xff")
    ):
        raise HTTPException(
            400, "Uploaded file is not a valid JPEG image or exceeds the size limit"
        )

    image_hash = calculate_image_hash(contents)
    logger.info(f"[HASH] Generated image hash: {image_hash[:12]}...")

    stored_filename = f"{uuid4().hex}{suffix}"
    image_path = settings.upload_dir / stored_filename
    image_path.write_bytes(contents)

    ocr_items = None
    analysis = None
    is_cached_hit = False

    # 1. Lookup in persistent exact-image result cache
    try:
        cached_result = get_cached_analysis(contents)
        if cached_result is not None:
            logger.info(f"[CACHE] Cache hit for hash {image_hash[:12]}...")
            ocr_items = cached_result.get("ocr_items", [])
            analysis = cached_result.get("analysis", {})
            is_cached_hit = True
    except Exception as err:
        logger.error(f"[CACHE] Lookup failed: {err}")

    # Fallback to existing verified demo cache if not in persistent cache yet
    if not is_cached_hit:
        try:
            demo_result = get_demo_result(contents, original_filename)
            if demo_result is not None:
                logger.info(f"[CACHE] Cache hit (demo provider) for hash {image_hash[:12]}...")
                ocr_items = demo_result["ocr_items"]
                analysis = demo_result["analysis"]
                is_cached_hit = True
                # Populate persistent cache for subsequent requests
                try:
                    save_cached_analysis(contents, ocr_items, analysis, metadata={"filename": original_filename})
                except Exception as save_err:
                    logger.error(f"[CACHE] Save failed: {save_err}")
        except Exception as err:
            logger.error(f"[CACHE] Demo lookup failed: {err}")

    # 2. On Cache MISS: Execute existing OCR -> Extraction -> Compliance pipeline
    if not is_cached_hit or analysis is None:
        logger.info(f"[CACHE] Cache miss for hash {image_hash[:12]}...")
        logger.info("[OCR] Starting OCR pipeline")
        try:
            ocr_items = run_ocr(image_path)
            logger.info(f"[OCR] Completed: extracted {len(ocr_items)} tokens")
            analysis = analyze_package(ocr_items, image_path=image_path)
        except FileNotFoundError as error:
            raise HTTPException(400, "Uploaded image could not be read") from error
        except (RuntimeError, ValueError) as error:
            raise HTTPException(422, "Image analysis failed") from error
        except Exception as error:
            logger.exception("Unexpected error during package scan")
            raise HTTPException(
                status_code=500,
                detail=f"{type(error).__name__}: {error}",
            ) from error

        # 3. Save newly verified result to persistent cache
        try:
            save_cached_analysis(contents, ocr_items, analysis, metadata={"filename": original_filename})
            logger.info(f"[CACHE] Result saved for hash {image_hash[:12]}...")
        except Exception as err:
            logger.error(f"[CACHE] Save failed: {err}")

    # 4. Record scan into repository for inspector history
    scan = repository.create(
        filename=original_filename,
        image_url=f"/uploads/{stored_filename}",
        ocr=ocr_items or [],
        fields=analysis["fields"],
        declarations=analysis["declarations"],
        compliance=analysis["compliance"],
    )

    return {
        "status": "success",
        "scan": scan,
        "analysis": analysis,
        "cached": is_cached_hit,
    }


@router.post("/api/scan-url")
def scan_product_url(body: UrlScanRequest) -> dict[str, Any]:
    """Scrapes e-commerce product URL and checks Legal Metrology E-Commerce Compliance."""
    if not body.url or not body.url.startswith(("http://", "https://")):
        raise HTTPException(400, "A valid HTTP/HTTPS URL must be provided")
    result = analyze_digital_product_url(body.url)
    return result


@router.get("/api/scans")

def list_scans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
) -> dict[str, Any]:
    return repository.list(page=page, page_size=page_size, status=status)


@router.get("/api/scans/{scan_id}")
def get_scan(scan_id: str) -> dict[str, Any]:
    scan = repository.get(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


@router.api_route("/api/reports/pdf", methods=["GET", "POST"])
def report_pdf(scan_id: str = Query(...)) -> Response:
    scan = repository.get(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return Response(
        build_scan_report(scan),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="packsure-{scan_id}.pdf"'
        },
    )


@router.get("/api/analytics/dashboard")
def dashboard() -> dict[str, Any]:
    return repository.analytics()
