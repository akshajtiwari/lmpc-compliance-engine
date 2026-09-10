"""Operations endpoints (Part 12.9). Anonymous by design: orchestrators cannot log in."""
from __future__ import annotations
from fastapi import APIRouter

from .. import rulepack

router = APIRouter(tags=["ops"])
_state: dict = {}


def boot(rulepack_path: str) -> None:
    """Fail-fast: a corrupt or absent rulepack is a start-up failure, not a 500 later."""
    _state["rulepack"] = rulepack.load(rulepack_path)


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict:
    pack = _state.get("rulepack")
    ready = pack is not None and rulepack.intact(pack)
    return {"status": "ok" if ready else "E_RULEPACK_INTEGRITY"}


@router.get("/version")
def version() -> dict:
    return {"git_sha": "", **rulepack.summary()}