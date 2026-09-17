"""Connecting a phone to the portable build, with nothing else installed.

The shipped preview could not pair at all: it ran with authentication disabled, so
AccountService refused to manage accounts and the executable could not mint an enrollment
even in principle. These tests pin the replacement — and, just as importantly, pin the
three gates that keep a credential-bearing page off the network.
"""
from __future__ import annotations

import sys
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
def addresses(monkeypatch):
    """Pin what this machine appears to hold.

    Otherwise these tests pass or fail on whether the machine running them has Wi-Fi, a
    VPN, or Docker — and the VPN case is precisely the bug being pinned.
    """
    from lmpc.server import net
    from lmpc.server.ifaces import Interface

    found = [
        Interface("wlan0", "192.168.1.20", 24, point_to_point=False, running=True),
        Interface("CloudflareWARP", "172.16.0.2", 32, point_to_point=True, running=True),
        Interface("docker0", "172.17.0.1", 16, point_to_point=False, running=False),
    ]
    monkeypatch.setattr(net, "enumerate_ipv4", lambda: list(found))
    monkeypatch.setattr(net, "routed_address", lambda: "172.16.0.2")
    return found


@pytest.fixture()
def desktop(tmp_path, monkeypatch, addresses):
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


@pytest.fixture()
def desktop_service(desktop):
    """What `lmpc/desktop.py --allow-phones --public-url ...` builds."""
    return PairingService(desktop.state.accounts, desktop.state.auth,
                          desktop.state.pairing.credentials, 8000,
                          advertised="https://lmpc.example.gov.in", network_open=True)


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


