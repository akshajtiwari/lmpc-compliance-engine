"""API contract tests (Part 12.3) and the start-up refusal semantics."""
import io
import uuid
import pytest
from fastapi.testclient import TestClient

from lmpc.server.main import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _post(client, client_uuid=None, **over):
    body = dict(
        client_uuid=client_uuid or str(uuid.uuid4()),
        captured_at="2026-09-07", mode="PHYSICAL_PACKAGE", category="FOOD",
        coverage_asserted="true", panels=["FRONT", "BACK"],
    )
    body.update(over)
    files = [("images", (n, io.BytesIO(b"jpeg"), "image/jpeg")) for n in body["panels"]]
    return client.post("/api/v1/scans", data=body, files=files)


def test_healthz_and_readyz(client):
    assert client.get("/api/v1/healthz").json() == {"status": "ok"}
    assert client.get("/api/v1/readyz").json() == {"status": "ok"}
    v = client.get("/api/v1/version").json()
    assert v["rulepack_sha256"] and v["current_to"] == "G.S.R. 418(E)"


def test_submit_scan_is_accepted(client):
    r = _post(client)
    assert r.status_code == 202
    assert r.json()["status"] == "SUBMITTED" and r.json()["status_url"].startswith("/api/v1/scans/")


def test_repeated_client_uuid_is_not_a_duplicate(client):
    same = str(uuid.uuid4())
    a, b = _post(client, client_uuid=same), _post(client, client_uuid=same)
    assert a.status_code == 202 and b.status_code == 200
    assert a.json()["scan_id"] == b.json()["scan_id"]
    assert b.json()["duplicate_ignored"] is True


def test_coverage_asserted_without_the_back_panel_is_rejected(client):
    r = _post(client, coverage_asserted="true", panels=["FRONT"])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "E_COVERAGE_MISMATCH"


def test_coverage_false_needs_no_back_panel(client):
    r = _post(client, coverage_asserted="false", panels=["FRONT"])
    assert r.status_code == 202


def test_unknown_scan_is_404(client):
    r = client.get("/api/v1/scans/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "E_NOT_FOUND"