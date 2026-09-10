"""Repository search and append-only officer review workflow."""
from __future__ import annotations

import hashlib
import io
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


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(storage_root=str(tmp_path)))


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, "JPEG")
    return output.getvalue()


async def _request(app, method: str, path: str, **kwargs):
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def _create(app, client_uuid: str):
    raw = _jpeg()
    return await _request(app, "POST", "/api/v1/scans", data={
        "client_uuid": client_uuid, "captured_at": "2026-09-07",
        "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
        "coverage_asserted": "true", "panels": ["FRONT", "BACK"],
        "image_sha256": [hashlib.sha256(raw).hexdigest()] * 2,
    }, files=[("images", ("front.jpg", raw, "image/jpeg")),
              ("images", ("back.jpg", raw, "image/jpeg"))])


async def test_search_correction_history_override_and_finalization_are_coherent(app):
    client_uuid = str(uuid.uuid4())
    created = await _create(app, client_uuid)
    assert created.status_code == 202
    scan_id = created.json()["scan_id"]

    def reader(_data, *, panel, **_kwargs):
        return ([Token("MRP Rs. 45.00 (incl. of all taxes)", 2, 3, 300, 20,
                       conf=0.99, panel=panel)] if panel == "FRONT" else [])

    app.state.pipeline.reader = reader
    first = await _request(app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    assert first.status_code == 202 and len(first.json()["evaluations"]) == 21

    found = await _request(app, "GET", f"/api/v1/scans?q={client_uuid[:12]}&page_size=1")
    assert found.status_code == 200
    assert found.json()["total"] == 1 and found.json()["items"][0]["id"] == scan_id

    correction = await _request(
        app, "POST", f"/api/v1/scans/{scan_id}/declarations/mrp",
        json={"text": "MRP Rs. 49.00 (incl. of all taxes)"})
    assert correction.status_code == 200
    assert correction.json()["declaration"]["corrected_by"]

    second = await _request(app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    corrected = next(item for item in second.json()["declarations"]
                     if item["field"] == "mrp")
    assert corrected["text"].startswith("MRP Rs. 49.00")
    assert corrected["feature_weights"] == {"officer_correction": 100.0}

    old_batch = await _request(
        app, "GET", f"/api/v1/scans/{scan_id}/evaluations?batch=1")
    assert old_batch.status_code == 200 and len(old_batch.json()["evaluations"]) == 21
    current = second.json()["evaluations"]
    target = next(item for item in current if item["outcome"] == "FAIL")
    too_short = await _request(
        app, "POST", f"/api/v1/scans/{scan_id}/evaluations/{target['id']}/override",
        json={"outcome": "PASS", "reason": "too short"})
    assert too_short.status_code == 400
    assert too_short.json()["error"]["code"] == "E_REASON_REQUIRED"

    overridden = await _request(
        app, "POST", f"/api/v1/scans/{scan_id}/evaluations/{target['id']}/override",
        json={"outcome": "PASS", "reason": "Officer verified the declaration manually"})
    assert overridden.status_code == 200
    assert overridden.json()["evaluation"]["override_of_evaluation_id"] == target["id"]
    history = await _request(app, "GET", f"/api/v1/scans/{scan_id}/evaluations")
    assert len(history.json()["evaluations"]) == 22
    assert len(history.json()["effective"]) == 21
    effective = next(item for item in history.json()["effective"]
                     if item["check"] == target["check"])
    assert effective["outcome"] == "PASS" and effective["is_override"] is True

    patched = await _request(
        app, "PATCH", f"/api/v1/scans/{scan_id}",
        json={"package_shape": "CYLINDRICAL",
              "dimensions": {"h_cm": 12.0, "w_cm": 18.0}})
    assert patched.status_code == 200
    assert patched.json()["status"] == "RECEIVED"
    assert patched.json()["reevaluation_required"] is True
    third = await _request(app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    assert next(item for item in third.json()["declarations"]
                if item["field"] == "mrp")["corrected_by"]

    report = await _request(app, "POST", f"/api/v1/scans/{scan_id}/report")
    assert report.status_code == 201
    blocked = await _request(
        app, "POST", f"/api/v1/scans/{scan_id}/declarations/mrp",
        json={"text": "MRP Rs. 50.00 (incl. of all taxes)"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "E_SCAN_FINALIZED"


async def test_patch_rejects_partial_dimensions_and_unknown_fields(app):
    scan_id = (await _create(app, str(uuid.uuid4()))).json()["scan_id"]
    partial = await _request(app, "PATCH", f"/api/v1/scans/{scan_id}",
                             json={"dimensions": {"h_cm": 10}})
    unknown = await _request(app, "PATCH", f"/api/v1/scans/{scan_id}",
                             json={"not_a_field": True})
    assert partial.status_code == 400
    assert unknown.status_code == 422


async def test_dashboard_summarises_effective_scoped_findings(app):
    scan_id = (await _create(app, str(uuid.uuid4()))).json()["scan_id"]

    def reader(_data, *, panel, **_kwargs):
        return ([Token("MRP Rs. 45.00 (incl. of all taxes)", 2, 3, 300, 20,
                       conf=0.99, panel=panel)] if panel == "FRONT" else [])

    app.state.pipeline.reader = reader
    evaluated = await _request(app, "POST", f"/api/v1/scans/{scan_id}/reevaluate")
    assert evaluated.status_code == 202
    summary = await _request(app, "GET", "/api/v1/dashboard/summary")
    violations = await _request(app, "GET", "/api/v1/dashboard/violations-by-type")
    quality = await _request(app, "GET", "/api/v1/dashboard/quality")
    assert summary.json()["total"] == 1
    assert summary.json()["pending_reviews"] == 1
    assert summary.json()["non_compliant"] == 1
    assert summary.json()["violation_rate"] == 1.0
    assert violations.json() and violations.json()[0]["count"] >= 1
    assert quality.json()["declarations_extracted"] >= 1
    assert quality.json()["false_accusation_guard_breaches"] == 0
    metrics = await _request(app, "GET", "/api/v1/metrics")
    assert "lmpc_scan_submitted_total" in metrics.text
    assert 'lmpc_verdict_total{check="' in metrics.text
    assert 'lmpc_pipeline_duration_seconds_count{stage="total"}' in metrics.text