def test_a_server_without_the_qr_library_still_starts(tmp_path, monkeypatch):
    """segno is a desktop-only dependency, imported inside the two functions that draw a
    code. A departmental deployment that never mounts the pairing page must not fail to
    start for want of it — which is exactly how this shipped broken: an import at module
    scope took down every route in the application.
    """
    import builtins

    real_import = builtins.__import__

    def refuse_segno(name, *args, **kwargs):
        if name == "segno":
            raise ModuleNotFoundError("No module named 'segno'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_segno)
    for module in [name for name in sys.modules if name.startswith("lmpc.server")]:
        monkeypatch.delitem(sys.modules, module, raising=False)

    from lmpc.server.main import create_app as rebuilt

    # Constructing the application is the invariant: it imports every router, including
    # the pairing one, whether or not the pairing routes are mounted.
    app = rebuilt(Settings(storage_root=str(tmp_path / "objects")))
    assert app.title == "LMPC Compliance API"


# ---- the address in the code --------------------------------------------------------

async def test_the_code_carries_a_reachable_address_not_the_vpn(desktop):
    """The shipped failure, end to end.

    With a VPN holding the default route, the old code advertised the tunnel's /32. The
    QR was valid, the server was running, and every phone that scanned it reported that
    it could not reach the server — which reads as "we are on different networks".
    """
    invitation = desktop.state.pairing.invitation()
    assert invitation["server_url"] == "http://192.168.1.20:8000"
    assert "172.16.0.2" not in invitation["enrollment_uri"]


async def test_the_page_shows_what_else_it_found_and_why_it_was_passed_over(desktop):
    """An officer whose phone still cannot connect needs to see the alternatives."""
    async with client(desktop) as http:
        page = (await http.get("/pair")).text
    assert "http://192.168.1.20:8000" in page
    assert "172.16.0.2" in page and "VPN / tunnel" in page
    assert "172.17.0.1" in page and "Container network" in page
    assert 'name="custom"' in page, "an address can be typed for a server elsewhere"


async def test_an_officer_can_point_the_code_at_a_remote_server(desktop):
    """The server is not always in the room. A public host name has to be acceptable,
    and the invitation has to be re-minted to carry it — a stale one keeps handing out
    the address that was just corrected."""
    before = desktop.state.pairing.invitation()["token"]
    async with client(desktop) as http:
        token = (await http.get("/pair")).text.split('name="csrf" value="')[1].split('"')[0]
        saved = await http.post("/pair/address",
                                data={"csrf": token, "custom": "https://lmpc.example.gov.in"},
                                follow_redirects=False)
        assert saved.status_code == 303

    invitation = desktop.state.pairing.invitation()
    assert invitation["server_url"] == "https://lmpc.example.gov.in"
    assert invitation["token"] != before, "the code must carry the new address"
    assert desktop.state.pairing.overridden


async def test_an_officer_can_choose_a_different_local_address(desktop):
    """Detection cannot always be right — a laptop with two live networks has to be told
    which one the phone is on."""
    async with client(desktop) as http:
        token = (await http.get("/pair")).text.split('name="csrf" value="')[1].split('"')[0]
        await http.post("/pair/address", data={"csrf": token, "choice": "172.16.0.2"},
                        follow_redirects=False)
    assert desktop.state.pairing.invitation()["server_url"] == "http://172.16.0.2:8000"

    async with client(desktop) as http:
        token = (await http.get("/pair")).text.split('name="csrf" value="')[1].split('"')[0]
        await http.post("/pair/address", data={"csrf": token, "reset": "on"},
                        follow_redirects=False)
    assert desktop.state.pairing.invitation()["server_url"] == "http://192.168.1.20:8000"


async def test_an_address_the_app_would_refuse_is_refused_on_the_page(desktop):
    """Better a message on the page than a phone that has already scanned the code."""
    async with client(desktop) as http:
        token = (await http.get("/pair")).text.split('name="csrf" value="')[1].split('"')[0]
        refused = await http.post("/pair/address",
                                  data={"csrf": token, "custom": "http://box/api/v1"},
                                  follow_redirects=False)
        assert refused.status_code == 303
        assert "error=" in refused.headers["location"]
        page = (await http.get(refused.headers["location"])).text
        assert "must not carry a path" in page
    assert desktop.state.pairing.invitation()["server_url"] == "http://192.168.1.20:8000"


async def test_a_forged_post_cannot_move_the_address(desktop):
    """Same reasoning as the network switch: a page the user visits can POST here."""
    async with client(desktop) as http:
        for body in ({"custom": "http://evil.test"},
                     {"csrf": "guessed", "custom": "http://evil.test"}):
            assert (await http.post("/pair/address", data=body)).status_code == 403
    assert desktop.state.pairing.invitation()["server_url"] == "http://192.168.1.20:8000"


async def test_a_machine_with_no_usable_address_still_renders_the_page(desktop, monkeypatch):
    """The one screen that can fix the problem must not be taken down by it.

    Minting an enrollment with no address raises E_VALIDATION, which used to 500 the
    whole page — so a laptop with its Wi-Fi off showed an error instead of the form for
    typing the address of a server somewhere else.
    """
    from lmpc.server import net
    monkeypatch.setattr(net, "enumerate_ipv4", list)
    monkeypatch.setattr(net, "routed_address", lambda: None)
    desktop.state.pairing.clear_advertised()

    async with client(desktop) as http:
        page = await http.get("/pair")
        assert page.status_code == 200
        assert 'name="custom"' in page.text
        assert "no network address at all" in page.text
        assert (await http.get("/pair/qr.svg")).status_code == 400


# ---- telling the officer what is actually happening ---------------------------------

async def test_a_refused_phone_is_reported_on_the_page(desktop):
    """A phone dialling the right address and being refused looks identical, from the
    officer's side, to a phone that cannot find the machine at all."""
    async with client(desktop, PHONE) as phone:
        assert (await phone.get("/readyz")).status_code == 403

    async with client(desktop) as http:
        page = (await http.get("/pair")).text
        assert "192.168.1.55" in page and "was refused" in page
        status = (await http.get("/pair/status")).json()
        assert status["last_contact"]["peer"] == "192.168.1.55"
        assert status["last_contact"]["allowed"] is False


async def test_an_accepted_phone_is_reported_too(desktop):
    desktop.state.pairing.set_network_open(True)
    async with client(desktop, PHONE) as phone:
        assert (await phone.get("/readyz")).status_code == 200

    async with client(desktop) as http:
        contact = (await http.get("/pair/status")).json()["last_contact"]
        assert contact["allowed"] is True and contact["peer"] == "192.168.1.55"


async def test_nothing_is_reported_before_anything_reaches_the_machine(desktop):
    async with client(desktop) as http:
        assert (await http.get("/pair/status")).json()["last_contact"] is None
        assert "reached this computer yet" in (await http.get("/pair")).text


async def test_the_code_is_reminted_when_the_network_changes(desktop, monkeypatch):
    """Wi-Fi changes under a running server. Without this, an officer who joins the right
    network still scans a code pointing at the one they left."""
    assert desktop.state.pairing.invitation()["server_url"] == "http://192.168.1.20:8000"

    from lmpc.server import net
    from lmpc.server.ifaces import Interface
    monkeypatch.setattr(net, "enumerate_ipv4", lambda: [
        Interface("wlan0", "10.42.0.7", 24, point_to_point=False, running=True)])
    monkeypatch.setattr(net, "routed_address", lambda: "10.42.0.7")

    assert desktop.state.pairing.invitation()["server_url"] == "http://10.42.0.7:8000"


async def test_a_server_nobody_sits_at_can_start_already_open(desktop_service):
    """A server at a remote location has no one to click 'Allow phone connections', and
    no local address worth advertising. Both have to be settable at start-up."""
    assert desktop_service.network_open is True
    assert desktop_service.advertised_url() == "https://lmpc.example.gov.in"
    assert desktop_service.invitation()["server_url"] == "https://lmpc.example.gov.in"
    assert desktop_service.overridden
