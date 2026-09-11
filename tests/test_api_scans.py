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
    health = await _request(app, "GET", "/api/v1/healthz",
                            headers={"X-Request-ID": "contract-test-123"})
    assert health.json() == {"status": "ok"}
    assert health.headers["x-request-id"] == "contract-test-123"
    assert (await _request(app, "GET", "/api/v1/readyz")).json() == {"status": "ok"}
    version = (await _request(app, "GET", "/api/v1/version")).json()
    assert version["rulepack_sha256"] and version["current_to"] == "G.S.R. 418(E)"
    metrics = await _request(app, "GET", "/api/v1/metrics")
    assert metrics.status_code == 200
    assert "lmpc_fail_without_coverage_total 0" in metrics.text
    assert "lmpc_chain_incomplete 1" in metrics.text


async def test_rule_explainer_is_available_for_every_review_card(app):
    detail = await _request(app, "GET", "/api/v1/rules/LMPC-R6-1-E-MRP")
    assert detail.status_code == 200
    assert detail.json()["clause"] == "Rule 6(1)(e)"
    assert "maximum retail price" in detail.json()["requirement"].lower()
    missing = await _request(app, "GET", "/api/v1/rules/unknown")
    assert missing.status_code == 404


async def test_readyz_reports_a_failed_dependency(app):
    original = app.state.object_store.ready
    app.state.object_store.ready = lambda: False
    try:
        response = await _request(app, "GET", "/api/v1/readyz")
    finally:
        app.state.object_store.ready = original
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"rulepack": True, "database": True, "object_store": False},
    }


async def test_local_api_rate_limit_has_a_structured_429(tmp_path):
    limited = create_app(Settings(storage_root=str(tmp_path), rate_limit_per_min=2))
    first = await _request(limited, "GET", "/api/v1/version")
    second = await _request(limited, "GET", "/api/v1/version")
    blocked = await _request(limited, "GET", "/api/v1/version")
    assert first.status_code == second.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert blocked.json()["error"]["code"] == "E_RATE_LIMITED"


async def test_submit_scan_persists_hash_addressed_evidence(app):
    response = await _post(app)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "RECEIVED"
    assert body["status_url"].startswith("/api/v1/scans/")
    assert [(image["width"], image["height"]) for image in body["images"]] == [(12, 8)] * 2
    for image in body["images"]:
        assert app.state.object_store.read(image["storage_key"]) == _jpeg()
        served = await _request(app, "GET", image["url"])
        assert served.content == _jpeg()
        assert served.headers["content-type"] == "image/jpeg"
        assert served.headers["etag"] == f'"{image["sha256"]}"'
    assert all(image.data == b"" for image in app.state.scan_store.get(body["scan_id"]).images)


async def test_panel_labels_must_be_unique(app):
    response = await _post(app, panels=["FRONT", "FRONT"])
    assert response.status_code == 400
    assert "only be uploaded once" in response.json()["error"]["message"]


async def test_capture_pwa_is_served_by_the_api_process(app):
    page = await _request(app, "GET", "/")
    manifest = await _request(app, "GET", "/manifest.webmanifest")
    assert page.status_code == 200 and "LMPC Field Capture" in page.text
    assert manifest.status_code == 200 and manifest.json()["start_url"] == "/"
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert "unsafe-inline" not in page.headers["content-security-policy"]
    assert page.headers["permissions-policy"] == "camera=(self), geolocation=(self)"


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


async def test_image_quality_is_recorded_per_image(app):
    quality = json.dumps({
        "source": "CAMERA", "sharpness": 132.5, "mean_luma": 141.0,
        "glare_fraction": 0.012, "warnings": [],
    })
    response = await _post(app, image_quality=[quality, quality])
    assert response.status_code == 202
    body = response.json()
    assert all(image["quality"]["sharpness"] == 132.5 for image in body["images"])


async def test_image_quality_is_optional_and_defaults_to_none(app):
    response = await _post(app)
    assert response.status_code == 202
    assert all(image["quality"] is None for image in response.json()["images"])


async def test_image_quality_rejects_unknown_keys_and_bad_values(app):
    response = await _post(app, image_quality=[
        json.dumps({"sharpness": 10, "cheated": True}),
        json.dumps({"sharpness": 10}),
    ])
    assert response.status_code == 400
    assert "unknown keys" in response.json()["error"]["message"]

    out_of_range = json.dumps({"glare_fraction": 1.5})
    response = await _post(app, image_quality=[out_of_range, out_of_range])
    assert response.status_code == 400
    assert "glare_fraction" in response.json()["error"]["message"]


