"""Account administration and mobile-device enrollment endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..svc.auth import ACCESS_TTL, REFRESH_TTL, Principal
from .auth import require

router = APIRouter(tags=["accounts"])


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    role: str
    jurisdiction_id: str | None = None
    phone: str | None = Field(None, max_length=20)
    department: str | None = Field(None, max_length=150)
    password: str | None = None
    is_legal_reviewer: bool = False


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(None, min_length=1, max_length=200)
    role: str | None = None
    jurisdiction_id: str | None = None
    phone: str | None = Field(None, max_length=20)
    department: str | None = Field(None, max_length=150)
    password: str | None = None
    is_active: bool | None = None
    is_legal_reviewer: bool | None = None


class EnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_url: str | None = None


class EnrollmentExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=200)
    device_name: str | None = Field(None, max_length=200)


@router.get("/admin/users")
async def list_users(
    request: Request, principal: Principal = Depends(require("users:read")),
) -> dict:
    return {"items": request.app.state.accounts.list_users(principal)}


@router.post("/admin/users", status_code=201)
async def create_user(
    payload: UserCreate, request: Request,
    principal: Principal = Depends(require("users:manage")),
) -> dict:
    return request.app.state.accounts.create_user(payload.model_dump(), principal)


@router.patch("/admin/users/{user_id}")
async def update_user(
    user_id: str, payload: UserPatch, request: Request,
    principal: Principal = Depends(require("users:manage")),
) -> dict:
    return request.app.state.accounts.update_user(
        user_id, payload.model_dump(exclude_unset=True), principal)


@router.get("/admin/jurisdictions")
async def list_jurisdictions(
    request: Request, _: Principal = Depends(require("users:read")),
) -> dict:
    return {"items": request.app.state.accounts.list_jurisdictions()}


@router.post("/admin/users/{user_id}/enrollments", status_code=201)
async def issue_enrollment(
    user_id: str, payload: EnrollmentRequest, request: Request,
    principal: Principal = Depends(require("users:manage")),
) -> dict:
    return request.app.state.accounts.issue_enrollment(
        user_id, payload.server_url, principal)


@router.post("/auth/enroll")
async def enroll_mobile(payload: EnrollmentExchange, request: Request) -> JSONResponse:
    access, refresh, principal = request.app.state.auth.enroll(
        payload.token, device_name=payload.device_name,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None)
    response = JSONResponse({
        "access_token": access, "refresh_token": refresh,
        "expires_in": int(ACCESS_TTL.total_seconds()), "user": principal.public(),
        "refresh_expires_in": int(REFRESH_TTL.total_seconds()),
        "server_fingerprint": request.app.state.auth.server_fingerprint(),
    })
    response.headers["Cache-Control"] = "no-store"
    return response
