"""Scan intake validation and the in-memory store used until Postgres is configured.
The contract is final (Part 12.3); scan_store.py chooses the backing store."""
from __future__ import annotations
import uuid
from datetime import UTC, date, datetime
from dataclasses import dataclass, field
from typing import Any

from ..api.errors import ApiError
from .evidence import EvidenceImage

REQUIRED_PANELS = {"FRONT", "BACK"}          # Part 7.3: BACK waivable => flag false
PHYSICAL_PANELS = REQUIRED_PANELS | {"SIDE_1", "SIDE_2", "SCALE_REF"}
ECOMMERCE_PANELS = {"LISTING"} | {f"LISTING_{number}" for number in range(2, 7)}
PANELS = PHYSICAL_PANELS | ECOMMERCE_PANELS
MODES = {"PHYSICAL_PACKAGE", "ECOMMERCE_LISTING"}
BUYER_TYPES = {"RETAIL", "INDUSTRIAL", "INSTITUTIONAL"}
PACKAGE_SHAPES = {"RECTANGULAR", "CYLINDRICAL", "IRREGULAR"}
SCALE_TYPES = {"ISO_ID1_CARD", "APRILTAG_36H11", "MANUAL_DIMENSIONS", "NONE"}
QUALITY_KEYS = {"source", "sharpness", "mean_luma", "glare_fraction", "warnings"}
CATEGORIES = {
    "FOOD", "COSMETIC", "GENERIC", "CEMENT", "FERTILIZER", "FARM_PRODUCE",
    "TOBACCO", "DRUG_FORMULATION", "MEDICAL_DEVICE", "RESTAURANT_FAST_FOOD",
    "HANDLOOM_THREAD_COIL",
}


@dataclass
class ScanRecord:
    client_uuid: str
    captured_at: str
    mode: str
    category: str
    coverage_asserted: bool
    panels: list[str]
    images: list[EvidenceImage]
    status: str = "RECEIVED"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    overall: str | None = None
    rulepack_version: str | None = None
    rulepack_sha256: str | None = None
    batch: int = 0
    declarations: list[dict[str, Any]] = field(default_factory=list)
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    officer_id: str | None = None
    jurisdiction_id: str | None = None

    def latest_declarations(self) -> list[dict[str, Any]]:
        effective = {}
        for item in self.declarations:
            if item["batch"] == self.batch:
                effective[item["field"]] = item
        return list(effective.values())

    def latest_evaluations(self) -> list[dict[str, Any]]:
        effective = {}
        for item in self.evaluations:
            if item["batch"] == self.batch:
                effective[item["check"]] = item
        return list(effective.values())


def validate(*, client_uuid: str, captured_at: str, mode: str, category: str,
             coverage_asserted: bool, panels: list[str], n_images: int) -> None:
    validate_deferred(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                      category=category, coverage_asserted=coverage_asserted,
                      panels=panels)
    if not 1 <= n_images <= 6 or n_images != len(panels):
        raise ApiError("E_VALIDATION", "1–6 images, one panel label per image")


def validate_deferred(*, client_uuid: str, captured_at: str, mode: str, category: str,
                      coverage_asserted: bool, panels: list[str]) -> None:
    """Deferred intake declares metadata and panels first; images arrive one by one
    over unreliable field networks (plan §8 item 9) and are completed afterwards."""
    try:
        uuid.UUID(client_uuid)
    except ValueError as exc:
        raise ApiError("E_VALIDATION", "client_uuid must be a UUID") from exc
    try:
        date.fromisoformat(captured_at)
    except ValueError as exc:
        raise ApiError("E_VALIDATION", "captured_at must be an ISO-8601 date") from exc
    if mode not in MODES:
        raise ApiError("E_VALIDATION", f"unsupported scan mode: {mode}")
    if category not in CATEGORIES:
        raise ApiError("E_VALIDATION", f"unsupported commodity category: {category}")
    if not 1 <= len(panels) <= 6:
        raise ApiError("E_VALIDATION", "declare 1–6 panel labels")
    if any(panel not in PANELS for panel in panels):
        raise ApiError("E_VALIDATION", "unsupported panel label")
    if len(set(panels)) != len(panels):
        raise ApiError("E_VALIDATION", "a panel label may only be uploaded once")
    if coverage_asserted and not REQUIRED_PANELS.issubset(panels):
        raise ApiError(
            "E_COVERAGE_MISMATCH",
            "coverage_asserted=true but required panels were not captured: "
            + ", ".join(sorted(REQUIRED_PANELS - set(panels))))


def validate_panel_mode(*, mode: str, coverage_asserted: bool,
                        panels: list[str]) -> None:
    """Keep package photographs and third-party listing screenshots distinct."""
    supplied = set(panels)
    if mode == "ECOMMERCE_LISTING":
        if coverage_asserted:
            raise ApiError(
                "E_COVERAGE_MISMATCH",
                "e-commerce screenshots cannot assert physical-package coverage")
        if not supplied.issubset(ECOMMERCE_PANELS):
            raise ApiError(
                "E_VALIDATION",
                "e-commerce evidence must use LISTING screenshot panel labels")
    elif not supplied.issubset(PHYSICAL_PANELS):
        raise ApiError(
            "E_VALIDATION",
            "physical-package evidence cannot use LISTING screenshot panel labels")


