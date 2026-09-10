"""Extraction and evaluation (Part 13.4). rule_evaluations is append-only.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_N = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "extracted_declarations",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", pg.UUID, sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scan_image_id", pg.UUID, sa.ForeignKey("scan_images.id")),
        sa.Column("batch", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("field_type", sa.String(40), nullable=False),
        sa.Column("raw_text", sa.Text),
        sa.Column("normalized_value", pg.JSONB),
        sa.Column("bbox_x", sa.Integer), sa.Column("bbox_y", sa.Integer),
        sa.Column("bbox_w", sa.Integer), sa.Column("bbox_h", sa.Integer),
        sa.Column("ocr_confidence", sa.Numeric(4, 3)),
        sa.Column("score", sa.Numeric(6, 2)),
        sa.Column("runner_up_margin", sa.Numeric(6, 2)),
        sa.Column("feature_weights", pg.JSONB),
        sa.Column("source_token_ids", pg.JSONB),
        sa.Column("is_composite", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_repaired", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("glyph_height_px", sa.Numeric(8, 2)),
        sa.Column("glyph_height_mm", sa.Numeric(6, 2)),
        sa.Column("is_on_pdp", sa.Boolean),
        sa.Column("corrected_by", pg.UUID, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
    )
    op.create_index("idx_extracted_scan", "extracted_declarations", ["scan_id", "batch"])
    op.create_table(
        "rule_evaluations",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", pg.UUID, sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("check_code", sa.String(60), nullable=False),
        sa.Column("clause", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(25), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("citation", pg.JSONB, nullable=False),
        sa.Column("evidence", pg.JSONB),
        sa.Column("rulepack_version", sa.String(60), nullable=False),
        sa.Column("law_version", sa.Date),
        sa.Column("evidence_declaration_id", pg.UUID,
                  sa.ForeignKey("extracted_declarations.id")),
        sa.Column("is_override", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("override_of_evaluation_id", pg.UUID,
                  sa.ForeignKey("rule_evaluations.id")),
        sa.Column("override_reason", sa.Text),
        sa.Column("overridden_by", pg.UUID, sa.ForeignKey("users.id")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
        sa.CheckConstraint("outcome IN ('PASS','FAIL','INDETERMINATE','NOT_APPLICABLE',"
                           "'REVIEW_REQUIRED','SYSTEM_ERROR')", name="ck_eval_outcome"),
        sa.CheckConstraint("NOT is_override OR (override_reason IS NOT NULL"
                           " AND overridden_by IS NOT NULL)", name="ck_override_provenance"),
    )
    op.execute("CREATE INDEX idx_eval_scan ON rule_evaluations(scan_id, batch)")
    op.execute("CREATE INDEX idx_eval_check ON rule_evaluations(check_code, outcome)")
    # Append-only: the application role may only INSERT and SELECT (13.4).
    op.execute("REVOKE UPDATE, DELETE ON rule_evaluations FROM PUBLIC")


def downgrade() -> None:
    op.drop_table("rule_evaluations")
    op.drop_index("idx_extracted_scan", table_name="extracted_declarations")
    op.drop_table("extracted_declarations")