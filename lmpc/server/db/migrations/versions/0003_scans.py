"""Scans and evidence (Part 13.3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_N = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_uuid", pg.UUID, unique=True),
        sa.Column("product_id", pg.UUID, sa.ForeignKey("products.id")),
        sa.Column("officer_id", pg.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("jurisdiction_id", pg.UUID, sa.ForeignKey("jurisdictions.id"), nullable=False),
        sa.Column("captured_at", sa.Date, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("category_code", sa.String(50),
                  sa.ForeignKey("commodity_categories.code"), nullable=False),
        sa.Column("buyer_type", sa.String(20), nullable=False, server_default=sa.text("'RETAIL'")),
        sa.Column("package_shape", sa.String(20)),
        sa.Column("coverage_asserted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("panels_captured", pg.ARRAY(sa.String(10)), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("glyph_segmentation", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("scale_reference_type", sa.String(20)),
        sa.Column("scale_reference_data", pg.JSONB),
        sa.Column("px_per_mm", sa.Numeric(8, 3)),
        sa.Column("pdp_h_cm", sa.Numeric(7, 2)), sa.Column("pdp_w_cm", sa.Numeric(7, 2)),
        sa.Column("pdp_area_cm2", sa.Numeric(10, 2)),
        sa.Column("capacity_cm3", sa.Numeric(10, 2)),
        sa.Column("net_quantity_g", sa.Numeric(12, 3)),
        sa.Column("net_quantity_ml", sa.Numeric(12, 3)),
        sa.Column("is_imported", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_molded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("other_law_requires_same_info", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ecommerce_url", sa.Text), sa.Column("ecommerce_text", sa.Text),
        sa.Column("geo_lat", sa.Numeric(9, 6)), sa.Column("geo_lng", sa.Numeric(9, 6)),
        sa.Column("rulepack_version", sa.String(60)),
        sa.Column("rulepack_sha256", sa.String(64)),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'RECEIVED'")),
        sa.Column("overall", sa.String(24)),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
        sa.CheckConstraint("mode IN ('PHYSICAL_PACKAGE','ECOMMERCE_LISTING')", name="ck_scans_mode"),
        sa.CheckConstraint("buyer_type IN ('RETAIL','INDUSTRIAL','INSTITUTIONAL')", name="ck_scans_buyer"),
        sa.CheckConstraint("package_shape IN ('RECTANGULAR','CYLINDRICAL','IRREGULAR')",
                           name="ck_scans_shape"),
        sa.CheckConstraint("scale_reference_type IN"
                           " ('ISO_ID1_CARD','APRILTAG_36H11','MANUAL_DIMENSIONS','NONE')",
                           name="ck_scans_scale"),
        sa.CheckConstraint("status IN ('RECEIVED','OCR_IN_PROGRESS','OCR_COMPLETE',"
                           "'EXTRACTION_COMPLETE','EVALUATION_COMPLETE','UNDER_REVIEW',"
                           "'FINALIZED','SYNC_CONFLICT','FAILED')", name="ck_scans_status"),
    )
    op.execute("CREATE INDEX idx_scans_jur_date ON scans(jurisdiction_id, captured_at DESC)")
    op.execute("CREATE INDEX idx_scans_status ON scans(status) WHERE status <> 'FINALIZED'")
    op.execute("CREATE INDEX idx_scans_officer ON scans(officer_id, created_at DESC)")
    op.create_index("idx_scans_product", "scans", ["product_id"])
    op.create_table(
        "scan_images",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", pg.UUID, sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("panel_label", sa.String(10), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width_px", sa.Integer), sa.Column("height_px", sa.Integer),
        sa.Column("max_edge_used", sa.Integer),
        sa.Column("quality", pg.JSONB),
        sa.Column("upload_status", sa.String(20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
        sa.UniqueConstraint("scan_id", "panel_label", "sha256", name="uq_scan_image"),
        sa.CheckConstraint("upload_status IN ('PENDING','UPLOADING','UPLOADED','FAILED')",
                           name="ck_scan_images_upload"),
    )


def downgrade() -> None:
    op.drop_table("scan_images")
    op.drop_index("idx_scans_product", table_name="scans")
    op.drop_table("scans")