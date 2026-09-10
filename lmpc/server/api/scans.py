"""Scans routes (Part 12.3). Routes declare; ScanService decides.

Image bytes are verified for size here; their content reaches the queue in Phase 4.
The response shape is final now so the capture app can be built against it."""
from __future__ import annotations
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..config import Settings
from ..svc.scan_store import open_store
from .errors import ApiError

router = APIRouter(prefix="/scans", tags=["scans"])
svc = open_store(Settings.from_env())
_max_image_bytes = Settings.from_env().max_image_bytes


@router.post("")
async def create_scan(
    client_uuid: str = Form(...),
    captured_at: str = Form(...),
    mode: str = Form(...),
    category: str = Form(...),
    coverage_asserted: bool = Form(...),
    panels: list[str] = Form(...),
    images: list[UploadFile] = File(...),
) -> JSONResponse:
    names = []
    for im in images:
        data = await im.read()
        if len(data) > _max_image_bytes:
            raise ApiError("E_IMAGE_TOO_LARGE", f"{im.filename} exceeds the image cap")
        names.append(im.filename or "image")
    rec, created = svc.create(
        client_uuid=client_uuid, captured_at=captured_at, mode=mode, category=category,
        coverage_asserted=coverage_asserted, panels=panels, image_names=names)
    # A repeated client_uuid is 200 with the existing scan — never a duplicate.
    return JSONResponse(_envelope(rec, created), status_code=202 if created else 200)


@router.get("/{scan_id}")
def get_scan(scan_id: str) -> dict:
    return _envelope(svc.get(scan_id), created=True)


def _envelope(rec, created: bool) -> dict:
    body = {"scan_id": rec.id, "status": rec.status,
            "status_url": f"/api/v1/scans/{rec.id}",
            "coverage_asserted": rec.coverage_asserted,
            "panels_captured": rec.panels}
    if not created:
        body["duplicate_ignored"] = True
    return body