"""The backing store behind POST /scans: Postgres when configured, memory otherwise.

Idempotency is a database guarantee, not a service promise: scans.client_uuid is
UNIQUE and the insert is ON CONFLICT DO NOTHING, so two racing submissions —
the offline queue retries after a timeout — cannot create a second scan (Part 12.3).
"""
from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.exc import NoResultFound

from ..api.errors import ApiError
from ..config import Settings
from ..db import sessionmaker_of
from ..db.models import (ExtractedDeclaration, RuleEvaluation, Scan,
                         ScanImage)
from .evidence import EvidenceImage
from .report_store import ReportStoreMixin, _uuid_or_404
from .scan_service import MemoryStore, ScanRecord, validate, validate_deferred
from .store_records import (declaration_dict, evaluation_dict, optional_date,
                            scan_metadata)

Fields = dict  # the create() keyword contract shared by both stores


def open_store(settings: Settings) -> MemoryStore | DbStore:
    return DbStore(settings) if settings.db_url else MemoryStore()


class DbStore(ReportStoreMixin):
    def __init__(self, settings: Settings):
        # Part 14 puts officer and jurisdiction on the token; until auth lands they
        # arrive as bootstrap configuration.
        if not settings.officer_uuid or not settings.jurisdiction_uuid:
            raise RuntimeError(
                "LMPC_DB_URL requires LMPC_OFFICER_UUID and LMPC_JURISDICTION_UUID")
        try:
            uuid.UUID(settings.officer_uuid)
            uuid.UUID(settings.jurisdiction_uuid)
        except ValueError as exc:
            raise RuntimeError(
                "LMPC_OFFICER_UUID and LMPC_JURISDICTION_UUID must be UUIDs") from exc
        self.sessions = sessionmaker_of(settings.db_url)
        self.officer_id = settings.officer_uuid
        self.jurisdiction_id = settings.jurisdiction_uuid

    def ready(self) -> bool:
        try:
            with self.sessions() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def create(self, *, client_uuid: str, captured_at: str, mode: str, category: str,
               coverage_asserted: bool, panels: list[str],
               images: list[EvidenceImage],
               metadata: dict[str, Any] | None = None,
               officer_id: str | None = None,
               jurisdiction_id: str | None = None) -> tuple[ScanRecord, bool]:
        validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                 category=category, coverage_asserted=coverage_asserted, panels=panels,
                 n_images=len(images))
        with self.sessions() as s:
            row = s.execute(
                insert(Scan)
                .values(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                        category_code=category, coverage_asserted=coverage_asserted,
                        panels_captured=panels, officer_id=officer_id or self.officer_id,
                        jurisdiction_id=jurisdiction_id or self.jurisdiction_id,
                        **(metadata or {}))
                .on_conflict_do_nothing(index_elements=[Scan.client_uuid])
                .returning(Scan.id)).first()
            if row is None:                       # the race lost: return the winner
                s.commit()
                return self._rec(client_uuid=client_uuid), False
            s.add_all(ScanImage(
                scan_id=row[0], panel_label=image.panel_label,
                storage_key=image.storage_key, sha256=image.sha256,
                width_px=image.width_px, height_px=image.height_px,
                quality=image.quality, upload_status="UPLOADED") for image in images)
            s.commit()
            return self._rec(scan_id=str(row[0])), True

    def get(self, scan_id: str) -> ScanRecord:
        try:
            return self._rec(scan_id=str(uuid.UUID(scan_id)))
        except (ValueError, NoResultFound):
            raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found") from None

    def begin(self, *, client_uuid: str, captured_at: str, mode: str, category: str,
              coverage_asserted: bool, panels: list[str],
              metadata: dict[str, Any] | None = None,
              officer_id: str | None = None,
              jurisdiction_id: str | None = None) -> tuple[ScanRecord, bool]:
        validate_deferred(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                          category=category, coverage_asserted=coverage_asserted,
                          panels=panels)
        with self.sessions() as s:
            row = s.execute(
                insert(Scan)
                .values(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                        category_code=category, coverage_asserted=coverage_asserted,
                        panels_captured=panels, officer_id=officer_id or self.officer_id,
                        jurisdiction_id=jurisdiction_id or self.jurisdiction_id,
                        **(metadata or {}))
                .on_conflict_do_nothing(index_elements=[Scan.client_uuid])
                .returning(Scan.id)).first()
            if row is None:                       # the race lost: return the winner
                s.commit()
                return self._rec(client_uuid=client_uuid), False
            s.commit()
            return self._rec(scan_id=str(row[0])), True

    def add_image(self, scan_id: str, panel: str, item: EvidenceImage) -> dict:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            row = session.get(Scan, scan_uuid)
            if row is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            if row.status != "RECEIVED":
                raise ApiError("E_CONFLICT",
                               f"scan {scan_id} has left the RECEIVED state and cannot take images")
            if panel not in row.panels_captured:
                raise ApiError("E_VALIDATION", f"panel {panel} was not declared for this scan")
            existing = session.scalar(select(ScanImage).where(
                ScanImage.scan_id == scan_uuid, ScanImage.panel_label == panel))
            if existing is not None:
                if existing.sha256 != item.sha256:
                    raise ApiError(
                        "E_CONFLICT", f"panel {panel} already holds different evidence")
                return {"panel": panel, "sha256": existing.sha256,
                        "duplicate_ignored": True}
            session.add(ScanImage(
                scan_id=scan_uuid, panel_label=panel, storage_key=item.storage_key,
                sha256=item.sha256, width_px=item.width_px, height_px=item.height_px,
                quality=item.quality, upload_status="UPLOADED"))
            session.commit()
            return {"panel": panel, "sha256": item.sha256, "duplicate_ignored": False}

    def complete_upload(self, scan_id: str) -> ScanRecord:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            row = session.get(Scan, scan_uuid)
            if row is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            supplied = {image.panel_label for image in session.scalars(
                select(ScanImage).where(ScanImage.scan_id == scan_uuid))}
            missing = sorted(set(row.panels_captured) - supplied)
            if missing:
                raise ApiError(
                    "E_VALIDATION",
                    f"this scan is still missing uploaded panels: {missing}")
        return self.get(scan_id)

    def start_processing(self, scan_id: str) -> ScanRecord:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            row = session.get(Scan, scan_uuid)
            if row is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            if row.status == "FINALIZED":
                raise ApiError("E_SCAN_FINALIZED", "a finalized scan cannot be re-evaluated")
            row.status = "OCR_IN_PROGRESS"
            session.commit()
        return self.get(scan_id)

    def complete_evaluation(self, scan_id: str, *, declarations: list[dict],
                            evaluations: list[dict], overall: str,
                            rulepack_version: str, rulepack_sha256: str,
                            max_edges: dict[str, int]) -> ScanRecord:
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            row = session.get(Scan, scan_uuid)
            if row is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            prior = session.scalar(select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == scan_uuid)) or 0
            batch = prior + 1
            image_ids = {image.panel_label: image.id for image in session.scalars(
                select(ScanImage).where(ScanImage.scan_id == scan_uuid))}
            for image in session.scalars(select(ScanImage).where(
                    ScanImage.scan_id == scan_uuid)):
                image.max_edge_used = max_edges.get(image.storage_key)
            field_ids = {}
            for item in declarations:
                x, y, width, height = item["bbox"]
                declaration = ExtractedDeclaration(
                    scan_id=scan_uuid, scan_image_id=image_ids.get(item["panel"]),
                    batch=batch, field_type=item["field"], raw_text=item["text"],
                    normalized_value=item["normalized_value"], bbox_x=x, bbox_y=y,
                    bbox_w=width, bbox_h=height, ocr_confidence=item["confidence"],
                    score=item["score"], runner_up_margin=item["margin"],
                    feature_weights=item["feature_weights"],
                    source_token_ids=item["source_token_ids"],
                    is_composite=item["is_composite"], is_repaired=item["is_repaired"],
                    glyph_height_px=item["glyph_height_px"],
                    is_on_pdp=item["panel"] == "FRONT",
                    corrected_by=(uuid.UUID(item["corrected_by"])
                                  if item.get("corrected_by") else None))
                session.add(declaration)
                session.flush()
                field_ids[item["field"]] = declaration.id
            for item in evaluations:
                session.add(RuleEvaluation(
                    scan_id=scan_uuid, batch=batch, check_code=item["check"],
                    clause=item["clause"], outcome=item["outcome"], reason=item["reason"],
                    citation=item["citation"], evidence=item["evidence"],
                    rulepack_version=rulepack_version,
                    law_version=optional_date(item["law_version"]),
                    evidence_declaration_id=field_ids.get(item["field"])))
            row.status = "EVALUATION_COMPLETE"
            row.overall = overall
            row.rulepack_version = rulepack_version
            row.rulepack_sha256 = rulepack_sha256
            session.commit()
        return self.get(scan_id)

    def fail_processing(self, scan_id: str, reason: str) -> None:
        del reason  # structured failure storage lands with the job table
        scan_uuid = _uuid_or_404(scan_id)
        with self.sessions() as session:
            row = session.get(Scan, scan_uuid)
            if row is not None:
                row.status = "FAILED"
                session.commit()

    def _rec(self, scan_id: str | None = None, client_uuid: str | None = None) -> ScanRecord:
        with self.sessions() as s:
            q = s.query(Scan)
            q = q.filter(Scan.id == scan_id) if scan_id else q.filter(
                Scan.client_uuid == uuid.UUID(client_uuid))
            row = q.one()
            images = [EvidenceImage(
                filename="", media_type="", data=b"", sha256=image.sha256,
                width_px=image.width_px or 0, height_px=image.height_px or 0,
                storage_key=image.storage_key, panel_label=image.panel_label,
                max_edge_used=image.max_edge_used, quality=image.quality)
                for image in s.query(ScanImage).filter(ScanImage.scan_id == row.id).all()]
            batch = s.scalar(select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == row.id)) or 0
            declarations = [declaration_dict(item) for item in s.scalars(select(
                ExtractedDeclaration).where(
                    ExtractedDeclaration.scan_id == row.id,
                    ExtractedDeclaration.batch == batch).order_by(
                        ExtractedDeclaration.created_at, ExtractedDeclaration.id))]
            evaluations = [evaluation_dict(item) for item in s.scalars(select(
                RuleEvaluation).where(
                    RuleEvaluation.scan_id == row.id,
                    RuleEvaluation.batch == batch).order_by(
                        RuleEvaluation.evaluated_at, RuleEvaluation.is_override,
                        RuleEvaluation.id))]
            return ScanRecord(
                client_uuid=str(row.client_uuid), captured_at=str(row.captured_at),
                mode=row.mode, category=row.category_code,
                coverage_asserted=row.coverage_asserted,
                panels=list(row.panels_captured), images=images,
                status=row.status, id=str(row.id), overall=row.overall,
                rulepack_version=row.rulepack_version, rulepack_sha256=row.rulepack_sha256,
                batch=batch, declarations=declarations, evaluations=evaluations,
                metadata=scan_metadata(row), officer_id=str(row.officer_id),
                jurisdiction_id=str(row.jurisdiction_id))
