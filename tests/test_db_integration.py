"""PostgreSQL dialect integration; skipped unless LMPC_TEST_DB_URL is supplied."""
from __future__ import annotations

import hashlib
import io
import os
import uuid

import httpx
import pytest
from PIL import Image

from lmpc.engine.model import Token
from lmpc.server.config import Settings
from lmpc.server.db import sessionmaker_of
from lmpc.server.db.models import Jurisdiction, User
from lmpc.server.main import create_app

DB_URL = os.environ.get("LMPC_TEST_DB_URL", "")
pytestmark = [pytest.mark.anyio,
              pytest.mark.skipif(not DB_URL, reason="set LMPC_TEST_DB_URL")]


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def database_app(tmp_path_factory):
    jurisdiction_id, officer_id = uuid.uuid4(), uuid.uuid4()
    with sessionmaker_of(DB_URL)() as session:
        session.add(Jurisdiction(
            id=jurisdiction_id, name=f"Test {jurisdiction_id}", state="Delhi",
            path=f"test_{jurisdiction_id.hex}"))
        session.add(User(
            id=officer_id, full_name="Integration Officer",
            email=f"officer-{officer_id}@example.test", role="FIELD_OFFICER",
            jurisdiction_id=jurisdiction_id))
        session.commit()
    return create_app(Settings(
        db_url=DB_URL, officer_uuid=str(officer_id), jurisdiction_uuid=str(jurisdiction_id),
        storage_root=str(tmp_path_factory.mktemp("db-evidence"))))


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, "JPEG")
    return output.getvalue()


async def _request(app, method: str, path: str, **kwargs):
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def test_postgres_round_trip_keeps_images_evaluations_and_reports(database_app):
    raw = _jpeg()
    digest = hashlib.sha256(raw).hexdigest()
    client_uuid = str(uuid.uuid4())
    data = {
        "client_uuid": client_uuid, "captured_at": "2026-09-07",
        "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
        "coverage_asserted": "false", "panels": ["FRONT"],
        "image_sha256": [digest],
    }
    files = [("images", ("front.jpg", raw, "image/jpeg"))]
    created = await _request(
        database_app, "POST", "/api/v1/scans", data=data, files=files)
    duplicate = await _request(
        database_app, "POST", "/api/v1/scans", data=data, files=files)
    assert created.status_code == 202 and duplicate.status_code == 200
    assert created.json()["scan_id"] == duplicate.json()["scan_id"]

    def reader(_data, *, panel, **_kwargs):
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 1, 2, 300, 20,
                      conf=0.99, panel=panel)]

    database_app.state.pipeline.reader = reader
    scan_id = created.json()["scan_id"]
    evaluated = await _request(
        database_app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    assert evaluated.status_code == 202
    assert len(evaluated.json()["evaluations"]) == 21
    assert evaluated.json()["images"][0]["max_edge_used"] == 32

    report = await _request(database_app, "POST", f"/api/v1/scans/{scan_id}/report")
    assert report.status_code == 201
    downloaded = await _request(
        database_app, "GET",
        f"/api/v1/reports/{report.json()['report_id']}/download?format=pdf")
    assert downloaded.content.startswith(b"%PDF-")
