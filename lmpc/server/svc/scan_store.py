"""The backing store behind POST /scans: Postgres when configured, memory otherwise.

Idempotency is a database guarantee, not a service promise: scans.client_uuid is
UNIQUE and the insert is ON CONFLICT DO NOTHING, so two racing submissions —
the offline queue retries after a timeout — cannot create a second scan (Part 12.3).
"""
from __future__ import annotations
import uuid

from sqlalchemy.dialects.postgresql import insert

from ..api.errors import ApiError
from ..config import Settings
from ..db import sessionmaker_of
from ..db.models import Scan
from .scan_service import MemoryStore, ScanRecord, validate

Fields = dict  # the create() keyword contract shared by both stores


def open_store(settings: Settings) -> MemoryStore | "DbStore":
    return DbStore(settings) if settings.db_url else MemoryStore()


class DbStore:
    def __init__(self, settings: Settings):
        # Part 14 puts officer and jurisdiction on the token; until auth lands they
        # arrive as bootstrap configuration and default to anonymous placeholders.
        self.sessions = sessionmaker_of(settings.db_url)
        self.officer_id = settings.officer_uuid or str(uuid.UUID(int=0))
        self.jurisdiction_id = settings.jurisdiction_uuid or str(uuid.UUID(int=0))

    def create(self, *, client_uuid: str, captured_at: str, mode: str, category: str,
               coverage_asserted: bool, panels: list[str],
               image_names: list[str]) -> tuple[ScanRecord, bool]:
        validate(coverage_asserted, panels, len(image_names))
        with self.sessions() as s:
            row = s.execute(
                insert(Scan)
                .values(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                        category_code=category, coverage_asserted=coverage_asserted,
                        panels_captured=panels, officer_id=self.officer_id,
                        jurisdiction_id=self.jurisdiction_id)
                .on_conflict_do_nothing(index_elements=[Scan.client_uuid])
                .returning(Scan.id)).first()
            s.commit()
            if row is None:                       # the race lost: return the winner
                return self._rec(client_uuid=client_uuid), False
            return self._rec(scan_id=str(row[0])), True

    def get(self, scan_id: str) -> ScanRecord:
        try:
            return self._rec(scan_id=scan_id)
        except Exception:
            raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found") from None

    def _rec(self, scan_id: str | None = None, client_uuid: str | None = None) -> ScanRecord:
        with self.sessions() as s:
            q = s.query(Scan)
            q = q.filter(Scan.id == scan_id) if scan_id else q.filter(
                Scan.client_uuid == uuid.UUID(client_uuid))
            row = q.one()
            return ScanRecord(
                client_uuid=str(row.client_uuid), captured_at=str(row.captured_at),
                mode=row.mode, category=row.category_code,
                coverage_asserted=row.coverage_asserted,
                panels=list(row.panels_captured), image_names=[],
                status=row.status, id=str(row.id))