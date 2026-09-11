"""Deferred field-intake routes (plan §8 item 9).

The phone declares an inspection, uploads each panel image on its own request so a
flaky network resumes instead of restarting, and calls complete-upload when every
declared panel has arrived. Routes declare; ScanService decides."""
from __future__ import annotations
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ..svc.evidence import validate_image
from ..svc.scan_fields import validate_image_quality, validate_metadata
from ..svc.scan_service import validate_deferred, validate_panel_mode
from ..svc.auth import Principal
from ..obs import metrics
from .auth import require
from .scan_payload import envelope, json_object

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/deferred", status_code=202)
async def create_deferred_scan(
    request: Request,
    client_uuid: str = Form(...),
    captured_at: str = Form(...),
    mode: str = Form(...),
    category: str = Form(...),
    coverage_asserted: bool = Form(...),
    panels: list[str] = Form(...),
    buyer_type: str = Form("RETAIL"),
    package_shape: str = Form("RECTANGULAR"),
    scale_reference: str | None = Form(None),
    dimensions: str | None = Form(None),
    flags: str | None = Form(None),
    geo: str | None = Form(None),
    ecommerce: str | None = Form(None),
    principal: Principal = Depends(require("scans:create")),
) -> JSONResponse:
    """Declare a field inspection without images.

    A repeated client_uuid returns the existing scan, so the retry that timed out
    on a rural network never creates a second inspection.
    """
    validate_deferred(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                      category=category, coverage_asserted=coverage_asserted,
                      panels=panels)
    metadata = validate_metadata(
        mode=mode, buyer_type=buyer_type, package_shape=package_shape,
        scale_reference=json_object(scale_reference, "scale_reference"),
        dimensions=json_object(dimensions, "dimensions"),
        flags=json_object(flags, "flags"), geo=json_object(geo, "geo"),
        ecommerce=json_object(ecommerce, "ecommerce"))
    validate_panel_mode(
        mode=mode, coverage_asserted=coverage_asserted, panels=panels)
    svc = request.app.state.scan_store
    rec, created = svc.begin(
        client_uuid=client_uuid, captured_at=captured_at, mode=mode, category=category,
        coverage_asserted=coverage_asserted, panels=panels, metadata=metadata,
        officer_id=principal.id, jurisdiction_id=principal.jurisdiction_id)
    if created:
        metrics.inc("lmpc_scan_submitted_total")
        request.app.state.auth.audit_action(
            principal, "scan", rec.id, "SCAN_CREATE",
            {"client_uuid": rec.client_uuid, "category": rec.category,
             "mode": rec.mode, "deferred": True})
    return JSONResponse(envelope(rec, created), status_code=202 if created else 200)


@router.post("/{scan_id}/images", status_code=201)
async def append_scan_image(
    scan_id: str, request: Request,
    panel: str = Form(...),
    image_sha256: str = Form(...),
    image: UploadFile = File(...),
    image_quality: str | None = Form(None),
    principal: Principal = Depends(require("scans:create")),
) -> JSONResponse:
    """Upload one declared panel image idempotently."""
    rec = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, rec)
    quality = validate_image_quality(
        [json_object(image_quality, "image_quality")] if image_quality else None, 1)[0]
    settings = request.app.state.settings
    data = await image.read(settings.max_image_bytes + 1)
    item = validate_image(
        data=data, filename=image.filename or f"{panel.lower()}.jpg",
        media_type=image.content_type or "", expected_sha256=image_sha256,
        max_bytes=settings.max_image_bytes, max_pixels=settings.max_image_pixels,
    ).on_panel(panel).with_quality(quality)
    request.app.state.object_store.put_immutable(
        item.storage_key, item.data, item.media_type, item.sha256)
    result = request.app.state.scan_store.add_image(scan_id, panel, item)
    request.app.state.auth.audit_action(
        principal, "scan", rec.id, "SCAN_IMAGE_APPEND",
        {"panel": panel, "sha256": item.sha256,
         "duplicate_ignored": result["duplicate_ignored"]})
    return JSONResponse(result, status_code=200 if result["duplicate_ignored"] else 201)


@router.post("/{scan_id}/complete-upload")
async def complete_scan_upload(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("scans:create")),
) -> JSONResponse:
    """Confirm that every declared panel image has arrived."""
    rec = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, rec)
    rec = request.app.state.scan_store.complete_upload(scan_id)
    request.app.state.auth.audit_action(
        principal, "scan", rec.id, "SCAN_UPLOAD_COMPLETE", {})
    return JSONResponse(envelope(rec, created=True), status_code=202)
