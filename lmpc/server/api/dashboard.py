"""Jurisdiction-scoped dashboard endpoints (Part 12.7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..svc.auth import Principal
from .auth import require

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(
    request: Request,
    principal: Principal = Depends(require("dashboard:read")),
) -> dict:
    return request.app.state.dashboard.summary(principal)


@router.get("/violations-by-type")
async def violations_by_type(
    request: Request, limit: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(require("dashboard:read")),
) -> list[dict]:
    return request.app.state.dashboard.violations(principal, limit)


@router.get("/top-non-compliant")
async def top_non_compliant(
    request: Request, limit: int = Query(10, ge=1, le=100),
    principal: Principal = Depends(require("dashboard:read")),
) -> list[dict]:
    return request.app.state.dashboard.top_non_compliant(principal, limit)


@router.get("/geo")
async def geo(
    request: Request,
    principal: Principal = Depends(require("dashboard:read")),
) -> list[dict]:
    return request.app.state.dashboard.geo(principal)


@router.get("/quality")
async def quality(
    request: Request,
    principal: Principal = Depends(require("dashboard:read")),
) -> dict:
    return request.app.state.dashboard.quality(principal)
