"""Authentication endpoints plus reusable permission dependencies."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ..svc.auth import ACCESS_TTL, REFRESH_TTL, Principal
from .errors import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
COOKIE = "lmpc_refresh"


class LoginBody(BaseModel):
    email: str
    password: str
    otp: str | None = None


class RefreshBody(BaseModel):
    refresh_token: str | None = None


async def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    token = credentials.credentials if credentials else None
    return request.app.state.auth.current(token)


def require(permission: str) -> Callable:
    async def allowed(
        request: Request,
        principal: Principal = Depends(current_principal),
    ) -> Principal:
        if not principal.has(permission):
            request.app.state.auth.audit_denial(principal, "endpoint", None)
            raise ApiError("E_FORBIDDEN", f"permission required: {permission}")
        return principal

    return allowed


@router.post("/login")
async def login(payload: LoginBody, request: Request) -> JSONResponse:
    access, refresh, principal = request.app.state.auth.login(
        payload.email, payload.password, user_agent=request.headers.get("user-agent"),
        ip=_ip(request))
    response = JSONResponse({
        "access_token": access, "refresh_token": refresh,
        "expires_in": int(ACCESS_TTL.total_seconds()), "user": principal.public(),
    })
    _cookie(response, refresh, request.app.state.settings.cookie_secure)
    return response


@router.post("/refresh")
async def refresh(
    request: Request,
    payload: RefreshBody | None = None,
    cookie_token: str | None = Cookie(None, alias=COOKIE),
) -> JSONResponse:
    access, rotated, principal = request.app.state.auth.refresh(
        payload.refresh_token if payload and payload.refresh_token else cookie_token,
        user_agent=request.headers.get("user-agent"), ip=_ip(request))
    response = JSONResponse({
        "access_token": access, "expires_in": int(ACCESS_TTL.total_seconds()),
        "user": principal.public(),
    })
    _cookie(response, rotated, request.app.state.settings.cookie_secure)
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    payload: RefreshBody | None = None,
    cookie_token: str | None = Cookie(None, alias=COOKIE),
) -> Response:
    request.app.state.auth.logout(
        payload.refresh_token if payload and payload.refresh_token else cookie_token,
        user_agent=request.headers.get("user-agent"), ip=_ip(request))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/", samesite="strict")
    return response


@router.get("/me")
async def me(principal: Principal = Depends(current_principal)) -> dict:
    return principal.public()


def _cookie(response: Response, value: str, secure: bool) -> None:
    response.set_cookie(
        COOKIE, value, max_age=int(REFRESH_TTL.total_seconds()), path="/",
        secure=secure, httponly=True, samesite="strict")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None
