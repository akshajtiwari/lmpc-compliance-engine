"""Scoped repository, correction and verdict-review endpoints (Parts 12.3–12.4)."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict

from ..svc.auth import Principal
from ..svc.review import validate_bbox, validate_changes
from .auth import require
from .scans import _envelope

router = APIRouter(tags=["review"])


class ScanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str | None = None
    package_shape: str | None = None
    category: str | None = None
    dimensions: dict | None = None


class CorrectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    bbox: list[int] | None = None


class OverrideBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str
    reason: str


@router.get("/scans")
async def list_scans(
    request: Request,
    manufacturer: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    status: str | None = None,
    overall: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    officer_id: uuid.UUID | None = None,
    jurisdiction_id: uuid.UUID | None = None,
    violation_type: str | None = None,
    q: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str = "newest",
    principal: Principal = Depends(require("scans:read")),
) -> dict:
    filters = {
        "manufacturer": manufacturer, "brand": brand, "category": category,
        "status": status, "overall": overall, "date_from": date_from,
        "date_to": date_to, "officer_id": officer_id,
        "jurisdiction_id": jurisdiction_id, "violation_type": violation_type, "q": q,
    }
    return request.app.state.review.list_scans(
        principal, filters, page, page_size, sort)


@router.patch("/scans/{scan_id}")
async def update_scan(
    scan_id: str, payload: ScanPatch, request: Request,
    principal: Principal = Depends(require("scans:update")),
) -> dict:
    changes = validate_changes(payload.model_dump(exclude_unset=True))
    record = request.app.state.review.update_scan(scan_id, changes, principal)
    return {**_envelope(record, created=True), "reevaluation_required": True}


@router.post("/scans/{scan_id}/declarations/{field}")
async def correct_declaration(
    scan_id: str, field: str, payload: CorrectionBody, request: Request,
    principal: Principal = Depends(require("declarations:correct")),
) -> dict:
    declaration = request.app.state.review.correct(
        scan_id, field, payload.text, validate_bbox(payload.bbox), principal)
    return {"scan_id": scan_id, "declaration": declaration,
            "reevaluation_required": True}


@router.get("/scans/{scan_id}/evaluations")
async def evaluation_history(
    scan_id: str, request: Request,
    batch: int | None = Query(None, ge=1),
    principal: Principal = Depends(require("evaluations:read")),
) -> dict:
    return request.app.state.review.evaluations(scan_id, batch, principal)


@router.post("/scans/{scan_id}/evaluations/{evaluation_id}/override")
async def override_evaluation(
    scan_id: str, evaluation_id: str, payload: OverrideBody, request: Request,
    principal: Principal = Depends(require("evaluations:override")),
) -> dict:
    evaluation = request.app.state.review.override(
        scan_id, evaluation_id, payload.outcome, payload.reason, principal)
    scan = request.app.state.scan_store.get(scan_id)
    return {"scan_id": scan_id, "overall": scan.overall, "evaluation": evaluation}
