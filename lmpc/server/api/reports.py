"""Report finalization, metadata and downloads (Part 12.5)."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

router = APIRouter(tags=["reports"])


@router.post("/scans/{scan_id}/report", status_code=201)
async def finalize_report(scan_id: str, request: Request) -> dict:
    report = request.app.state.reports.finalize(scan_id)
    return {"report_id": report["id"], "version": report["version"],
            "content_sha256": report["content_sha256"]}


@router.get("/reports/{report_id}")
async def report_metadata(report_id: str, request: Request) -> dict:
    return request.app.state.scan_store.get_report(report_id)


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str, request: Request,
                          format_: str = Query("pdf", alias="format")) -> Response:
    body, media_type, filename = request.app.state.reports.download(report_id, format_)
    return Response(body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
