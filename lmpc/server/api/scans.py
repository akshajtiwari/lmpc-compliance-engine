"""Scans routes (Part 12.3). Routes declare; ScanService decides.

Every image is validated, hash-verified and persisted before processing is accepted."""
from __future__ import annotations
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ..svc.evidence import validate_image
from ..svc.scan_service import validate
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
    panels: list[str] = Form(...),
    images: list[UploadFile] = File(...),
    image_sha256: list[str] = Form(...),
) -> JSONResponse:
    validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
             category=category, coverage_asserted=coverage_asserted, panels=panels,
             n_images=len(images))
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
        coverage_asserted=coverage_asserted, panels=panels, images=evidence)
    # A repeated client_uuid is 200 with the existing scan — never a duplicate.
    return JSONResponse(_envelope(rec, created), status_code=202 if created else 200)


@router.get("/{scan_id}")
async def get_scan(scan_id: str, request: Request) -> dict:
    return _envelope(request.app.state.scan_store.get(scan_id), created=True)


def _envelope(rec, created: bool) -> dict:
    body = {"scan_id": rec.id, "status": rec.status,
            "status_url": f"/api/v1/scans/{rec.id}",
            "coverage_asserted": rec.coverage_asserted,
            "panels_captured": rec.panels,
            "images": [{"panel": image.panel_label, "storage_key": image.storage_key,
                        "sha256": image.sha256, "width": image.width_px,
                        "height": image.height_px} for image in rec.images]}
    if not created:
        body["duplicate_ignored"] = True
    return body
