"""Report finalization, metadata and downloads (Part 12.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ..svc.auth import Principal
from .auth import require
from .errors import ApiError

router = APIRouter(tags=["reports"])


@router.get("/scans/{scan_id}/reports")
async def list_scan_reports(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("reports:read")),
) -> dict:
    scan = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, scan)
    return {"items": request.app.state.scan_store.list_reports(scan_id)}


@router.post("/scans/{scan_id}/report", status_code=201)
async def finalize_report(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("reports:create")),
) -> dict:
    scan = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, scan)
    if (not principal.disabled_auth
            and not request.app.state.settings.allow_self_review
            and scan.officer_id == principal.id):
        raise ApiError("E_FORBIDDEN", "the capturing officer cannot finalise this report")
    report = request.app.state.reports.finalize(
        scan_id, reviewed_by=principal.id, kind="FINALIZED", generated_by=principal.id)
    request.app.state.auth.audit_action(
        principal, "compliance_report", report["id"], "REPORT_FINALIZE",
        {"scan_id": scan_id, "version": report["version"],
         "content_sha256": report["content_sha256"]})
    return {"report_id": report["id"], "version": report["version"],
            "content_sha256": report["content_sha256"]}


@router.post("/scans/{scan_id}/field-report", status_code=201)
async def field_report(
    scan_id: str, request: Request,
    principal: Principal = Depends(require("reports:create_field")),
) -> dict:
    """The officer's own copy, watermarked and explicitly not a legal finding.

    No self-review guard: this is the capturing officer's working document, and it
    deliberately leaves the scan open to correction, re-evaluation and override. Only
    POST /scans/{id}/report closes an inspection, and only a reviewer may call it.
    """
    scan = request.app.state.scan_store.get(scan_id)
    request.app.state.auth.ensure_scan_scope(principal, scan)
    report = request.app.state.reports.finalize(
        scan_id, kind="FIELD", generated_by=principal.id)
    request.app.state.auth.audit_action(
        principal, "compliance_report", report["id"], "FIELD_REPORT_GENERATED",
        {"scan_id": scan_id, "version": report["version"]})
    return {"report_id": report["id"], "version": report["version"],
            "report_kind": "FIELD", "content_sha256": report["content_sha256"]}


def _authorize(request: Request, principal: Principal, report: dict) -> None:
    """An investigation report has no single scan, so scan scoping cannot apply to it."""
    if report.get("investigation_id"):
        request.app.state.investigations.get(principal, report["investigation_id"])
        return
    request.app.state.auth.ensure_scan_scope(
        principal, request.app.state.scan_store.get(report["scan_id"]))


@router.get("/reports/{report_id}")
async def report_metadata(
    report_id: str, request: Request,
    principal: Principal = Depends(require("reports:read")),
) -> dict:
    report = request.app.state.scan_store.get_report(report_id)
    _authorize(request, principal, report)
    return report


@router.get("/reports/{report_id}/download")
async def download_report(report_id: str, request: Request,
                          format_: str = Query("pdf", alias="format"),
                          principal: Principal = Depends(require("reports:export"))) -> Response:
    report = request.app.state.scan_store.get_report(report_id)
    _authorize(request, principal, report)
    body, media_type, filename = request.app.state.reports.download(report_id, format_)
    return Response(body, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
