"""Optional TLS: a self-signed certificate whose pin travels with the QR.

Cleartext HTTP is the preview posture; TLS is opt-in and only useful once a phone pins
the certificate. These tests pin the server half: the certificate is generated once and
stably, it names the addresses a phone could dial, and the pin reaches both /version and
the enrollment URI — the same out-of-band channel as the fingerprint.
"""
from __future__ import annotations

import urllib.parse

import httpx
import pytest

from lmpc.server.config import Settings
from lmpc.server.db import desktop_bootstrap
from lmpc.server.main import create_app
from lmpc.server.svc.pairing import PairingService
from lmpc.server.tls import configured_pin, ensure_certificate, spki_sha256

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client(app, peer=("127.0.0.1", 50000)) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=peer),
        base_url="http://testserver")


def test_the_certificate_is_generated_once_and_survives_a_restart(tmp_path):
    first = ensure_certificate(tmp_path, addresses=["192.168.1.20"])
    assert first["tls_pin"]
    generated_at = (tmp_path / "server.pem").stat().st_mtime_ns
    assert (tmp_path / "server-key.pem").stat().st_mode & 0o777 == 0o600

    again = ensure_certificate(tmp_path, addresses=["192.168.1.20"])
    assert again == first
    assert (tmp_path / "server.pem").stat().st_mtime_ns == generated_at
    assert spki_sha256(tmp_path / "server.pem") == first["tls_pin"]


def test_a_different_certificate_carries_a_different_pin(tmp_path):
    one = ensure_certificate(tmp_path / "one", addresses=["192.168.1.20"])
    two = ensure_certificate(tmp_path / "two", addresses=["192.168.1.20"])
    assert one["tls_pin"] != two["tls_pin"]


def test_the_certificate_names_what_a_phone_could_dial(tmp_path):
    ensure_certificate(tmp_path, addresses=["192.168.1.20", "not-an-address"])
    from cryptography import x509

    cert = x509.load_pem_x509_certificate((tmp_path / "server.pem").read_bytes())
    names = cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
    assert any(str(address) == "192.168.1.20" for address in names)
    # An unparsable address is skipped, never fatal: pairing must survive a machine
    # whose interfaces list includes something odd.
    assert any(str(address) == "127.0.0.1" for address in names)


@pytest.fixture()
def tls_desktop(tmp_path, monkeypatch):
    material = ensure_certificate(tmp_path / "tls", addresses=["192.168.1.20"])
    data_root = tmp_path / "portable"
    data_root.mkdir()
    db_url = f"sqlite+pysqlite:///{data_root / 'lmpc.sqlite3'}"
    monkeypatch.setenv("LMPC_JWT_KEY_PATH", str(data_root / "jwt.pem"))
    record = desktop_bootstrap.run(data_root, db_url)
    app = create_app(Settings(
        db_url=db_url, auth_mode="local", desktop_mode=True,
        storage_root=str(data_root / "objects"),
        jwt_key_path=str(data_root / "jwt.pem"),
        tls_cert=material["cert"], tls_key=material["key"],
        officer_uuid=record["officer"]["id"],
        jurisdiction_uuid=record["jurisdiction_id"]))
    app.state.pairing = PairingService(app.state.accounts, app.state.auth, record, 8000,
                                       scheme="https")
    return app, material


async def test_the_pin_reaches_the_version_endpoint_and_the_qr(tls_desktop):
    app, material = tls_desktop
    assert configured_pin(app.state.settings) == material["tls_pin"]
    async with client(app) as http:
        body = (await http.get("/api/v1/version")).json()
    assert body["tls_pin"] == material["tls_pin"]

    invitation = app.state.pairing.invitation()
    fields = urllib.parse.parse_qs(urllib.parse.urlparse(invitation["enrollment_uri"]).query)
    assert fields["tls_pin"] == [material["tls_pin"]]
    assert fields["fingerprint"] == [invitation["server_fingerprint"]]


async def test_without_tls_the_qr_and_the_version_stay_as_they_were(tmp_path):
    data_root = tmp_path / "portable"
    data_root.mkdir()
    db_url = f"sqlite+pysqlite:///{data_root / 'lmpc.sqlite3'}"
    monkey = pytest.MonkeyPatch()
    monkey.setenv("LMPC_JWT_KEY_PATH", str(data_root / "jwt.pem"))
    try:
        record = desktop_bootstrap.run(data_root, db_url)
        app = create_app(Settings(
            db_url=db_url, auth_mode="local", desktop_mode=True,
            storage_root=str(data_root / "objects"),
            jwt_key_path=str(data_root / "jwt.pem"),
            officer_uuid=record["officer"]["id"],
            jurisdiction_uuid=record["jurisdiction_id"]))
        app.state.pairing = PairingService(app.state.accounts, app.state.auth, record, 8000)
        async with client(app) as http:
            assert "tls_pin" not in (await http.get("/api/v1/version")).json()
        fields = urllib.parse.parse_qs(urllib.parse.urlparse(
            app.state.pairing.invitation()["enrollment_uri"]).query)
        assert "tls_pin" not in fields
        assert app.state.pairing.advertised_url().startswith("http://")
    finally:
        monkey.undo()


def test_an_advertised_https_url_is_left_alone(tmp_path):
    """--public-url https://… already meant HTTPS before TLS existed; the typed-address
    path must keep accepting it."""
    from lmpc.server.net import normalise_base_url

    assert normalise_base_url("https://lmpc.example.gov.in") == \
        "https://lmpc.example.gov.in"