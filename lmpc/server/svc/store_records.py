"""Stable dictionary projections shared by persistence and review services."""
from __future__ import annotations

from datetime import date

from ..db.models import ComplianceReport, ExtractedDeclaration, RuleEvaluation, Scan


def optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def declaration_dict(row: ExtractedDeclaration, panel: str | None = None) -> dict:
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
        "corrected_by": str(row.corrected_by) if row.corrected_by else None,
        "glyph_height_px": (float(row.glyph_height_px)
                            if row.glyph_height_px is not None else None),
        "panel": panel,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def evaluation_dict(row: RuleEvaluation) -> dict:
    return {
        "id": str(row.id), "batch": row.batch, "check": row.check_code,
        "clause": row.clause, "outcome": row.outcome, "reason": row.reason,
        "citation": row.citation, "evidence": row.evidence or {},
        "law_version": str(row.law_version) if row.law_version else None,
        "is_override": row.is_override,
        "override_of_evaluation_id": (str(row.override_of_evaluation_id)
                                      if row.override_of_evaluation_id else None),
        "override_reason": row.override_reason,
        "overridden_by": str(row.overridden_by) if row.overridden_by else None,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
    }


def scan_metadata(row: Scan) -> dict:
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


def report_dict(row: ComplianceReport) -> dict:
    return {
        "id": str(row.id), "scan_id": str(row.scan_id), "version": row.version,
        "overall_status": row.overall_status, "pdf_storage_key": row.pdf_storage_key,
        "docx_storage_key": row.docx_storage_key,
        "content_sha256": row.content_sha256, "manifest": row.manifest,
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
        "finalized_at": row.finalized_at.isoformat(),
    }
