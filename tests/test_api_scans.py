"""API contract tests (Part 12.3), evidence integrity and start-up refusal."""
from __future__ import annotations

import hashlib
import io
import json
import uuid

import httpx
import pytest
from PIL import Image

from lmpc.engine.model import Token
from lmpc.server.config import Settings
from lmpc.server.main import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    root = tmp_path_factory.mktemp("evidence")
    return create_app(Settings(storage_root=str(root)))


def _jpeg(size=(12, 8)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, "JPEG")
    return out.getvalue()


async def _request(app, method: str, path: str, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def _post(app, client_uuid=None, image_data=None, media_type="image/jpeg", **over):
    panels = over.pop("panels", ["FRONT", "BACK"])
    data = image_data or _jpeg()
    body = {
        "client_uuid": client_uuid or str(uuid.uuid4()),
        "captured_at": "2026-09-07", "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
        "coverage_asserted": "true", "panels": panels,
        "image_sha256": [hashlib.sha256(data).hexdigest()] * len(panels),
    }
    body.update(over)
    files = [("images", (f"{panel}.jpg", data, media_type)) for panel in panels]
    return await _request(app, "POST", "/api/v1/scans", data=body, files=files)


async def test_healthz_and_readyz(app):
    assert (await _request(app, "GET", "/api/v1/healthz")).json() == {"status": "ok"}
    assert (await _request(app, "GET", "/api/v1/readyz")).json() == {"status": "ok"}
    version = (await _request(app, "GET", "/api/v1/version")).json()
    assert version["rulepack_sha256"] and version["current_to"] == "G.S.R. 418(E)"


async def test_submit_scan_persists_hash_addressed_evidence(app):
    response = await _post(app)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "RECEIVED"
    assert body["status_url"].startswith("/api/v1/scans/")
    assert [(image["width"], image["height"]) for image in body["images"]] == [(12, 8)] * 2
    for image in body["images"]:
        assert app.state.object_store.read(image["storage_key"]) == _jpeg()
    assert all(image.data == b"" for image in app.state.scan_store.get(body["scan_id"]).images)


async def test_reevaluate_runs_the_real_rule_engine_and_returns_the_latest_batch(app):
    submitted = (await _post(app, coverage_asserted="false", panels=["FRONT"])).json()

    def reader(_data, *, panel, **_kwargs):
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 2, 3, 300, 20,
                      conf=0.99, panel=panel)]

    app.state.pipeline.reader = reader
    response = await _request(
        app, "POST", f"/api/v1/scans/{submitted['scan_id']}/reevaluate")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "EVALUATION_COMPLETE"
    assert len(body["rulepack"]["sha256"]) == 64
    assert len(body["evaluations"]) == 21
    assert any(item["field"] == "mrp" for item in body["declarations"])


async def test_repeated_client_uuid_is_not_a_duplicate(app):
    same = str(uuid.uuid4())
    first, second = await _post(app, client_uuid=same), await _post(app, client_uuid=same)
    assert first.status_code == 202 and second.status_code == 200
    assert first.json()["scan_id"] == second.json()["scan_id"]
    assert second.json()["duplicate_ignored"] is True


async def test_coverage_asserted_without_the_back_panel_is_rejected(app):
    response = await _post(app, coverage_asserted="true", panels=["FRONT"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "E_COVERAGE_MISMATCH"


async def test_coverage_false_needs_no_back_panel(app):
    response = await _post(app, coverage_asserted="false", panels=["FRONT"])
    assert response.status_code == 202


async def test_hash_mismatch_is_rejected(app):
    response = await _post(app, image_sha256=["0" * 64, "0" * 64])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_VALIDATION"


async def test_mime_spoofing_is_rejected(app):
    response = await _post(app, media_type="image/png")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "E_UNSUPPORTED_MEDIA"


async def test_corrupt_image_is_rejected_even_with_a_matching_hash(app):
    response = await _post(app, image_data=b"\xff\xd8\xffnot-a-jpeg")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "E_UNSUPPORTED_MEDIA"


async def test_pixel_cap_is_enforced(app):
    small_cap = create_app(Settings(storage_root=str(app.state.settings.storage_root),
                                    max_image_pixels=20))
    response = await _post(small_cap, image_data=_jpeg((6, 4)))
    assert response.status_code == 415
    assert "pixel cap" in response.json()["error"]["message"]


async def test_optional_scan_metadata_is_validated_and_retained(app):
    response = await _post(
        app, buyer_type="INSTITUTIONAL", package_shape="CYLINDRICAL",
        dimensions=json.dumps({"h_cm": 12.5, "w_cm": 18, "capacity_cm3": 250}),
        flags=json.dumps({"is_imported": True}), geo=json.dumps({"lat": 28.61, "lng": 77.2}))
    assert response.status_code == 202
    body = response.json()
    assert body["buyer_type"] == "INSTITUTIONAL"
    rec = app.state.scan_store.get(body["scan_id"])
    assert rec.metadata["pdp_h_cm"] == 12.5 and rec.metadata["is_imported"] is True


async def test_listing_mode_requires_listing_text(app):
    response = await _post(app, mode="ECOMMERCE_LISTING")
    assert response.status_code == 400
    assert "listing_text" in response.json()["error"]["message"]


async def test_invalid_geo_is_a_validation_error_not_a_server_error(app):
    response = await _post(app, geo=json.dumps({"lat": "north", "lng": 77.2}))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_VALIDATION"


async def test_unknown_scan_is_404(app):
    response = await _request(app, "GET", "/api/v1/scans/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "E_NOT_FOUND"


async def test_report_finalization_metadata_and_downloads(app):
    submitted = (await _post(app, coverage_asserted="false", panels=["FRONT"])).json()

    def reader(_data, *, panel, **_kwargs):
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 2, 3, 300, 20,
                      conf=0.99, panel=panel)]

    app.state.pipeline.reader = reader
    scan_id = submitted["scan_id"]
    await _request(app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    finalized = await _request(app, "POST", f"/api/v1/scans/{scan_id}/report")
    assert finalized.status_code == 201
    report_id = finalized.json()["report_id"]
    metadata = await _request(app, "GET", f"/api/v1/reports/{report_id}")
    assert metadata.json()["content_sha256"] == finalized.json()["content_sha256"]
    pdf = await _request(app, "GET", f"/api/v1/reports/{report_id}/download?format=pdf")
    docx = await _request(app, "GET", f"/api/v1/reports/{report_id}/download?format=docx")
    assert pdf.content.startswith(b"%PDF-") and pdf.headers["content-type"] == "application/pdf"
    assert docx.content.startswith(b"PK") and "wordprocessingml" in docx.headers["content-type"]
    blocked = await _request(app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "E_SCAN_FINALIZED"