async def test_listing_mode_requires_listing_text(app):
    response = await _post(app, mode="ECOMMERCE_LISTING")
    assert response.status_code == 400
    assert "listing_text" in response.json()["error"]["message"]


async def test_listing_mode_processes_pasted_text_and_keeps_screenshots_distinct(app):
    response = await _post(
        app, mode="ECOMMERCE_LISTING", coverage_asserted="false",
        panels=["LISTING", "LISTING_2"],
        ecommerce=json.dumps({
            "url": "https://shop.example.test/product/45",
            "listing_text": "MRP Rs. 45.00 (incl. of all taxes)\nNet Qty 500 g",
        }))
    assert response.status_code == 202
    body = response.json()
    assert body["ecommerce"]["url"] == "https://shop.example.test/product/45"
    assert body["coverage_asserted"] is False

    original = app.state.pipeline.reader
    app.state.pipeline.reader = lambda *_args, **_kwargs: []
    try:
        processed = await _request(
            app, "POST", f"/api/v1/scans/{body['scan_id']}/process")
    finally:
        app.state.pipeline.reader = original
    assert processed.status_code == 202
    findings = {item["check"]: item["outcome"]
                for item in processed.json()["evaluations"]}
    assert findings["LMPC-R6-1-E-MRP"] == "PASS"
    assert findings["LMPC-R6-1-D-MFG-DATE"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("values", [
    {"mode": "ECOMMERCE_LISTING", "coverage_asserted": "true",
     "panels": ["LISTING"],
     "ecommerce": json.dumps({"listing_text": "MRP Rs. 45"})},
    {"mode": "PHYSICAL_PACKAGE", "coverage_asserted": "false",
     "panels": ["LISTING"]},
])
async def test_scan_mode_rejects_the_other_modes_evidence_labels(app, values):
    response = await _post(app, **values)
    assert response.status_code in {400, 409}


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "https://user:secret@shop.example.test/product",
    "https://:secret@shop.example.test/product",
    "shop.example.test/product",
])
async def test_listing_mode_rejects_unsafe_source_urls(app, url):
    response = await _post(
        app, mode="ECOMMERCE_LISTING", coverage_asserted="false",
        panels=["LISTING"],
        ecommerce=json.dumps({"url": url, "listing_text": "MRP Rs. 45"}))
    assert response.status_code == 400
    assert "HTTP(S)" in response.json()["error"]["message"]


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


async def _deferred_begin(app, client_uuid=None, **over):
    body = {
        "client_uuid": client_uuid or str(uuid.uuid4()),
        "captured_at": "2026-09-07", "mode": "PHYSICAL_PACKAGE", "category": "FOOD",
        "coverage_asserted": "true", "panels": ["FRONT", "BACK"],
    }
    body.update(over)
    return await _request(app, "POST", "/api/v1/scans/deferred", data=body)


def _panel_form(panel: str, data: bytes, quality: str | None = None):
    form = {
        "panel": panel, "image_sha256": hashlib.sha256(data).hexdigest(),
        "image_quality": quality,
    }
    files = {"image": (f"{panel.lower()}.jpg", data, "image/jpeg")}
    return form, files


@pytest.fixture()
def deferred_app(tmp_path):
    """A fresh app: the deferred tests are request-heavy and would trip the shared
    module-scoped app's per-minute rate limit."""
    return create_app(Settings(storage_root=str(tmp_path), rate_limit_per_min=10_000))


async def test_deferred_begin_declares_a_scan_without_images(deferred_app):
    first, second = (await _deferred_begin(deferred_app, client_uuid=(same := str(uuid.uuid4()))),
                     await _deferred_begin(deferred_app, client_uuid=same))
    assert first.status_code == 202
    body = first.json()
    assert body["status"] == "RECEIVED"
    assert body["panels_captured"] == ["FRONT", "BACK"]
    assert body["images"] == []
    assert second.status_code == 200
    assert second.json()["scan_id"] == body["scan_id"]
    assert second.json()["duplicate_ignored"] is True


async def test_deferred_scan_takes_each_panel_on_its_own_request(deferred_app):
    begun = (await _deferred_begin(deferred_app)).json()
    form, files = _panel_form("FRONT", _jpeg())
    appended = await _request(deferred_app, "POST", f"/api/v1/scans/{begun['scan_id']}/images",
                              data=form, files=files)
    assert appended.status_code == 201
    assert appended.json()["duplicate_ignored"] is False
    # the same panel resending the same bytes is accepted and ignored
    resent = await _request(deferred_app, "POST", f"/api/v1/scans/{begun['scan_id']}/images",
                            data=form, files=files)
    assert resent.status_code == 200
    assert resent.json()["duplicate_ignored"] is True
    assert len(begun["panels_captured"]) == 2
    stored = deferred_app.state.scan_store.get(begun["scan_id"])
    assert [image.panel_label for image in stored.images] == ["FRONT"]


