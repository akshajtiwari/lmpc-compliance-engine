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
PANELS = REQUIRED_PANELS | {"SIDE_1", "SIDE_2", "SCALE_REF", "LISTING"}
MODES = {"PHYSICAL_PACKAGE", "ECOMMERCE_LISTING"}
BUYER_TYPES = {"RETAIL", "INDUSTRIAL", "INSTITUTIONAL"}
PACKAGE_SHAPES = {"RECTANGULAR", "CYLINDRICAL", "IRREGULAR"}
SCALE_TYPES = {"ISO_ID1_CARD", "APRILTAG_36H11", "MANUAL_DIMENSIONS", "NONE"}
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

    def latest_declarations(self) -> list[dict[str, Any]]:
        return [item for item in self.declarations if item["batch"] == self.batch]

    def latest_evaluations(self) -> list[dict[str, Any]]:
        return [item for item in self.evaluations if item["batch"] == self.batch]


def validate(*, client_uuid: str, captured_at: str, mode: str, category: str,
             coverage_asserted: bool, panels: list[str], n_images: int) -> None:
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
    if not 1 <= n_images <= 6 or n_images != len(panels):
        raise ApiError("E_VALIDATION", "1–6 images, one panel label per image")
    if any(panel not in PANELS for panel in panels):
        raise ApiError("E_VALIDATION", "unsupported panel label")
    if len(set(panels)) != len(panels):
        raise ApiError("E_VALIDATION", "a panel label may only be uploaded once")
    if coverage_asserted and not REQUIRED_PANELS.issubset(panels):
        raise ApiError(
            "E_COVERAGE_MISMATCH",
            "coverage_asserted=true but required panels were not captured: "
            + ", ".join(sorted(REQUIRED_PANELS - set(panels))))


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
               metadata: dict[str, Any] | None = None) -> tuple[ScanRecord, bool]:
        validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                 category=category, coverage_asserted=coverage_asserted, panels=panels,
                 n_images=len(images))
        client_uuid = str(uuid.UUID(client_uuid))
        if client_uuid in self._by_client:
            return self._by_client[client_uuid], False
        rec = ScanRecord(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                         category=category, coverage_asserted=coverage_asserted,
                         panels=panels, images=images, metadata=metadata or {})
        self._by_id[rec.id] = self._by_client[client_uuid] = rec
        return rec, True

    def get(self, scan_id: str) -> ScanRecord:
        rec = self._by_id.get(scan_id)
        if rec is None:
            raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
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
                    content_sha256: str, manifest: dict) -> dict:
        rec = self.get(scan_id)
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id, "scan_id": scan_id, "version": version,
            "overall_status": overall_status, "pdf_storage_key": pdf_storage_key,
            "docx_storage_key": docx_storage_key, "content_sha256": content_sha256,
            "manifest": manifest, "finalized_at": datetime.now(UTC).isoformat(),
        }
        self._reports[report_id] = report
        rec.status = "FINALIZED"
        return report

    def get_report(self, report_id: str) -> dict:
        report = self._reports.get(report_id)
        if report is None:
            raise ApiError("E_NOT_FOUND", f"report {report_id} not found")
        return report


def validate_metadata(*, mode: str, buyer_type: str, package_shape: str,
                      scale_reference: dict, dimensions: dict, flags: dict,
                      geo: dict, ecommerce: dict) -> dict[str, Any]:
    if buyer_type not in BUYER_TYPES:
        raise ApiError("E_VALIDATION", f"unsupported buyer_type: {buyer_type}")
    if package_shape not in PACKAGE_SHAPES:
        raise ApiError("E_VALIDATION", f"unsupported package_shape: {package_shape}")
    scale_type = scale_reference.get("type", "NONE")
    if scale_type not in SCALE_TYPES:
        raise ApiError("E_VALIDATION", f"unsupported scale reference: {scale_type}")
    numbers = {key: _positive_number(dimensions, key)
               for key in ("h_cm", "w_cm", "capacity_cm3")}
    if (numbers["h_cm"] is None) != (numbers["w_cm"] is None):
        raise ApiError("E_VALIDATION", "dimensions require both h_cm and w_cm")
    expected_flags = {"is_imported", "is_molded", "other_law_requires_same_info"}
    if any(key not in expected_flags or not isinstance(value, bool)
           for key, value in flags.items()):
        raise ApiError("E_VALIDATION", "flags contain an unknown or non-boolean value")
    lat, lng = geo.get("lat"), geo.get("lng")
    numeric_geo = all(not isinstance(value, bool) and isinstance(value, (int, float))
                      for value in (lat, lng) if value is not None)
    if (lat is None) != (lng is None) or not numeric_geo \
            or (lat is not None and not (-90 <= lat <= 90)) \
            or (lng is not None and not (-180 <= lng <= 180)):
        raise ApiError("E_VALIDATION", "geo requires a valid latitude and longitude")
    if mode == "ECOMMERCE_LISTING" and not ecommerce.get("listing_text"):
        raise ApiError("E_VALIDATION", "ecommerce.listing_text is required in listing mode")
    if any(value is not None and not isinstance(value, str)
           for value in (ecommerce.get("url"), ecommerce.get("listing_text"))):
        raise ApiError("E_VALIDATION", "ecommerce url and listing_text must be strings")
    return {
        "buyer_type": buyer_type, "package_shape": package_shape,
        "scale_reference_type": scale_type,
        "scale_reference_data": scale_reference.get("data"),
        "pdp_h_cm": numbers["h_cm"], "pdp_w_cm": numbers["w_cm"],
        "capacity_cm3": numbers["capacity_cm3"],
        "is_imported": flags.get("is_imported", False),
        "is_molded": flags.get("is_molded", False),
        "other_law_requires_same_info": flags.get("other_law_requires_same_info", False),
        "geo_lat": lat, "geo_lng": lng,
        "ecommerce_url": ecommerce.get("url"),
        "ecommerce_text": ecommerce.get("listing_text"),
    }


def _positive_number(values: dict, key: str) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ApiError("E_VALIDATION", f"dimensions.{key} must be a positive number")
    return float(value)
