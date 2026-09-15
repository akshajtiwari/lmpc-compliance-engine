"""Connecting a phone to the portable build, with nothing else installed.

The shipped preview could not pair at all: it ran with authentication disabled, so
AccountService refused to manage accounts and the executable could not mint an enrollment
even in principle. These tests pin the replacement — and, just as importantly, pin the
three gates that keep a credential-bearing page off the network.
"""
from __future__ import annotations

import urllib.parse

import httpx
import pytest

from lmpc.server.api import pairing as pairing_api
from lmpc.server.config import Settings
from lmpc.server.db import desktop_bootstrap
from lmpc.server.main import create_app
from lmpc.server.svc.pairing import PairingService

pytestmark = pytest.mark.anyio

PHONE = ("192.168.1.55", 51000)
HERE = ("127.0.0.1", 50000)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def desktop(tmp_path, monkeypatch):
    data_root = tmp_path / "portable"
    data_root.mkdir()
    db_url = f"sqlite+pysqlite:///{data_root / 'lmpc.sqlite3'}"
    monkeypatch.setenv("LMPC_JWT_KEY_PATH", str(data_root / "jwt.pem"))
    record = desktop_bootstrap.run(data_root, db_url)
    app = create_app(Settings(
        db_url=db_url, auth_mode="local", desktop_mode=True,
        storage_root=str(data_root / "objects"),
        jwt_key_path=str(data_root / "jwt.pem"),
        officer_uuid=record["officer"]["id"],
        jurisdiction_uuid=record["jurisdiction_id"]))
    app.state.pairing = PairingService(app.state.accounts, app.state.auth, record, 8000)
    return app


def client(app, peer=HERE) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=peer),
        base_url="http://testserver")


async def test_the_pairing_page_renders_a_code_for_somebody_at_the_computer(desktop):
    async with client(desktop) as http:
        page = await http.get("/pair")
        assert page.status_code == 200
        assert "/pair/qr.svg" in page.text
        qr = await http.get("/pair/qr.svg")
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/svg+xml")
        assert qr.content.lstrip().startswith(b"<svg")


async def test_the_pairing_page_is_refused_from_the_network(desktop):
    """It prints two plaintext passwords and can open the listener. A phone, or anything
    else on the Wi-Fi, must never see it — armed or not."""
    desktop.state.pairing.set_network_open(True)
    async with client(desktop, PHONE) as http:
        for path in ("/pair", "/pair/qr.svg", "/pair/status"):
            assert (await http.get(path)).status_code == 403, path


async def test_a_forged_post_cannot_arm_the_listener(desktop):
    """Any page the user visits can POST to 127.0.0.1. It cannot read the response, but
    arming the network listener does not require reading anything."""
    async with client(desktop) as http:
        for body in ({"allow": "on"}, {"csrf": "guessed", "allow": "on"}):
            refused = await http.post("/pair/network", data=body)
            assert refused.status_code == 403
            assert refused.json()["error"]["code"] == "E_FORBIDDEN"
    assert desktop.state.pairing.network_open is False


async def test_the_network_is_refused_until_somebody_allows_it(desktop):
    async with client(desktop, PHONE) as phone:
        assert (await phone.get("/readyz")).status_code == 403

    async with client(desktop) as http:
        page = await http.get("/pair")
        token = page.text.split('name="csrf" value="')[1].split('"')[0]
        armed = await http.post("/pair/network", data={"csrf": token, "allow": "on"},
                                follow_redirects=False)
        assert armed.status_code == 303

    async with client(desktop, PHONE) as phone:
        assert (await phone.get("/readyz")).status_code == 200
        assert (await phone.get("/api/v1/version")).json()["server_fingerprint"]


async def test_the_invitation_is_what_the_field_app_will_accept(desktop):
    """apps/mobile/src/api.ts::enrollFromUri validates all of this before it will
    exchange the token, and rejects a server URL carrying a path, query or credentials."""
    invitation = desktop.state.pairing.invitation()
    parsed = urllib.parse.urlparse(invitation["enrollment_uri"])
    query = dict(urllib.parse.parse_qsl(parsed.query))

    assert parsed.scheme == "lmpc"
    assert parsed.hostname == "enroll"
    assert len(query["token"]) >= 20
    assert query["fingerprint"] == desktop.state.auth.server_fingerprint()

    server = urllib.parse.urlparse(query["server"])
    assert server.scheme == "http" and server.port == 8000
    assert not server.path and not server.query and not server.username


async def test_a_phone_can_exchange_the_token_for_a_session(desktop):
    """The end of the story: scan, enroll, and hold a working field-officer session."""
    desktop.state.pairing.set_network_open(True)
    uri = desktop.state.pairing.invitation()["enrollment_uri"]
    token = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(uri).query))["token"]

    async with client(desktop, PHONE) as phone:
        enrolled = await phone.post("/api/v1/auth/enroll",
                                    json={"token": token, "device_name": "Test phone"})
        assert enrolled.status_code == 200, enrolled.text
        session = enrolled.json()
        assert session["user"]["role"] == "FIELD_OFFICER"
        assert session["server_fingerprint"] == desktop.state.auth.server_fingerprint()

        me = await phone.get("/api/v1/auth/me",
                             headers={"Authorization": f"Bearer {session['access_token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == "officer@lmpc.local"

        replayed = await phone.post("/api/v1/auth/enroll",
                                    json={"token": token, "device_name": "Second phone"})
        assert replayed.status_code >= 400, "an enrollment token must be single-use"


async def test_a_reloaded_page_does_not_mint_a_second_live_token(desktop):
    """Tokens are single-use and live fifteen minutes; refreshing the browser should not
    leave a trail of valid ones behind."""
    async with client(desktop) as http:
        first = (await http.get("/pair")).status_code
        assert first == 200
        before = desktop.state.pairing.invitation()["token"]
        await http.get("/pair")
        assert desktop.state.pairing.invitation()["token"] == before


async def test_pairing_does_not_exist_outside_the_desktop_build(tmp_path):
    """The router is mounted only in desktop mode, which is what keeps it out of the
    published contract and out of the RBAC matrix."""
    app = create_app(Settings(storage_root=str(tmp_path / "objects")))
    assert not any(getattr(route, "path", "").startswith("/pair") for route in app.routes)
    async with client(app) as http:
        assert (await http.get("/pair")).status_code == 404


def test_the_csrf_token_is_not_predictable():
    assert len(pairing_api.CSRF_TOKEN) >= 24