class MemoryStore:
    """A repeated client_uuid returns the existing scan — never a duplicate."""

    def __init__(self):
        self._by_id: dict[str, ScanRecord] = {}
        self._by_client: dict[str, ScanRecord] = {}
        self._reports: dict[str, dict] = {}

    def ready(self) -> bool:
        return True

    def create(self, *, client_uuid: str, captured_at: str, mode: str, category: str,
               coverage_asserted: bool, panels: list[str],
               images: list[EvidenceImage],
               metadata: dict[str, Any] | None = None,
               officer_id: str | None = None,
               jurisdiction_id: str | None = None) -> tuple[ScanRecord, bool]:
        validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                 category=category, coverage_asserted=coverage_asserted, panels=panels,
                 n_images=len(images))
        client_uuid = str(uuid.UUID(client_uuid))
        if client_uuid in self._by_client:
            return self._by_client[client_uuid], False
        rec = ScanRecord(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                         category=category, coverage_asserted=coverage_asserted,
                         panels=panels, images=images, metadata=metadata or {},
                         officer_id=officer_id, jurisdiction_id=jurisdiction_id)
        self._by_id[rec.id] = self._by_client[client_uuid] = rec
        return rec, True

    def get(self, scan_id: str) -> ScanRecord:
        rec = self._by_id.get(scan_id)
        if rec is None:
            raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
        return rec

    def begin(self, *, client_uuid: str, captured_at: str, mode: str, category: str,
              coverage_asserted: bool, panels: list[str],
              metadata: dict[str, Any] | None = None,
              officer_id: str | None = None,
              jurisdiction_id: str | None = None) -> tuple[ScanRecord, bool]:
        validate_deferred(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                          category=category, coverage_asserted=coverage_asserted,
                          panels=panels)
        client_uuid = str(uuid.UUID(client_uuid))
        if client_uuid in self._by_client:
            return self._by_client[client_uuid], False
        rec = ScanRecord(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                         category=category, coverage_asserted=coverage_asserted,
                         panels=panels, images=[], metadata=metadata or {},
                         officer_id=officer_id, jurisdiction_id=jurisdiction_id)
        self._by_id[rec.id] = self._by_client[client_uuid] = rec
        return rec, True

    def add_image(self, scan_id: str, panel: str, item: EvidenceImage) -> dict:
        rec = self.get(scan_id)
        if panel not in rec.panels:
            raise ApiError("E_VALIDATION", f"panel {panel} was not declared for this scan")
        if rec.status != "RECEIVED":
            raise ApiError("E_CONFLICT",
                           f"scan {scan_id} has left the RECEIVED state and cannot take images")
        existing = next((image for image in rec.images
                         if image.panel_label == panel), None)
        if existing is not None:
            if existing.sha256 != item.sha256:
                raise ApiError(
                    "E_CONFLICT",
                    f"panel {panel} already holds different evidence")
            return {"panel": panel, "sha256": existing.sha256,
                    "duplicate_ignored": True}
        rec.images.append(item.on_panel(panel))
        return {"panel": panel, "sha256": item.sha256, "duplicate_ignored": False}

    def complete_upload(self, scan_id: str) -> ScanRecord:
        rec = self.get(scan_id)
        supplied = {image.panel_label for image in rec.images}
        missing = sorted(set(rec.panels) - supplied)
        if missing:
            raise ApiError(
                "E_VALIDATION", f"this scan is still missing uploaded panels: {missing}")
        return rec

    def start_processing(self, scan_id: str) -> ScanRecord:
        rec = self.get(scan_id)
        if rec.status == "FINALIZED":
            raise ApiError("E_SCAN_FINALIZED", "a finalized scan cannot be re-evaluated")
        rec.status = "OCR_IN_PROGRESS"
        rec.failure_reason = None
        return rec

    def complete_evaluation(self, scan_id: str, *, declarations: list[dict],
                            evaluations: list[dict], overall: str,
                            rulepack_version: str, rulepack_sha256: str,
                            max_edges: dict[str, int]) -> ScanRecord:
        rec = self.get(scan_id)
        rec.batch += 1
        for item in declarations:
            rec.declarations.append({**item, "id": str(uuid.uuid4()), "batch": rec.batch})
        for item in evaluations:
            rec.evaluations.append({**item, "id": str(uuid.uuid4()), "batch": rec.batch})
        rec.overall = overall
        rec.rulepack_version = rulepack_version
        rec.rulepack_sha256 = rulepack_sha256
        rec.images = [image.with_max_edge(max_edges[image.storage_key])
                      if image.storage_key in max_edges else image for image in rec.images]
        rec.status = "EVALUATION_COMPLETE"
        return rec

    def fail_processing(self, scan_id: str, reason: str) -> None:
        rec = self.get(scan_id)
        rec.status = "FAILED"
        rec.failure_reason = reason

    def next_report_version(self, scan_id: str) -> int:
        self.get(scan_id)
        versions = [item["version"] for item in self._reports.values()
                    if item["scan_id"] == scan_id]
        return max(versions, default=0) + 1

    def save_report(self, scan_id: str, *, version: int, overall_status: str,
                    pdf_storage_key: str, docx_storage_key: str,
                    content_sha256: str, manifest: dict,
                    reviewed_by: str | None = None) -> dict:
        rec = self.get(scan_id)
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id, "scan_id": scan_id, "version": version,
            "overall_status": overall_status, "pdf_storage_key": pdf_storage_key,
            "docx_storage_key": docx_storage_key, "content_sha256": content_sha256,
            "manifest": manifest, "reviewed_by": reviewed_by,
            "finalized_at": datetime.now(UTC).isoformat(),
        }
        self._reports[report_id] = report
        rec.status = "FINALIZED"
        return report

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
