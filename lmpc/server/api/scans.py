"""Scans routes (Part 12.3). Routes declare; ScanService decides.

Every image is validated, hash-verified and persisted before processing is accepted."""
from __future__ import annotations
import mimetypes
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..svc.evidence import validate_image
from ..svc.scan_fields import validate_image_quality, validate_metadata
from ..svc.scan_service import validate, validate_panel_mode
from ..svc.auth import Principal
from ..obs import metrics
from .auth import require
from .errors import ApiError
from .scan_payload import envelope, json_object

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("")
async def create_scan(
    request: Request,
    client_uuid: str = Form(...),
    captured_at: str = Form(...),
    mode: str = Form(...),
    category: str = Form(...),
    coverage_asserted: bool = Form(...),
    buyer_type: str = Form("RETAIL"),
    package_shape: str = Form("RECTANGULAR"),
    scale_reference: str | None = Form(None),
    dimensions: str | None = Form(None),
    flags: str | None = Form(None),
    geo: str | None = Form(None),
    ecommerce: str | None = Form(None),
    panels: list[str] = Form(...),
    images: list[UploadFile] = File(...),
    image_sha256: list[str] = Form(...),
    image_quality: list[str] | None = Form(None),
    principal: Principal = Depends(require("scans:create")),
) -> JSONResponse:
    validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
             category=category, coverage_asserted=coverage_asserted, panels=panels,
             n_images=len(images))
    metadata = validate_metadata(
        mode=mode, buyer_type=buyer_type, package_shape=package_shape,
        scale_reference=json_object(scale_reference, "scale_reference"),
        dimensions=json_object(dimensions, "dimensions"),
        flags=json_object(flags, "flags"), geo=json_object(geo, "geo"),
        ecommerce=json_object(ecommerce, "ecommerce"))
    validate_panel_mode(
        mode=mode, coverage_asserted=coverage_asserted, panels=panels)
    if len(image_sha256) != len(images):
        raise ApiError("E_VALIDATION", "one image_sha256 is required per image")
    quality = validate_image_quality(
        None if image_quality is None else
        [json_object(item, "image_quality") for item in image_quality], len(images))
    settings = request.app.state.settings
    evidence = []
    for panel, upload, digest, quality_report in zip(
            panels, images, image_sha256, quality, strict=True):
        data = await upload.read(settings.max_image_bytes + 1)
        item = validate_image(
            data=data, filename=upload.filename or "image",
            media_type=upload.content_type or "", expected_sha256=digest,
            max_bytes=settings.max_image_bytes, max_pixels=settings.max_image_pixels,
        ).on_panel(panel).with_quality(quality_report)
        evidence.append(item)
    for item in evidence:
        request.app.state.object_store.put_immutable(
            item.storage_key, item.data, item.media_type, item.sha256)
    evidence = [item.without_data() for item in evidence]
    svc = request.app.state.scan_store
    rec, created = svc.create(
        client_uuid=client_uuid, captured_at=captured_at, mode=mode, category=category,
        coverage_asserted=coverage_asserted, panels=panels, images=evidence,
        metadata=metadata, officer_id=principal.id,
        jurisdiction_id=principal.jurisdiction_id)
    if created:
        metrics.inc("lmpc_scan_submitted_total")
        request.app.state.auth.audit_action(
            principal, "scan", rec.id, "SCAN_CREATE",
            {"client_uuid": rec.client_uuid, "category": rec.category,
             "mode": rec.mode})
    # A repeated client_uuid is 200 with the existing scan — never a duplicate.
    return JSONResponse(envelope(rec, created), status_code=202 if created else 200)


@router.get("/{scan_id}")
async def get_scan(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("scans:read")),
) -> dict:
    rec = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, rec)
    return envelope(rec, created=True)


@router.get("/{scan_id}/images/{panel}")
async def get_scan_image(
    scan_id: str, panel: str, request: Request,
    principal: Principal = Depends(require("scans:read")),
) -> Response:
    rec = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, rec)
    image = next((item for item in rec.images if item.panel_label == panel), None)
    if image is None:
        raise ApiError("E_NOT_FOUND", f"panel {panel} not found on scan {scan_id}")
    body = request.app.state.object_store.read(image.storage_key)
    media_type = (image.media_type or mimetypes.guess_type(image.storage_key)[0]
                  or "application/octet-stream")
    return Response(
        body, media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable",
                 "ETag": f'"{image.sha256}"', "X-Content-Type-Options": "nosniff"})


@router.post("/{scan_id}/reevaluate")
async def reevaluate_scan(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("scans:reevaluate")),
) -> JSONResponse:
    """Run one append-only evaluation batch.

    Production workers call the same Pipeline object from the queue; this direct path
    keeps the modular-monolith development deployment functional without Redis.
    """
    rec = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, rec)
    try:
        rec = request.app.state.pipeline.process(scan_id)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError("E_INTERNAL", f"scan processing failed: {type(exc).__name__}") from exc
    return JSONResponse(envelope(rec, created=True), status_code=202)


@router.post("/{scan_id}/process")
async def process_new_scan(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("scans:create")),
) -> JSONResponse:
    """Run the first evaluation for a newly uploaded field inspection.

    A field officer may process their own new evidence on a local deployment. Any later
    evaluation remains the reviewing-officer-only ``reevaluate`` operation.
    """
    rec = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, rec)
    if rec.latest_evaluations() or rec.status not in {"RECEIVED", "FAILED"}:
        raise ApiError("E_CONFLICT", "this scan has already entered evaluation")
    missing = sorted(set(rec.panels) - {image.panel_label for image in rec.images})
    if missing:
        raise ApiError(
            "E_VALIDATION",
            f"this scan is still missing uploaded panels: {missing}")
    try:
        rec = request.app.state.pipeline.process(scan_id)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError("E_INTERNAL", f"scan processing failed: {type(exc).__name__}") from exc
    return JSONResponse(envelope(rec, created=True), status_code=202)
