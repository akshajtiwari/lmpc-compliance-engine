"""Read-only plain-language rule guidance for the officer workbench."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ..svc.auth import Principal
from ..svc.rule_help import rule_detail
from ..svc.rulepack_view import overview
from .auth import require

router = APIRouter(prefix="/rules", tags=["rules"])
RuleReader = Annotated[Principal, Depends(require("rules:read"))]


@router.get("")
async def get_rulepack_overview(
    request: Request,
    _principal: RuleReader,
) -> dict:
    """The loaded rulepack: version, instruments and every check it applies."""
    return overview(request.app.state.pipeline.rulepack)


@router.get("/{check_code}")
async def get_rule_detail(
    check_code: str,
    request: Request,
    _principal: RuleReader,
) -> dict:
    return rule_detail(request.app.state.pipeline.rulepack, check_code)
