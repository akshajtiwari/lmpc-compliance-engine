"""Review workflow over either the local PostgreSQL or in-memory scan store."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from lmpc.engine import normalize
from lmpc.engine.engine import FIELD_KINDS

from ..api.errors import ApiError
from ..obs import metrics
from .review_db import ReviewDb, overall

PACKAGE_SHAPES = {"RECTANGULAR", "CYLINDRICAL", "IRREGULAR"}
OUTCOMES = {"PASS", "FAIL", "INDETERMINATE", "NOT_APPLICABLE",
            "REVIEW_REQUIRED", "SYSTEM_ERROR"}


class ReviewService:
    def __init__(self, scan_store, auth):
        self.scans = scan_store
        self.auth = auth
        self.db = ReviewDb(scan_store) if hasattr(scan_store, "sessions") else None

    def list_scans(self, principal, filters: dict, page: int,
                   page_size: int, sort: str) -> dict:
        if sort not in {"newest", "oldest", "status", "overall"}:
            raise ApiError("E_VALIDATION", "sort must be newest, oldest, status or overall")
        if filters.get("jurisdiction_id"):
            self.auth.ensure_jurisdiction_scope(
                principal, str(filters["jurisdiction_id"]))
        if self.db:
            return self.db.list_scans(principal, filters, page, page_size, sort)
        rows = [record for record in self.scans._by_id.values()
                if _memory_match(record, filters)]
        reverse = sort != "oldest"
        key = ({"newest": lambda row: row.captured_at,
                "oldest": lambda row: row.captured_at,
                "status": lambda row: row.status,
                "overall": lambda row: row.overall or ""})[sort]
        rows.sort(key=key, reverse=reverse)
        start = (page - 1) * page_size
        items = [_memory_summary(row) for row in rows[start:start + page_size]]
        return {"items": items, "page": page, "page_size": page_size,
                "total": len(rows), "pages": (len(rows) + page_size - 1) // page_size}

    def update_scan(self, scan_id: str, changes: dict, principal):
        record = self._writable(scan_id, principal)
        if self.db:
            return self.db.update_scan(scan_id, changes, principal)
        if "product_id" in changes:
            record.metadata["product_id"] = changes["product_id"]
        if "package_shape" in changes:
            record.metadata["package_shape"] = changes["package_shape"]
        if "category" in changes:
            record.category = changes["category"]
        for key, value in (changes.get("dimensions") or {}).items():
            record.metadata[{"h_cm": "pdp_h_cm", "w_cm": "pdp_w_cm",
                             "capacity_cm3": "capacity_cm3"}[key]] = value
        if record.status == "EVALUATION_COMPLETE":
            record.status, record.overall = "RECEIVED", None
        return record

    def correct(self, scan_id: str, field: str, text: str,
                bbox: list[int] | None, principal) -> dict:
        if field not in FIELD_KINDS:
            raise ApiError("E_VALIDATION", f"unsupported declaration field: {field}")
        cleaned = text.strip()
        if not cleaned or len(cleaned) > 4000:
            raise ApiError("E_VALIDATION", "correction text must contain 1–4000 characters")
        record = self._writable(scan_id, principal)
        parsed = _normalized(field, cleaned)
        if self.db:
            return self.db.correct(scan_id, field, cleaned, bbox, parsed, principal)
        original = next((row for row in reversed(record.declarations)
                         if row["field"] == field), None)
        bounds = bbox or (original["bbox"] if original else
                          [0, 0, max(8, len(cleaned) * 8), 22])
        item = {
            "id": str(uuid.uuid4()), "batch": max(record.batch, 1), "field": field,
            "text": cleaned, "normalized_value": parsed, "bbox": bounds,
            "confidence": 1.0, "score": 100.0, "margin": 100.0,
            "feature_weights": {"officer_correction": 100.0},
            "source_token_ids": [], "is_composite": False, "is_repaired": False,
            "glyph_height_px": bounds[3], "panel": original.get("panel", "FRONT")
            if original else "FRONT", "corrected_by": principal.id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        item["source_token_ids"] = [f"correction:{item['id']}"]
        record.declarations.append(item)
        return item

    def corrections(self, scan_id: str) -> list[dict]:
        if self.db:
            return self.db.corrections(scan_id)
        record = self.scans.get(scan_id)
        effective = {}
        for row in record.declarations:
            if row.get("corrected_by"):
                effective[row["field"]] = row
        return list(effective.values())

    def evaluations(self, scan_id: str, batch: int | None, principal) -> dict:
        record = self.scans.get(scan_id)
        self.auth.ensure_scan_scope(principal, record)
        if batch is not None and batch < 1:
            raise ApiError("E_VALIDATION", "batch must be at least 1")
        if self.db:
            selected, rows = self.db.evaluations(scan_id, batch)
        else:
            selected = batch or record.batch
            rows = [row for row in record.evaluations if row["batch"] == selected]
        if batch is not None and not rows:
            raise ApiError("E_NOT_FOUND", f"evaluation batch {batch} not found")
        return {"scan_id": scan_id, "batch": selected, "evaluations": rows,
                "effective": _effective(rows)}

    def override(self, scan_id: str, evaluation_id: str, outcome: str,
                 reason: str, principal) -> dict:
        if outcome not in OUTCOMES:
            raise ApiError("E_VALIDATION", f"unsupported outcome: {outcome}")
        cleaned = reason.strip()
        if len(cleaned) < 10:
            raise ApiError("E_REASON_REQUIRED", "override reason must be at least 10 characters")
        record = self.scans.get(scan_id)
        self.auth.ensure_scan_scope(principal, record)
        if record.status == "FINALIZED":
            raise ApiError("E_SCAN_FINALIZED", "a finalized finding cannot be overridden")
        if self.db:
            row = self.db.override(scan_id, evaluation_id, outcome, cleaned, principal)
            metrics.inc("lmpc_override_total", check=row["check"])
            return row
        target = next((row for row in record.evaluations
                       if row["id"] == evaluation_id), None)
        if target is None:
            raise ApiError("E_NOT_FOUND", "evaluation not found on this scan")
        root = target.get("override_of_evaluation_id") or target["id"]
        row = {**target, "id": str(uuid.uuid4()), "outcome": outcome,
               "reason": f"Officer override from {target['outcome']}: {cleaned}",
               "is_override": True, "override_of_evaluation_id": root,
               "override_reason": cleaned, "overridden_by": principal.id,
               "evaluated_at": datetime.now(UTC).isoformat()}
        record.evaluations.append(row)
        if row["batch"] == record.batch:
            record.overall = overall(record.latest_evaluations())
        metrics.inc("lmpc_override_total", check=row["check"])
        return row

    def _writable(self, scan_id: str, principal):
        record = self.scans.get(scan_id)
        self.auth.ensure_scan_scope(principal, record)
        if record.status == "FINALIZED":
            raise ApiError("E_SCAN_FINALIZED", "a finalized scan cannot be changed")
        if principal.role == "FIELD_OFFICER" and record.status == "UNDER_REVIEW":
            raise ApiError("E_FORBIDDEN", "field officers cannot change a scan under review")
        return record


def validate_changes(changes: dict) -> dict:
    if not changes:
        raise ApiError("E_VALIDATION", "at least one scan field is required")
    if changes.get("package_shape") not in PACKAGE_SHAPES and "package_shape" in changes:
        raise ApiError("E_VALIDATION", "unsupported package_shape")
    dimensions = changes.get("dimensions")
    if dimensions is not None:
        if not isinstance(dimensions, dict) or not dimensions:
            raise ApiError("E_VALIDATION", "dimensions must contain a value")
        allowed = {"h_cm", "w_cm", "capacity_cm3"}
        if set(dimensions) - allowed:
            raise ApiError("E_VALIDATION", "dimensions contain an unknown field")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
               for value in dimensions.values()):
            raise ApiError("E_VALIDATION", "dimensions must be positive numbers")
        if ("h_cm" in dimensions) != ("w_cm" in dimensions):
            raise ApiError("E_VALIDATION", "dimensions require h_cm and w_cm together")
    if changes.get("category") is not None:
        from .scan_service import CATEGORIES
        if changes["category"] not in CATEGORIES:
            raise ApiError("E_VALIDATION", "unsupported commodity category")
    return changes


def validate_bbox(value: list[int] | None) -> list[int] | None:
    if value is None:
        return None
    if len(value) != 4 or any(isinstance(n, bool) or not isinstance(n, int) for n in value):
        raise ApiError("E_VALIDATION", "bbox must be four integer pixel coordinates")
    if value[0] < 0 or value[1] < 0 or value[2] <= 0 or value[3] <= 0:
        raise ApiError("E_VALIDATION", "bbox origin must be non-negative and size positive")
    return value


def _normalized(field: str, text: str) -> dict:
    parser = {"mrp": lambda value: normalize.money(value, require_currency=False),
              "net_quantity": normalize.quantity,
              "mfg_date": normalize.month_year}.get(field)
    return (parser(text) if parser else {}) or {}


def _effective(rows: list[dict]) -> list[dict]:
    effective = {}
    for row in rows:
        effective[row["check"]] = row
    return list(effective.values())


def _memory_match(row, filters: dict) -> bool:
    checks = (("category", row.category), ("status", row.status),
              ("overall", row.overall), ("officer_id", row.officer_id),
              ("jurisdiction_id", row.jurisdiction_id))
    if any(filters.get(key) is not None and filters[key] != value for key, value in checks):
        return False
    if filters.get("date_from") and row.captured_at < str(filters["date_from"]):
        return False
    if filters.get("date_to") and row.captured_at > str(filters["date_to"]):
        return False
    query = str(filters.get("q") or "").casefold()
    if query and query not in f"{row.client_uuid} {row.category}".casefold():
        return False
    violation = filters.get("violation_type")
    return not violation or any(item["check"] == violation and item["outcome"] == "FAIL"
                                for item in row.latest_evaluations())


def _memory_summary(row) -> dict:
    return {"id": row.id, "client_uuid": row.client_uuid,
            "captured_at": row.captured_at, "created_at": row.captured_at,
            "mode": row.mode, "category": row.category, "status": row.status,
            "overall": row.overall, "coverage_asserted": row.coverage_asserted,
            "officer_id": row.officer_id, "jurisdiction_id": row.jurisdiction_id,
            "product_id": row.metadata.get("product_id"), "brand": None,
            "manufacturer": None}
