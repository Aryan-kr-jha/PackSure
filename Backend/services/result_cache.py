"""Persistent SHA-256 Result Cache for PackSure Package Analysis.

This module provides deterministic exact-image result caching:
1. Calculates SHA-256 hash of actual uploaded image bytes (never filenames).
2. Performs fast cache lookup before running OCR/extraction/compliance.
3. On Cache Hit: returns verified structured analysis immediately.
4. On Cache Miss: allows normal OCR pipeline to run and then saves the result.
5. In case of ANY cache error or storage failure, gracefully returns None / logs
   and never blocks the scanning pipeline.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"
RULES_VERSION = "2011.PCR"

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
UPLOADS_DIR = BACKEND_DIR / "uploads"
CACHE_FILE_PATH = UPLOADS_DIR / ".result_cache.json"

_CACHE_LOCK = Lock()
_MEMORY_CACHE: dict[str, dict[str, Any]] = {}
_INITIALIZED = False


def _ensure_cache_loaded() -> None:
    """Load persistent disk cache into memory once at startup."""
    global _INITIALIZED, _MEMORY_CACHE
    if _INITIALIZED:
        return

    with _CACHE_LOCK:
        if _INITIALIZED:
            return
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        if CACHE_FILE_PATH.exists():
            try:
                raw_text = CACHE_FILE_PATH.read_text(encoding="utf-8")
                if raw_text.strip():
                    loaded = json.loads(raw_text)
                    if isinstance(loaded, dict):
                        _MEMORY_CACHE = loaded
                        logger.info(f"[CACHE] Loaded {len(_MEMORY_CACHE)} cached results from disk.")
            except Exception as err:
                logger.warning(f"[CACHE] Failed to load disk cache: {err}")
        _INITIALIZED = True


def _save_cache_to_disk() -> None:
    """Save in-memory cache to atomic JSON file on disk."""
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = CACHE_FILE_PATH.with_suffix(".tmp")
        temp_file.write_text(json.dumps(_MEMORY_CACHE, indent=2, default=str), encoding="utf-8")
        temp_file.replace(CACHE_FILE_PATH)
    except Exception as err:
        logger.warning(f"[CACHE] Save failed: {err}")


def calculate_image_hash(image_bytes: bytes) -> str:
    """Generate deterministic SHA-256 hex digest from raw image bytes."""
    return hashlib.sha256(image_bytes).hexdigest()


def get_cached_analysis(image_bytes: bytes) -> dict[str, Any] | None:
    """Lookup cached analysis by raw image SHA-256 hash.

    Validates that the pipeline_version and rules_version match current system versions.
    Returns deep copy of cached record with 'ocr_items' and 'analysis' structure, or None.
    """
    if not image_bytes:
        return None

    try:
        _ensure_cache_loaded()
        image_hash = calculate_image_hash(image_bytes)

        with _CACHE_LOCK:
            entry = _MEMORY_CACHE.get(image_hash)

        if not entry:
            return None

        # Version safety check: invalidate stale versions
        cached_pipe = entry.get("pipeline_version")
        cached_rules = entry.get("rules_version")
        if cached_pipe != PIPELINE_VERSION or cached_rules != RULES_VERSION:
            logger.info(
                f"[CACHE] Stale version for hash {image_hash[:12]} "
                f"(pipe: {cached_pipe} vs {PIPELINE_VERSION}, rules: {cached_rules} vs {RULES_VERSION}). Re-evaluating."
            )
            return None

        result_payload = entry.get("result")
        if not result_payload or "analysis" not in result_payload:
            return None

        return copy.deepcopy(result_payload)
    except Exception as err:
        logger.error(f"[CACHE] Lookup failed: {err}")
        return None


def save_cached_analysis(
    image_bytes: bytes,
    ocr_items: list[dict[str, Any]],
    analysis: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Save an analysis result to the persistent cache indexed by image SHA-256 hash."""
    if not image_bytes or not analysis:
        return False

    try:
        _ensure_cache_loaded()
        image_hash = calculate_image_hash(image_bytes)

        record: dict[str, Any] = {
            "image_hash": image_hash,
            "pipeline_version": PIPELINE_VERSION,
            "rules_version": RULES_VERSION,
            "metadata": metadata or {},
            "result": {
                "ocr_items": ocr_items,
                "analysis": analysis,
            },
        }

        with _CACHE_LOCK:
            _MEMORY_CACHE[image_hash] = record
            _save_cache_to_disk()

        logger.info(f"[CACHE] Result saved for hash {image_hash[:12]}...")
        return True
    except Exception as err:
        logger.error(f"[CACHE] Save failed: {err}")
        return False


def get_cache_stats() -> dict[str, Any]:
    """Return cache health & statistics."""
    _ensure_cache_loaded()
    with _CACHE_LOCK:
        return {
            "total_cached_entries": len(_MEMORY_CACHE),
            "pipeline_version": PIPELINE_VERSION,
            "rules_version": RULES_VERSION,
            "hashes": list(_MEMORY_CACHE.keys()),
        }