async def test_deferred_scan_conflicts_when_a_panel_gets_different_evidence(deferred_app):
    begun = (await _deferred_begin(deferred_app)).json()
    form, files = _panel_form("FRONT", _jpeg())
    await _request(deferred_app, "POST", f"/api/v1/scans/{begun['scan_id']}/images",
                   data=form, files=files)
    clash, clash_files = _panel_form("FRONT", _jpeg((20, 10)))
    response = await _request(deferred_app, "POST", f"/api/v1/scans/{begun['scan_id']}/images",
                              data=clash, files=clash_files)
    assert response.status_code == 409
    assert "different evidence" in response.json()["error"]["message"]


async def test_deferred_scan_rejects_undeclared_and_duplicate_panels(deferred_app):
    begun = (await _deferred_begin(deferred_app)).json()
    form, files = _panel_form("SIDE_1", _jpeg())
    response = await _request(deferred_app, "POST", f"/api/v1/scans/{begun['scan_id']}/images",
                              data=form, files=files)
    assert response.status_code == 400
    assert "was not declared" in response.json()["error"]["message"]


async def test_complete_upload_requires_every_declared_panel(deferred_app):
    begun = (await _deferred_begin(deferred_app)).json()
    scan_id = begun["scan_id"]
    response = await _request(deferred_app, "POST", f"/api/v1/scans/{scan_id}/complete-upload")
    assert response.status_code == 400
    assert "missing uploaded panels: ['BACK', 'FRONT']" in response.json()["error"]["message"]
    form, files = _panel_form("FRONT", _jpeg())
    await _request(deferred_app, "POST", f"/api/v1/scans/{scan_id}/images", data=form, files=files)
    still_missing = await _request(
        deferred_app, "POST", f"/api/v1/scans/{scan_id}/complete-upload")
    assert "BACK" in still_missing.json()["error"]["message"]
    process = await _request(deferred_app, "POST", f"/api/v1/scans/{scan_id}/process")
    assert process.status_code == 400
    assert "missing uploaded panels" in process.json()["error"]["message"]


async def test_deferred_scan_processes_once_every_panel_has_arrived(deferred_app):
    begun = (await _deferred_begin(deferred_app)).json()
    scan_id = begun["scan_id"]

    def reader(_data, *, panel, **_kwargs):
        if panel == "BACK":
            return [Token("Net Qty 500 g", 4, 3, 300, 20, conf=0.99, panel=panel)]
        return [Token("MRP Rs. 45.00 (incl. of all taxes)", 2, 3, 300, 20,
                      conf=0.99, panel=panel)]

    deferred_app.state.pipeline.reader = reader
    try:
        quality = json.dumps({"source": "CAMERA", "sharpness": 90.0,
                              "mean_luma": 128.0, "glare_fraction": 0.0,
                              "warnings": []})
        for panel in ("FRONT", "BACK"):
            form, files = _panel_form(panel, _jpeg(), quality=quality)
            upload = await _request(
                deferred_app, "POST", f"/api/v1/scans/{scan_id}/images", data=form, files=files)
            assert upload.status_code == 201
        completed = await _request(
            deferred_app, "POST", f"/api/v1/scans/{scan_id}/complete-upload")
        assert completed.status_code == 202
        assert completed.json()["status"] == "RECEIVED"
        processed = await _request(deferred_app, "POST", f"/api/v1/scans/{scan_id}/process")
    finally:
        deferred_app.state.pipeline.reader = None
    assert processed.status_code == 202
    body = processed.json()
    assert body["status"] == "EVALUATION_COMPLETE"
    assert all(image["quality"]["source"] == "CAMERA" for image in body["images"])
    assert any(item["field"] == "mrp" for item in body["declarations"])


async def test_deferred_begin_rejects_a_bad_declaration(deferred_app):
    response = await _deferred_begin(deferred_app, panels=["FRONT", "FRONT"])
    assert response.status_code == 400
    assert "only be uploaded once" in response.json()["error"]["message"]
    response = await _deferred_begin(deferred_app, client_uuid="not-a-uuid")
    assert response.status_code == 400
