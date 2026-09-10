"""Scans routes (Part 12.3). Routes declare; ScanService decides.

Every image is validated, hash-verified and persisted before processing is accepted."""
from __future__ import annotations
import json
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ..svc.evidence import validate_image
from ..svc.scan_service import validate, validate_metadata
from .errors import ApiError

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
) -> JSONResponse:
    validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
             category=category, coverage_asserted=coverage_asserted, panels=panels,
             n_images=len(images))
    metadata = validate_metadata(
        mode=mode, buyer_type=buyer_type, package_shape=package_shape,
        scale_reference=_json_object(scale_reference, "scale_reference"),
        dimensions=_json_object(dimensions, "dimensions"),
        flags=_json_object(flags, "flags"), geo=_json_object(geo, "geo"),
        ecommerce=_json_object(ecommerce, "ecommerce"))
    if len(image_sha256) != len(images):
        raise ApiError("E_VALIDATION", "one image_sha256 is required per image")
    settings = request.app.state.settings
    evidence = []
    for panel, upload, digest in zip(panels, images, image_sha256, strict=True):
        data = await upload.read(settings.max_image_bytes + 1)
        item = validate_image(
            data=data, filename=upload.filename or "image",
            media_type=upload.content_type or "", expected_sha256=digest,
            max_bytes=settings.max_image_bytes, max_pixels=settings.max_image_pixels,
        ).on_panel(panel)
        evidence.append(item)
    for item in evidence:
        request.app.state.object_store.put_immutable(
            item.storage_key, item.data, item.media_type, item.sha256)
    evidence = [item.without_data() for item in evidence]
    svc = request.app.state.scan_store
    rec, created = svc.create(
        client_uuid=client_uuid, captured_at=captured_at, mode=mode, category=category,
        coverage_asserted=coverage_asserted, panels=panels, images=evidence,
        metadata=metadata)
    # A repeated client_uuid is 200 with the existing scan — never a duplicate.
    return JSONResponse(_envelope(rec, created), status_code=202 if created else 200)


@router.get("/{scan_id}")
async def get_scan(scan_id: str, request: Request) -> dict:
    return _envelope(request.app.state.scan_store.get(scan_id), created=True)


@router.post("/{scan_id}/reevaluate")
async def reevaluate_scan(scan_id: str, request: Request) -> JSONResponse:
    """Run one append-only evaluation batch.

    Production workers call the same Pipeline object from the queue; this direct path
    keeps the modular-monolith development deployment functional without Redis.
    """
    try:
        rec = request.app.state.pipeline.process(scan_id)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError("E_INTERNAL", f"scan processing failed: {type(exc).__name__}") from exc
    return JSONResponse(_envelope(rec, created=True), status_code=202)


def _envelope(rec, created: bool) -> dict:
    body = {"scan_id": rec.id, "status": rec.status,
            "status_url": f"/api/v1/scans/{rec.id}",
            "coverage_asserted": rec.coverage_asserted,
            "panels_captured": rec.panels,
            "captured_at": rec.captured_at, "mode": rec.mode, "category": rec.category,
            "buyer_type": rec.metadata.get("buyer_type", "RETAIL"),
            "package_shape": rec.metadata.get("package_shape", "RECTANGULAR"),
            "overall": rec.overall,
            "rulepack": ({"version": rec.rulepack_version,
                          "sha256": rec.rulepack_sha256}
                         if rec.rulepack_version else None),
            "images": [{"panel": image.panel_label, "storage_key": image.storage_key,
                        "sha256": image.sha256, "width": image.width_px,
                        "height": image.height_px, "max_edge_used": image.max_edge_used}
                       for image in rec.images],
            "declarations": rec.latest_declarations(),
            "evaluations": rec.latest_evaluations()}
    if rec.failure_reason:
        body["failure_reason"] = rec.failure_reason
    if not created:
        body["duplicate_ignored"] = True
    return body


def _json_object(raw: str | None, field: str) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("E_VALIDATION", f"{field} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ApiError("E_VALIDATION", f"{field} must be a JSON object")
    return value
