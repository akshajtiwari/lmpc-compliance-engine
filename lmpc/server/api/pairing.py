"""Connect a phone to this computer, with nothing else installed (desktop build only).

This router exists because the portable build shipped with no way to pair at all: the
enrollment QR lived in the Next.js workbench, behind npm and Docker, and the executable
ran with authentication disabled so it could not have minted one anyway.

It is mounted only when `LMPC_DESKTOP_MODE` is set, which keeps it out of the deployed
API surface and out of `docs/api/openapi.json` entirely.

Three gates guard every route here, because this page hands out credentials and can open
the listener to the network:

1. desktop mode, checked at mount time;
2. the request must come from this machine — a phone must never reach the pairing page;
3. a per-process CSRF token on every state change. Without it any web page the user
   happens to visit could POST to 127.0.0.1 and arm the network listener. It could not
   read the response, but it would not need to.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..net import is_loopback, lan_address
from ..svc.pairing import PairingService
from .errors import ApiError
from .pairing_page import render

router = APIRouter(tags=["pairing"], include_in_schema=False)

CSRF_TOKEN = secrets.token_urlsafe(24)


def _guard(request: Request) -> PairingService:
    if not is_loopback(request.client.host if request.client else None):
        raise ApiError("E_FORBIDDEN",
                       "the pairing page is only available on this computer")
    service = getattr(request.app.state, "pairing", None)
    if service is None:
        raise ApiError("E_FORBIDDEN", "pairing is only available in the desktop build")
    return service


def _check_csrf(value: str) -> None:
    if not secrets.compare_digest(value or "", CSRF_TOKEN):
        raise ApiError("E_FORBIDDEN", "stale pairing form; reload the page")


@router.get("/pair", response_class=HTMLResponse)
async def pair_page(request: Request) -> HTMLResponse:
    service = _guard(request)
    return HTMLResponse(render(service.snapshot(), CSRF_TOKEN))


@router.get("/pair/qr.svg")
async def pair_qr(request: Request) -> Response:
    """The QR as same-origin SVG. The page's CSP forbids inline script and style, so it
    cannot be drawn in the browser."""
    service = _guard(request)
    return Response(service.qr_svg(), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@router.post("/pair/enrollment")
async def pair_enrollment(request: Request, csrf: str = Form("")) -> RedirectResponse:
    service = _guard(request)
    _check_csrf(csrf)
    service.new_invitation()
    return RedirectResponse("/pair", status_code=303)


@router.post("/pair/network")
async def pair_network(request: Request, csrf: str = Form(""),
                       allow: str = Form("")) -> RedirectResponse:
    """Arm or disarm LAN access.

    The socket is already bound to every interface; this flips whether non-loopback
    requests are answered or refused. One socket, instant either way, and nothing to
    restart.
    """
    service = _guard(request)
    _check_csrf(csrf)
    service.set_network_open(allow == "on")
    return RedirectResponse("/pair", status_code=303)


@router.get("/pair/status")
async def pair_status(request: Request) -> dict:
    """Polled by the page so it can say 'phone connected' without a reload."""
    service = _guard(request)
    state = service.snapshot()
    return {"network_open": state["network_open"],
            "devices_enrolled": state["devices_enrolled"],
            "expires_at": state["expires_at"],
            "lan_url": state["lan_url"] or (lan_address() or "")}
