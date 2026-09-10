"""Error envelope (Part 12.1): every failure is {"error": {code, message, details}}.

Codes come from Appendix A. A client that cannot tell E_COVERAGE_MISMATCH from
E_VALIDATION cannot react correctly, and the capture app must know exactly which one
hit it."""
from __future__ import annotations
from fastapi import Request
from fastapi.responses import JSONResponse

CODES = {
    "E_VALIDATION": 400, "E_REASON_REQUIRED": 400, "E_BOUNDARY_UNCONFIRMED": 400,
    "E_BAD_CREDENTIALS": 401, "E_TOKEN_EXPIRED": 401, "E_REFRESH_REVOKED": 401,
    "E_MFA_REQUIRED": 403, "E_STEP_UP_REQUIRED": 403, "E_FORBIDDEN": 403,
    "E_NOT_FOUND": 404, "E_SCAN_FINALIZED": 409, "E_COVERAGE_MISMATCH": 409,
    "E_CONFLICT": 409, "E_IMAGE_TOO_LARGE": 413, "E_UNSUPPORTED_MEDIA": 415,
    "E_RATE_LIMITED": 429, "E_RULEPACK_INTEGRITY": 503, "E_INTERNAL": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: list | None = None):
        self.code, self.message, self.details = code, message, details or []
        super().__init__(message)


async def handler(_: Request, exc: Exception) -> JSONResponse:
    status = CODES.get(exc.code, 500)          # type: ignore[attr-defined]
    body = {"error": {"code": exc.code, "message": exc.message,      # type: ignore
                      "details": exc.details}}                       # type: ignore
    return JSONResponse(body, status_code=status)


def install(app) -> None:
    app.add_exception_handler(ApiError, handler)
