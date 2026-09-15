"""Investigations: the folder a field officer creates, works inside, and reopens later."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..svc.auth import Principal
from .auth import require

router = APIRouter(tags=["investigations"])


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_uuid: str | None = None          # set by the phone; makes a retry idempotent
    name: str = Field(min_length=1, max_length=200)
    subject_brand: str | None = None
    investigation_type: str | None = None
    location_text: str | None = None
    jurisdiction_id: str | None = None


class InvestigationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject_brand: str | None = None
    investigation_type: str | None = None
    location_text: str | None = None
    status: str | None = None


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)


def _service(request: Request):
    return request.app.state.investigations


@router.post("/investigations", status_code=201)
async def create_investigation(
    body: InvestigationCreate, request: Request,
    principal: Principal = Depends(require("investigations:create")),
) -> JSONResponse:
    row, created = _service(request).create(principal, body.model_dump())
    if created:
        request.app.state.auth.audit_action(
            principal, "investigation", row["id"], "INVESTIGATION_CREATE",
            {"name": row["name"]})
    return JSONResponse(row if created else {**row, "duplicate_ignored": True},
                        status_code=201 if created else 200)


@router.get("/investigations")
async def list_investigations(
    request: Request,
    q: str | None = None, status: str | None = None,
    investigation_type: str | None = None, created_by: str | None = None,
    sort: str = "recent", page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    principal: Principal = Depends(require("investigations:read")),
) -> dict:
    filters = {"q": q, "status": status, "investigation_type": investigation_type,
               "created_by": created_by}
    return _service(request).list(principal, filters, page, page_size, sort)


@router.get("/investigations/{investigation_id}")
async def get_investigation(
    investigation_id: str, request: Request,
    principal: Principal = Depends(require("investigations:read")),
) -> dict:
    return _service(request).get(principal, investigation_id)


@router.patch("/investigations/{investigation_id}")
async def update_investigation(
    investigation_id: str, body: InvestigationPatch, request: Request,
    principal: Principal = Depends(require("investigations:update")),
) -> dict:
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    row = _service(request).update(principal, investigation_id, changes)
    request.app.state.auth.audit_action(
        principal, "investigation", investigation_id, "INVESTIGATION_UPDATE", changes)
    return row


@router.get("/investigations/{investigation_id}/scans")
async def investigation_scans(
    investigation_id: str, request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    sort: str = "newest",
    principal: Principal = Depends(require("investigations:read")),
) -> dict:
    _service(request).get(principal, investigation_id)     # 404 before listing
    return request.app.state.review.list_scans(
        principal, {"investigation_id": investigation_id}, page, page_size, sort)


@router.get("/investigations/{investigation_id}/stats")
async def investigation_stats(
    investigation_id: str, request: Request,
    principal: Principal = Depends(require("investigations:read")),
) -> dict:
    return _service(request).stats(principal, investigation_id)


@router.get("/investigations/{investigation_id}/notes")
async def list_notes(
    investigation_id: str, request: Request,
    principal: Principal = Depends(require("investigations:read")),
) -> dict:
    return {"items": _service(request).notes(principal, investigation_id)}


@router.post("/investigations/{investigation_id}/notes", status_code=201)
async def add_note(
    investigation_id: str, body: NoteCreate, request: Request,
    principal: Principal = Depends(require("investigations:update")),
) -> dict:
    return _service(request).add_note(principal, investigation_id, body.body)
