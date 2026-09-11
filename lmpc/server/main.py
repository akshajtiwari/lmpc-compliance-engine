"""Application factory. Start-up refuses to serve when the rulepack cannot be proven
intact — a service that cannot vouch for its law must not issue findings."""
from __future__ import annotations
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from .api import (accounts, auth, dashboard, errors, health, reports, review, rules,
                  scan_intake, scans)
from .config import Settings
from .svc.object_store import open_object_store
from .svc.accounts import AccountService
from .svc.auth import AuthManager
from .svc.dashboard import DashboardService
from .svc.pipeline import Pipeline
from .svc.reporting import ReportService
from .svc.review import ReviewService
from .svc.scan_store import open_store
from .svc.rate_limit import RateLimiter
from .obs.logging import setup as setup_logging, trace_id


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    app = FastAPI(title="LMPC Compliance API", version="1.0.0", root_path="/api/v1")
    log = setup_logging(s.log_level)
    limiter = RateLimiter(s.rate_limit_per_min)

    @app.middleware("http")
    async def local_rate_limit(request, call_next):
        path = request.url.path
        exempt = path.endswith(("/healthz", "/readyz", "/metrics"))
        if "/api/v1/" in path and not exempt:
            client = request.client.host if request.client else "unknown"
            allowed, remaining, retry_after = limiter.take(client)
            if not allowed:
                return JSONResponse(
                    {"error": {"code": "E_RATE_LIMITED",
                               "message": "request rate limit exceeded", "details": []}},
                    status_code=429, headers={"Retry-After": str(retry_after)})
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limiter.limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response
        return await call_next(request)

    @app.middleware("http")
    async def request_observability(request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = (incoming if 8 <= len(incoming) <= 64
                      and all(char.isalnum() or char in "-_" for char in incoming)
                      else str(uuid.uuid4()))
        context = trace_id.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            principal = getattr(request.state, "principal", None)
            parts = request.url.path.split("/")
            scan_id = parts[parts.index("scans") + 1] if "scans" in parts \
                and len(parts) > parts.index("scans") + 1 else None
            log.info(
                f"request.complete {request.method} {request.url.path} "
                f"status={response.status_code} duration_ms="
                f"{(time.perf_counter() - started) * 1000:.1f}",
                extra={"scan_id": scan_id,
                       "user_id": principal.id if principal else None})
            return response
        finally:
            trace_id.reset(context)

    @app.middleware("http")
    async def browser_security_headers(request, call_next):
        response = await call_next(request)
        if not request.url.path.endswith(("/docs", "/redoc", "/openapi.json")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' blob: data:; "
                "style-src 'self'; script-src 'self'; connect-src 'self'; "
                "worker-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), geolocation=(self)"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload")
        return response

    app.state.settings = s
    app.state.object_store = open_object_store(s)
    app.state.scan_store = open_store(s)
    app.state.auth = AuthManager(s)
    app.state.accounts = AccountService(app.state.auth)
    app.state.review = ReviewService(app.state.scan_store, app.state.auth)
    app.state.dashboard = DashboardService(app.state.scan_store, app.state.review)
    errors.install(app)
    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(health.router)
    app.include_router(scans.router)
    app.include_router(scan_intake.router)
    app.include_router(reports.router)
    app.include_router(review.router)
    app.include_router(dashboard.router)
    app.include_router(rules.router)
    pack = health.boot(s.rulepack_path)   # fail-fast before the first request
    app.state.pipeline = Pipeline(
        app.state.scan_store, app.state.object_store, pack, s.ocr_max_edge,
        corrections=app.state.review.corrections)
    app.state.reports = ReportService(
        app.state.scan_store, app.state.object_store, pack, max_edge=s.ocr_max_edge,
        git_sha=s.git_sha, container_digest=s.container_digest)
    web_root = Path(__file__).with_name("web")
    app.mount("/", StaticFiles(directory=web_root, html=True), name="web")
    return app


app = create_app()
