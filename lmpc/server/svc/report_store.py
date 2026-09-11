"""Report persistence for the Postgres-backed scan store."""
from __future__ import annotations
import uuid

from sqlalchemy import func, select

from ..api.errors import ApiError
from ..db.models import ComplianceReport, Scan
from .store_records import report_dict


class ReportStoreMixin:
    """Versioned, append-only finalized reports behind POST /scans/{id}/report."""

    def next_report_version(self, scan_id: str) -> int:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            if session.get(Scan, scan_uuid) is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            latest = session.scalar(select(func.max(ComplianceReport.version)).where(
                ComplianceReport.scan_id == scan_uuid)) or 0
            return latest + 1

    def save_report(self, scan_id: str, *, version: int, overall_status: str,
                    pdf_storage_key: str, docx_storage_key: str,
                    content_sha256: str, manifest: dict,
                    reviewed_by: str | None = None) -> dict:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            scan = session.get(Scan, scan_uuid)
            if scan is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            report = ComplianceReport(
                scan_id=scan_uuid, version=version, overall_status=overall_status,
                pdf_storage_key=pdf_storage_key, docx_storage_key=docx_storage_key,
                content_sha256=content_sha256, manifest=manifest,
                reviewed_by=uuid.UUID(reviewed_by) if reviewed_by else None)
            session.add(report)
            scan.status = "FINALIZED"
            session.commit()
            session.refresh(report)
            return report_dict(report)

    def get_report(self, report_id: str) -> dict:
        try:
            report_uuid = uuid.UUID(report_id)
        except ValueError:
            raise ApiError("E_NOT_FOUND", f"report {report_id} not found") from None
        with self.sessions() as session:
            report = session.get(ComplianceReport, report_uuid)
            if report is None:
                raise ApiError("E_NOT_FOUND", f"report {report_id} not found")
            return report_dict(report)

    def list_reports(self, scan_id: str) -> list[dict]:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            if session.get(Scan, scan_uuid) is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            rows = session.scalars(select(ComplianceReport).where(
                ComplianceReport.scan_id == scan_uuid).order_by(
                    ComplianceReport.version.desc())).all()
            return [report_dict(row) for row in rows]


def _uuid_or_404(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ApiError("E_NOT_FOUND", f"scan {value} not found") from None
