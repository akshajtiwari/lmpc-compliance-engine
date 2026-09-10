"""Scan intake validation and the in-memory store used until Postgres is configured.
The contract is final (Part 12.3); scan_store.py chooses the backing store."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field

from ..api.errors import ApiError

REQUIRED_PANELS = {"FRONT", "BACK"}          # Part 7.3: BACK waivable => flag false


@dataclass
class ScanRecord:
    client_uuid: str
    captured_at: str
    mode: str
    category: str
    coverage_asserted: bool
    panels: list[str]
    image_names: list[str]
    status: str = "RECEIVED"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


def validate(coverage_asserted: bool, panels: list[str], n_images: int) -> None:
    if not 1 <= n_images <= 6 or n_images != len(panels):
        raise ApiError("E_VALIDATION", "1–6 images, one panel label per image")
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

    def create(self, *, client_uuid: str, captured_at: str, mode: str, category: str,
               coverage_asserted: bool, panels: list[str],
               image_names: list[str]) -> tuple[ScanRecord, bool]:
        validate(coverage_asserted, panels, len(image_names))
        if client_uuid in self._by_client:
            return self._by_client[client_uuid], False
        rec = ScanRecord(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                         category=category, coverage_asserted=coverage_asserted,
                         panels=panels, image_names=image_names)
        self._by_id[rec.id] = self._by_client[client_uuid] = rec
        return rec, True

    def get(self, scan_id: str) -> ScanRecord:
        rec = self._by_id.get(scan_id)
        if rec is None:
            raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
        return rec