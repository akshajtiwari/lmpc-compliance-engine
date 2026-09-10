"""Application factory. Start-up refuses to serve when the rulepack cannot be proven
intact — a service that cannot vouch for its law must not issue findings."""
from __future__ import annotations
from fastapi import FastAPI

from .api import errors, health, scans
from .config import Settings
from .svc.object_store import open_object_store
from .svc.scan_store import open_store


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    app = FastAPI(title="LMPC Compliance API", version="1.0.0", root_path="/api/v1")
    app.state.settings = s
    app.state.object_store = open_object_store(s)
    app.state.scan_store = open_store(s)
    errors.install(app)
    app.include_router(health.router)
    app.include_router(scans.router)
    health.boot(s.rulepack_path)          # fail-fast before the first request
    return app


app = create_app()
