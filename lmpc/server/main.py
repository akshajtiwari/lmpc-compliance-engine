"""Application factory. Start-up refuses to serve when the rulepack cannot be proven
intact — a service that cannot vouch for its law must not issue findings."""
from __future__ import annotations
from fastapi import FastAPI

from . import rulepack
from .api import errors, health, scans
from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    app = FastAPI(title="LMPC Compliance API", version="1.0.0", root_path="/api/v1")
    errors.install(app)
    app.include_router(health.router)
    app.include_router(scans.router)
    health.boot(s.rulepack_path)          # fail-fast before the first request
    return app


app = create_app()