from __future__ import annotations

from datetime import datetime, timezone
import logging
from threading import Lock
from typing import Any
from uuid import uuid4

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class ScanRepository:
    def __init__(self) -> None:
        self._memory: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._supabase_failed = False

    def _request(self, method: str, table: str, *, params: dict[str, Any] | None = None, payload: Any = None) -> list[dict[str, Any]]:
        if not settings.supabase_enabled or self._supabase_failed:
            raise RuntimeError("Supabase is disabled or unavailable")
        headers = {
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        response = httpx.request(
            method,
            f"{settings.supabase_url}/rest/v1/{table}",
            headers=headers,
            params=params,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return response.json() if response.content else []

    def create(
        self,
        *,
        filename: str,
        image_url: str | None,
        ocr: list[dict[str, Any]],
        fields: dict[str, Any],
        declarations: dict[str, Any],
        compliance: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": str(uuid4()),
            "filename": filename,
            "image_url": image_url,
            "raw_ocr_json": ocr,
            "extracted_fields_json": {"fields": fields, "declarations": declarations},
            "compliance_score": compliance["score"],
            "compliance_status": compliance["status"],
            "created_at": now,
            "violations": compliance.get("violations", []),
            "declarations": declarations,
            "fields": fields,
            "ocr": ocr,
        }

        if settings.supabase_enabled and not self._supabase_failed:
            try:
                base = {k: v for k, v in record.items() if k not in ("violations", "declarations", "fields", "ocr")}
                saved = self._request("POST", "scans", payload=base)[0]
                scan_id = saved.get("id", record["id"])
                for violation in compliance.get("violations", []):
                    self._request(
                        "POST",
                        "violations",
                        payload={
                            "scan_id": scan_id,
                            **{k: violation.get(k) for k in ("rule_code", "description", "severity", "clause")},
                        },
                    )
                with self._lock:
                    self._memory[record["id"]] = record
                return {**record, **saved, "violations": compliance.get("violations", [])}
            except Exception as err:
                self._supabase_failed = True
                logger.warning(f"Supabase persistence error (falling back to memory): {err}")

        with self._lock:
            self._memory[record["id"]] = record
        return record

    def list(self, *, page: int = 1, page_size: int = 20, status: str | None = None) -> dict[str, Any]:
        offset = max(page - 1, 0) * page_size
        if settings.supabase_enabled and not self._supabase_failed:
            try:
                params: dict[str, Any] = {
                    "select": "*",
                    "order": "created_at.desc",
                    "offset": offset,
                    "limit": page_size,
                }
                if status:
                    params["compliance_status"] = f"eq.{status.upper()}"
                rows = self._request("GET", "scans", params=params)
                if rows or not self._memory:
                    return {"items": rows, "page": page, "page_size": page_size, "total": len(rows)}
            except Exception as err:
                self._supabase_failed = True
                logger.warning(f"Supabase list error (falling back to memory): {err}")

        rows = list(self._memory.values())
        if status:
            rows = [r for r in rows if r.get("compliance_status") == status.upper()]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return {"items": rows[offset : offset + page_size], "page": page, "page_size": page_size, "total": len(rows)}

    def get(self, scan_id: str) -> dict[str, Any] | None:
        rec = None
        if settings.supabase_enabled:
            try:
                rows = self._request("GET", "scans", params={"id": f"eq.{scan_id}", "select": "*"})
                if rows:
                    violations = self._request("GET", "violations", params={"scan_id": f"eq.{scan_id}", "select": "*"})
                    rec = {**rows[0], "violations": violations}
            except Exception as err:
                logger.warning(f"Supabase get error (falling back to memory): {err}")

        if not rec:
            rec = self._memory.get(scan_id)

        if rec and isinstance(rec, dict):
            if "declarations" not in rec and "extracted_fields_json" in rec:
                ef = rec["extracted_fields_json"]
                if isinstance(ef, dict):
                    rec["declarations"] = ef.get("declarations", {})
                    rec["fields"] = ef.get("fields", {})

        return rec

    def analytics(self) -> dict[str, Any]:
        rows = self.list(page=1, page_size=10000)["items"]
        total = len(rows)
        compliant = sum(r.get("compliance_status") == "COMPLIANT" for r in rows)
        warning = sum(r.get("compliance_status") == "WARNING" for r in rows)
        non_compliant = sum(r.get("compliance_status") == "NON_COMPLIANT" for r in rows)
        avg_score = (
            sum(float(r.get("compliance_score", 100)) for r in rows) / total if total > 0 else 100.0
        )
        total_violations = sum(len(r.get("violations", [])) for r in rows)
        return {
            "total_scans": total,
            "total_packages_scanned": total,
            "average_compliance_score": round(avg_score, 2),
            "compliance_rate_pct": round((compliant / total) * 100, 2) if total else 100.0,
            "total_violations": total_violations,
            "status_counts": {"COMPLIANT": compliant, "WARNING": warning, "NON_COMPLIANT": non_compliant},
        }


repository = ScanRepository()
