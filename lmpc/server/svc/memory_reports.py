"""Report bookkeeping for the in-memory scan store.

The mirror of `ReportStoreMixin`, which does the same job against PostgreSQL. Extracted
from `scan_service` so both stores keep their report code in a file of its own and
`MemoryStore` stays within the module size the import-graph test enforces.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..api.errors import ApiError


class MemoryReportsMixin:
    """Mixed into MemoryStore, which supplies `get` and the `_reports` dict."""

    def next_report_version(self, scan_id: str, *, kind: str = "FINALIZED") -> int:
        self.get(scan_id)
        versions = [item["version"] for item in self._reports.values()
                    if item["scan_id"] == scan_id
                    and item.get("report_kind", "FINALIZED") == kind]
        return max(versions, default=0) + 1

    def save_report(self, scan_id: str, *, version: int, overall_status: str,
                    pdf_storage_key: str, docx_storage_key: str,
                    content_sha256: str, manifest: dict,
                    reviewed_by: str | None = None, report_kind: str = "FINALIZED",
                    generated_by: str | None = None) -> dict:
        rec = self.get(scan_id)
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id, "scan_id": scan_id, "version": version,
            "overall_status": overall_status, "pdf_storage_key": pdf_storage_key,
            "docx_storage_key": docx_storage_key, "content_sha256": content_sha256,
            "manifest": manifest, "reviewed_by": reviewed_by,
            "report_kind": report_kind, "generated_by": generated_by,
            "finalized_at": datetime.now(UTC).isoformat(),
        }
        self._reports[report_id] = report
        # See ReportStoreMixin.save_report: a field copy must not close the inspection.
        if report_kind == "FINALIZED":
            rec.status = "FINALIZED"
        return report

    def next_investigation_report_version(self, investigation_id: str, *,
                                          kind: str = "FINALIZED") -> int:
        versions = [item["version"] for item in self._reports.values()
                    if item.get("investigation_id") == investigation_id
                    and item.get("report_kind", "FINALIZED") == kind]
        return max(versions, default=0) + 1

    def save_investigation_report(self, investigation_id: str, *, version: int,
                                  overall_status: str, pdf_storage_key: str,
                                  docx_storage_key: str, content_sha256: str,
                                  manifest: dict, report_kind: str,
                                  generated_by: str | None) -> dict:
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id, "scan_id": None, "investigation_id": investigation_id,
            "version": version, "overall_status": overall_status,
            "pdf_storage_key": pdf_storage_key, "docx_storage_key": docx_storage_key,
            "content_sha256": content_sha256, "manifest": manifest,
            "report_kind": report_kind, "generated_by": generated_by,
            "reviewed_by": None, "finalized_at": datetime.now(UTC).isoformat(),
        }
        self._reports[report_id] = report
        return report

    def list_investigation_reports(self, investigation_id: str) -> list[dict]:
        return sorted((item for item in self._reports.values()
                       if item.get("investigation_id") == investigation_id),
                      key=lambda item: item["version"], reverse=True)

    def get_report(self, report_id: str) -> dict:
        report = self._reports.get(report_id)
        if report is None:
            raise ApiError("E_NOT_FOUND", f"report {report_id} not found")
        return report

    def list_reports(self, scan_id: str) -> list[dict]:
        self.get(scan_id)
        return sorted(
            (item for item in self._reports.values() if item["scan_id"] == scan_id),
            key=lambda item: item["version"], reverse=True)
