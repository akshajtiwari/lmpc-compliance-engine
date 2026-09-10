"""Application factory. Start-up refuses to serve when the rulepack cannot be proven
intact — a service that cannot vouch for its law must not issue findings."""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import auth, dashboard, errors, health, reports, review, scans
from .config import Settings
from .svc.object_store import open_object_store
from .svc.auth import AuthManager
from .svc.dashboard import DashboardService
from .svc.pipeline import Pipeline
from .svc.reporting import ReportService
from .svc.review import ReviewService
from .svc.scan_store import open_store


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    app = FastAPI(title="LMPC Compliance API", version="1.0.0", root_path="/api/v1")

    @app.middleware("http")
    async def browser_security_headers(request, call_next):
        response = await call_next(request)
        if not request.url.path.endswith(("/docs", "/redoc", "/openapi.json")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' blob: data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                "worker-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), geolocation=(self)"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    app.state.settings = s
    app.state.object_store = open_object_store(s)
    app.state.scan_store = open_store(s)
    app.state.auth = AuthManager(s)
    app.state.review = ReviewService(app.state.scan_store, app.state.auth)
    app.state.dashboard = DashboardService(app.state.scan_store, app.state.review)
    errors.install(app)
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(scans.router)
    app.include_router(reports.router)
    app.include_router(review.router)
    app.include_router(dashboard.router)
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
