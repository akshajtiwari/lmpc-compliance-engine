"""The backing store behind POST /scans: Postgres when configured, memory otherwise.

Idempotency is a database guarantee, not a service promise: scans.client_uuid is
UNIQUE and the insert is ON CONFLICT DO NOTHING, so two racing submissions —
the offline queue retries after a timeout — cannot create a second scan (Part 12.3).
"""
from __future__ import annotations
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.exc import NoResultFound

from ..api.errors import ApiError
from ..config import Settings
from ..db import sessionmaker_of
from ..db.models import ExtractedDeclaration, RuleEvaluation, Scan, ScanImage
from .evidence import EvidenceImage
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
               images: list[EvidenceImage],
               metadata: dict[str, Any] | None = None) -> tuple[ScanRecord, bool]:
        validate(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                 category=category, coverage_asserted=coverage_asserted, panels=panels,
                 n_images=len(images))
        with self.sessions() as s:
            row = s.execute(
                insert(Scan)
                .values(client_uuid=client_uuid, captured_at=captured_at, mode=mode,
                        category_code=category, coverage_asserted=coverage_asserted,
                        panels_captured=panels, officer_id=self.officer_id,
                        jurisdiction_id=self.jurisdiction_id, **(metadata or {}))
                .on_conflict_do_nothing(index_elements=[Scan.client_uuid])
                .returning(Scan.id)).first()
            if row is None:                       # the race lost: return the winner
                s.commit()
                return self._rec(client_uuid=client_uuid), False
            s.add_all(ScanImage(
                scan_id=row[0], panel_label=image.panel_label,
                storage_key=image.storage_key, sha256=image.sha256,
                width_px=image.width_px, height_px=image.height_px,
                upload_status="UPLOADED") for image in images)
            s.commit()
            return self._rec(scan_id=str(row[0])), True

    def get(self, scan_id: str) -> ScanRecord:
        try:
            return self._rec(scan_id=str(uuid.UUID(scan_id)))
        except (ValueError, NoResultFound):
            raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found") from None

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
                    is_on_pdp=item["panel"] == "FRONT")
                session.add(declaration)
                session.flush()
                field_ids[item["field"]] = declaration.id
            for item in evaluations:
                session.add(RuleEvaluation(
                    scan_id=scan_uuid, batch=batch, check_code=item["check"],
                    clause=item["clause"], outcome=item["outcome"], reason=item["reason"],
                    citation=item["citation"], evidence=item["evidence"],
                    rulepack_version=rulepack_version,
                    law_version=_optional_date(item["law_version"]),
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
                max_edge_used=image.max_edge_used)
                for image in s.query(ScanImage).filter(ScanImage.scan_id == row.id).all()]
            batch = s.scalar(select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == row.id)) or 0
            declarations = [_declaration_dict(item) for item in s.scalars(select(
                ExtractedDeclaration).where(
                    ExtractedDeclaration.scan_id == row.id,
                    ExtractedDeclaration.batch == batch))]
            evaluations = [_evaluation_dict(item) for item in s.scalars(select(
                RuleEvaluation).where(
                    RuleEvaluation.scan_id == row.id,
                    RuleEvaluation.batch == batch))]
            return ScanRecord(
                client_uuid=str(row.client_uuid), captured_at=str(row.captured_at),
                mode=row.mode, category=row.category_code,
                coverage_asserted=row.coverage_asserted,
                panels=list(row.panels_captured), images=images,
                status=row.status, id=str(row.id), overall=row.overall,
                rulepack_version=row.rulepack_version, rulepack_sha256=row.rulepack_sha256,
                batch=batch, declarations=declarations, evaluations=evaluations,
                metadata=_metadata(row))


def _uuid_or_404(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ApiError("E_NOT_FOUND", f"scan {value} not found") from None


def _optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _declaration_dict(row: ExtractedDeclaration) -> dict:
    return {
        "id": str(row.id), "batch": row.batch, "field": row.field_type,
        "text": row.raw_text, "normalized_value": row.normalized_value or {},
        "bbox": [row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h],
        "confidence": float(row.ocr_confidence) if row.ocr_confidence is not None else None,
        "score": float(row.score) if row.score is not None else None,
        "margin": float(row.runner_up_margin) if row.runner_up_margin is not None else None,
        "feature_weights": row.feature_weights or {},
        "source_token_ids": row.source_token_ids or [],
        "is_composite": row.is_composite, "is_repaired": row.is_repaired,
        "glyph_height_px": (float(row.glyph_height_px)
                            if row.glyph_height_px is not None else None),
    }


def _evaluation_dict(row: RuleEvaluation) -> dict:
    return {
        "id": str(row.id), "batch": row.batch, "check": row.check_code,
        "clause": row.clause, "outcome": row.outcome, "reason": row.reason,
        "citation": row.citation, "evidence": row.evidence or {},
        "law_version": str(row.law_version) if row.law_version else None,
        "is_override": row.is_override,
    }


def _metadata(row: Scan) -> dict:
    return {
        "buyer_type": row.buyer_type, "package_shape": row.package_shape,
        "scale_reference_type": row.scale_reference_type,
        "scale_reference_data": row.scale_reference_data,
        "px_per_mm": float(row.px_per_mm) if row.px_per_mm is not None else None,
        "pdp_h_cm": float(row.pdp_h_cm) if row.pdp_h_cm is not None else None,
        "pdp_w_cm": float(row.pdp_w_cm) if row.pdp_w_cm is not None else None,
        "capacity_cm3": float(row.capacity_cm3) if row.capacity_cm3 is not None else None,
        "net_quantity_g": (float(row.net_quantity_g)
                           if row.net_quantity_g is not None else None),
        "net_quantity_ml": (float(row.net_quantity_ml)
                            if row.net_quantity_ml is not None else None),
        "is_imported": row.is_imported, "is_molded": row.is_molded,
        "other_law_requires_same_info": row.other_law_requires_same_info,
        "geo_lat": float(row.geo_lat) if row.geo_lat is not None else None,
        "geo_lng": float(row.geo_lng) if row.geo_lng is not None else None,
        "ecommerce_url": row.ecommerce_url, "ecommerce_text": row.ecommerce_text,
    }
