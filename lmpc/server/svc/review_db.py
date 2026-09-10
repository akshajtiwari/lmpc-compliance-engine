"""PostgreSQL implementation of the scoped inspection review repository."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, cast, exists, func, or_, select

from ..api.errors import ApiError
from ..db.models import (AuditLog, CommodityCategory, ExtractedDeclaration,
                         Jurisdiction, Manufacturer, Product, RuleEvaluation, Scan,
                         ScanImage)
from .store_records import declaration_dict, evaluation_dict


class ReviewDb:
    def __init__(self, scan_store):
        self.scans = scan_store
        self.sessions = scan_store.sessions

    def list_scans(self, principal, filters: dict, page: int,
                   page_size: int, sort: str) -> dict:
        statement = select(Scan, Product.brand_name, Manufacturer.name).outerjoin(
            Product, Product.id == Scan.product_id).outerjoin(
                Manufacturer, Manufacturer.id == Product.manufacturer_id)
        statement = self.scope_scans(statement, principal)
        statement = self._filters(statement, filters)
        count = select(func.count(Scan.id)).outerjoin(
            Product, Product.id == Scan.product_id).outerjoin(
                Manufacturer, Manufacturer.id == Product.manufacturer_id)
        count = self._filters(self.scope_scans(count, principal), filters)
        order = {
            "newest": Scan.captured_at.desc(), "oldest": Scan.captured_at.asc(),
            "status": Scan.status.asc(), "overall": Scan.overall.asc(),
        }[sort]
        statement = statement.order_by(order, Scan.created_at.desc()).offset(
            (page - 1) * page_size).limit(page_size)
        with self.sessions() as session:
            total = session.scalar(count) or 0
            rows = session.execute(statement).all()
        return {
            "items": [_summary(scan, brand, manufacturer)
                      for scan, brand, manufacturer in rows],
            "page": page, "page_size": page_size, "total": total,
            "pages": (total + page_size - 1) // page_size,
        }

    def update_scan(self, scan_id: str, changes: dict, principal) -> object:
        scan_uuid = _uuid(scan_id, "scan")
        with self.sessions() as session:
            row = session.get(Scan, scan_uuid, with_for_update=True)
            if row is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            before = _mutable(row)
            if "product_id" in changes:
                product_id = changes["product_id"]
                parsed = _uuid(product_id, "product") if product_id else None
                if parsed and session.get(Product, parsed) is None:
                    raise ApiError("E_VALIDATION", f"product {product_id} does not exist")
                row.product_id = parsed
            if "package_shape" in changes:
                row.package_shape = changes["package_shape"]
            if "category" in changes:
                if session.get(CommodityCategory, changes["category"]) is None:
                    raise ApiError("E_VALIDATION", "unknown commodity category")
                row.category_code = changes["category"]
            for key, value in (changes.get("dimensions") or {}).items():
                setattr(row, {"h_cm": "pdp_h_cm", "w_cm": "pdp_w_cm",
                              "capacity_cm3": "capacity_cm3"}[key], value)
            row.updated_at = datetime.now(UTC)
            if row.status == "EVALUATION_COMPLETE":
                row.status, row.overall = "RECEIVED", None
            session.add(_audit(principal.id, "scan", row.id, "SCAN_UPDATED",
                               {"before": before, "after": _mutable(row)}))
            session.commit()
        return self.scans.get(scan_id)

    def correct(self, scan_id: str, field: str, text: str, bbox: list[int] | None,
                normalized: dict, principal) -> dict:
        scan_uuid = _uuid(scan_id, "scan")
        with self.sessions() as session:
            scan = session.get(Scan, scan_uuid, with_for_update=True)
            if scan is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            original = session.scalar(select(ExtractedDeclaration).where(
                ExtractedDeclaration.scan_id == scan_uuid,
                ExtractedDeclaration.field_type == field).order_by(
                    ExtractedDeclaration.created_at.desc(),
                    ExtractedDeclaration.id.desc()).limit(1))
            batch = session.scalar(select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == scan_uuid)) or 1
            image_id = original.scan_image_id if original else session.scalar(select(
                ScanImage.id).where(ScanImage.scan_id == scan_uuid).order_by(
                    ScanImage.created_at).limit(1))
            bounds = bbox or (_bounds(original) if original else [0, 0, max(8, len(text) * 8), 22])
            row = ExtractedDeclaration(
                scan_id=scan_uuid, scan_image_id=image_id, batch=batch,
                field_type=field, raw_text=text, normalized_value=normalized,
                bbox_x=bounds[0], bbox_y=bounds[1], bbox_w=bounds[2], bbox_h=bounds[3],
                ocr_confidence=1, score=100, runner_up_margin=100,
                feature_weights={"officer_correction": 100}, source_token_ids=[],
                is_composite=False, is_repaired=False, glyph_height_px=bounds[3],
                is_on_pdp=True, corrected_by=uuid.UUID(principal.id))
            session.add(row)
            session.flush()
            row.source_token_ids = [f"correction:{row.id}"]
            session.add(_audit(principal.id, "declaration", row.id,
                               "DECLARATION_CORRECT",
                               {"field": field, "original_id": (str(original.id)
                                if original else None), "text": text}))
            session.commit()
            session.refresh(row)
            panel = session.scalar(select(ScanImage.panel_label).where(
                ScanImage.id == row.scan_image_id)) if row.scan_image_id else "FRONT"
            return declaration_dict(row, panel or "FRONT")

    def corrections(self, scan_id: str) -> list[dict]:
        scan_uuid = _uuid(scan_id, "scan")
        with self.sessions() as session:
            rows = list(session.scalars(select(ExtractedDeclaration).where(
                ExtractedDeclaration.scan_id == scan_uuid,
                ExtractedDeclaration.corrected_by.is_not(None)).order_by(
                    ExtractedDeclaration.created_at, ExtractedDeclaration.id)))
            panels = {row.id: panel for row, panel in session.execute(select(
                ExtractedDeclaration, ScanImage.panel_label).join(
                    ScanImage, ScanImage.id == ExtractedDeclaration.scan_image_id,
                    isouter=True).where(ExtractedDeclaration.id.in_(
                        [item.id for item in rows])))} if rows else {}
        effective = {}
        for row in rows:
            effective[row.field_type] = declaration_dict(row, panels.get(row.id) or "FRONT")
        return list(effective.values())

    def evaluations(self, scan_id: str, batch: int | None) -> tuple[int, list[dict]]:
        scan_uuid = _uuid(scan_id, "scan")
        with self.sessions() as session:
            if session.get(Scan, scan_uuid) is None:
                raise ApiError("E_NOT_FOUND", f"scan {scan_id} not found")
            selected = batch or session.scalar(select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == scan_uuid)) or 0
            rows = session.scalars(select(RuleEvaluation).where(
                RuleEvaluation.scan_id == scan_uuid,
                RuleEvaluation.batch == selected).order_by(
                    RuleEvaluation.evaluated_at, RuleEvaluation.is_override,
                    RuleEvaluation.id)).all()
        return selected, [evaluation_dict(row) for row in rows]

    def override(self, scan_id: str, evaluation_id: str, outcome: str,
                 reason: str, principal) -> dict:
        scan_uuid, evaluation_uuid = _uuid(scan_id, "scan"), _uuid(
            evaluation_id, "evaluation")
        with self.sessions() as session:
            scan = session.get(Scan, scan_uuid, with_for_update=True)
            target = session.get(RuleEvaluation, evaluation_uuid, with_for_update=True)
            if scan is None or target is None or target.scan_id != scan_uuid:
                raise ApiError("E_NOT_FOUND", "scan or evaluation not found")
            if scan.status == "FINALIZED":
                raise ApiError("E_SCAN_FINALIZED", "a finalized finding cannot be overridden")
            root_id = target.override_of_evaluation_id or target.id
            row = RuleEvaluation(
                scan_id=scan_uuid, batch=target.batch, check_code=target.check_code,
                clause=target.clause, outcome=outcome,
                reason=f"Officer override from {target.outcome}: {reason}",
                citation=target.citation, evidence=target.evidence,
                rulepack_version=target.rulepack_version, law_version=target.law_version,
                evidence_declaration_id=target.evidence_declaration_id,
                is_override=True, override_of_evaluation_id=root_id,
                override_reason=reason, overridden_by=uuid.UUID(principal.id))
            session.add(row)
            session.flush()
            latest = session.scalar(select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == scan_uuid)) or 0
            if target.batch == latest:
                rows = session.scalars(select(RuleEvaluation).where(
                    RuleEvaluation.scan_id == scan_uuid,
                    RuleEvaluation.batch == latest).order_by(
                        RuleEvaluation.evaluated_at, RuleEvaluation.is_override,
                        RuleEvaluation.id)).all()
                scan.overall = overall([evaluation_dict(item) for item in rows])
            session.add(_audit(principal.id, "rule_evaluation", row.id,
                               "EVALUATION_OVERRIDE", {
                                   "original_id": str(root_id), "from": target.outcome,
                                   "to": outcome, "reason": reason}))
            session.commit()
            session.refresh(row)
            return evaluation_dict(row)

    def scope_scans(self, statement, principal):
        if principal.disabled_auth or principal.role == "ADMIN":
            return statement
        if principal.role == "FIELD_OFFICER":
            return statement.where(Scan.officer_id == uuid.UUID(principal.id))
        root_path = select(Jurisdiction.path).where(
            Jurisdiction.id == uuid.UUID(principal.jurisdiction_id)).scalar_subquery()
        descendants = select(Jurisdiction.id).where(Jurisdiction.path.op("<@")(root_path))
        return statement.where(Scan.jurisdiction_id.in_(descendants))

    def _filters(self, statement, values: dict):
        exact = {"category": Scan.category_code, "status": Scan.status,
                 "overall": Scan.overall, "officer_id": Scan.officer_id,
                 "jurisdiction_id": Scan.jurisdiction_id}
        for key, column in exact.items():
            if values.get(key) is not None:
                statement = statement.where(column == values[key])
        if values.get("date_from"):
            statement = statement.where(Scan.captured_at >= values["date_from"])
        if values.get("date_to"):
            statement = statement.where(Scan.captured_at <= values["date_to"])
        if values.get("manufacturer"):
            statement = statement.where(Manufacturer.name.ilike(
                f"%{values['manufacturer']}%"))
        if values.get("brand"):
            statement = statement.where(Product.brand_name.ilike(f"%{values['brand']}%"))
        if values.get("q"):
            needle = f"%{values['q']}%"
            statement = statement.where(or_(
                Manufacturer.name.ilike(needle), Product.brand_name.ilike(needle),
                Scan.ecommerce_text.ilike(needle),
                cast(Scan.client_uuid, String).ilike(needle)))
        if values.get("violation_type"):
            latest = select(func.max(RuleEvaluation.batch)).where(
                RuleEvaluation.scan_id == Scan.id).correlate(Scan).scalar_subquery()
            statement = statement.where(exists(select(RuleEvaluation.id).where(
                RuleEvaluation.scan_id == Scan.id, RuleEvaluation.batch == latest,
                RuleEvaluation.check_code == values["violation_type"],
                RuleEvaluation.outcome == "FAIL")))
        return statement


def overall(rows: list[dict]) -> str:
    effective = {}
    for row in rows:
        effective[row["check"]] = row["outcome"]
    outcomes = list(effective.values())
    return ("SYSTEM_ERROR" if "SYSTEM_ERROR" in outcomes else
            "NON_COMPLIANT" if "FAIL" in outcomes else
            "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in outcomes else
            "INCOMPLETE_EVIDENCE" if "INDETERMINATE" in outcomes else
            "OUT_OF_SCOPE" if outcomes and all(v == "NOT_APPLICABLE" for v in outcomes)
            else "COMPLIANT")


def _summary(row: Scan, brand: str | None, manufacturer: str | None) -> dict:
    return {
        "id": str(row.id), "client_uuid": str(row.client_uuid),
        "captured_at": str(row.captured_at), "created_at": row.created_at.isoformat(),
        "mode": row.mode, "category": row.category_code, "status": row.status,
        "overall": row.overall, "coverage_asserted": row.coverage_asserted,
        "officer_id": str(row.officer_id), "jurisdiction_id": str(row.jurisdiction_id),
        "product_id": str(row.product_id) if row.product_id else None,
        "brand": brand, "manufacturer": manufacturer,
    }


def _mutable(row: Scan) -> dict:
    return {"product_id": str(row.product_id) if row.product_id else None,
            "package_shape": row.package_shape, "category": row.category_code,
            "dimensions": {"h_cm": float(row.pdp_h_cm) if row.pdp_h_cm else None,
                           "w_cm": float(row.pdp_w_cm) if row.pdp_w_cm else None,
                           "capacity_cm3": (float(row.capacity_cm3)
                                            if row.capacity_cm3 else None)}}


def _bounds(row: ExtractedDeclaration) -> list[int]:
    return [row.bbox_x or 0, row.bbox_y or 0, row.bbox_w or 8, row.bbox_h or 22]


def _uuid(value: str, kind: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise ApiError("E_NOT_FOUND", f"{kind} {value} not found") from None


def _audit(actor: str, entity_type: str, entity_id: uuid.UUID,
           action: str, diff: dict) -> AuditLog:
    return AuditLog(entity_type=entity_type, entity_id=entity_id,
                    actor_id=uuid.UUID(actor), action=action, diff=diff)
