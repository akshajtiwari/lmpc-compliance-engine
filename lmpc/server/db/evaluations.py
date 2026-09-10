"""Extraction and evaluation tables (Part 13.4). rule_evaluations is append-only."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
                        Integer, Numeric, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, JSONB

OUTCOMES = ("PASS", "FAIL", "INDETERMINATE", "NOT_APPLICABLE", "REVIEW_REQUIRED",
            "SYSTEM_ERROR")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class ExtractedDeclaration(Base):
    __tablename__ = "extracted_declarations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("scans.id", ondelete="CASCADE"))
    scan_image_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("scan_images.id"))
    batch: Mapped[int] = mapped_column(Integer, default=1)
    field_type: Mapped[str] = mapped_column(String(40))
    raw_text: Mapped[str | None] = mapped_column(String)
    normalized_value: Mapped[dict | None] = mapped_column(JSONB)
    bbox_x: Mapped[int | None] = mapped_column(Integer)
    bbox_y: Mapped[int | None] = mapped_column(Integer)
    bbox_w: Mapped[int | None] = mapped_column(Integer)
    bbox_h: Mapped[int | None] = mapped_column(Integer)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    runner_up_margin: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    feature_weights: Mapped[dict | None] = mapped_column(JSONB)   # why this won (9.3)
    source_token_ids: Mapped[list | None] = mapped_column(JSONB)
    is_composite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_repaired: Mapped[bool] = mapped_column(Boolean, default=False)     # P9
    glyph_height_px: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    glyph_height_mm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    is_on_pdp: Mapped[bool | None] = mapped_column(Boolean)
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("idx_extracted_scan", scan_id, batch),)


class RuleEvaluation(Base):
    """Append-only: overrides insert a new row pointing at the original (13.4)."""
    __tablename__ = "rule_evaluations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("scans.id", ondelete="CASCADE"))
    batch: Mapped[int] = mapped_column(Integer, default=1)
    check_code: Mapped[str] = mapped_column(String(60))
    clause: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(25))
    reason: Mapped[str] = mapped_column(String)
    citation: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    rulepack_version: Mapped[str] = mapped_column(String(60))
    law_version: Mapped[date | None] = mapped_column(Date)
    evidence_declaration_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("extracted_declarations.id"))
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_of_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rule_evaluations.id"))
    override_reason: Mapped[str | None] = mapped_column(String)
    overridden_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("outcome IN " + _in(OUTCOMES), name="ck_eval_outcome"),
        CheckConstraint("NOT is_override OR (override_reason IS NOT NULL"
                        " AND overridden_by IS NOT NULL)", name="ck_override_provenance"),
        Index("idx_eval_scan", scan_id, batch),
        Index("idx_eval_check", check_code, outcome),
    )
