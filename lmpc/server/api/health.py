"""Operations endpoints (Part 12.9). Anonymous by design: orchestrators cannot log in."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .. import rulepack
from ..obs import metrics

router = APIRouter(tags=["ops"])
_state: dict = {}


def boot(rulepack_path: str) -> dict:
    """Fail-fast: a corrupt or absent rulepack is a start-up failure, not a 500 later."""
    _state["rulepack"] = rulepack.load(rulepack_path)
    metrics.set_chain_complete(_state["rulepack"]["currency"]["chain_complete"])
    return _state["rulepack"]


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    pack = _state.get("rulepack")
    checks = {
        "rulepack": pack is not None and rulepack.intact(pack),
        "database": request.app.state.scan_store.ready(),
        "object_store": request.app.state.object_store.ready(),
    }
    if all(checks.values()):
        return {"status": "ok"}
    return JSONResponse(
        {"status": "not_ready", "checks": checks}, status_code=503)


@router.get("/version")
async def version() -> dict:
    return {"git_sha": "", **rulepack.summary()}


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    return metrics.exposition()
