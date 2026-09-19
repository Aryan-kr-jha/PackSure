"""Pre-seed verified demo results for test packages into the persistent result cache.

This script:
1. Locates the actual physical image files for:
   - test_package_3.jpg (Face Wash - 100% compliant)
   - test_package_4.jpg (NIGHT EDP - 100% compliant)
   - test_package_7.jpg (Asus Monitor - 87% compliant)
2. Reads their real bytes and calculates their full SHA-256 hashes automatically.
3. Obtains their existing authentic verified results (from demo_cache / verified analysis).
4. Seeds them directly through the normal save_cached_analysis() mechanism.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Ensure Backend directory is on sys.path
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.demo_cache import _build_test_package_3_result, _build_test_package_4_result
from services.result_cache import calculate_image_hash, get_cached_analysis, save_cached_analysis


def find_image_file(filename: str) -> Path | None:
    """Locate the image file in the project's data folders."""
    candidates = [
        PROJECT_ROOT / "data" / "Good Image" / filename,
        PROJECT_ROOT / "data" / "Sample Image" / filename,
        PROJECT_ROOT / "data" / "Sample_data" / filename,
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def get_verified_analysis_7() -> dict:
    """Load authentic analysis generated for test_package_7.jpg."""
    json_path = BACKEND_DIR / "test_package_7_analysis.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Missing verified analysis file: {json_path}")
    return json.loads(json_path.read_text(encoding="utf-8"))


def seed_all_demo_packages() -> dict[str, str]:
    """Calculate real SHA-256 hashes and save verified results into persistent cache."""
    seeded_hashes: dict[str, str] = {}

    packages = [
        ("test_package_3.jpg", _build_test_package_3_result),
        ("test_package_4.jpg", _build_test_package_4_result),
        ("test_package_7.jpg", get_verified_analysis_7),
    ]

    for filename, result_builder in packages:
        img_path = find_image_file(filename)
        if not img_path:
            raise FileNotFoundError(f"Could not locate image file for {filename}")

        img_bytes = img_path.read_bytes()
        calculated_hash = calculate_image_hash(img_bytes)

        payload = result_builder()
        ocr_items = payload.get("ocr_items", [])
        analysis = payload.get("analysis", {})

        saved = save_cached_analysis(
            img_bytes,
            ocr_items,
            analysis,
            metadata={"source": "seed_demo_cache", "filename": filename},
        )
        if not saved:
            raise RuntimeError(f"Failed to seed cache for {filename}")

        # Verification check: immediately look up the entry
        verified = get_cached_analysis(img_bytes)
        if not verified:
            raise RuntimeError(f"Verification lookup failed after seeding {filename}")

        seeded_hashes[filename] = calculated_hash
        print(f"[SEEDED] {filename} -> {calculated_hash}")

    return seeded_hashes


if __name__ == "__main__":
    hashes = seed_all_demo_packages()
    print(f"Successfully seeded {len(hashes)} demo packages into persistent cache.")
