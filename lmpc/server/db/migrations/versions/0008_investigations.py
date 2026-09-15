"""Investigations: the folder a field officer works inside.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TYPES = "('RETAIL_SWEEP', 'MANUFACTURER_AUDIT', 'ECOMMERCE_SWEEP', 'COMPLAINT', " \
        "'MARKET_SURVEY', 'OTHER')"
STATUSES = "('OPEN', 'CLOSED')"


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", pg.UUID, primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_uuid", pg.UUID, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("subject_brand", sa.String(200)),
        sa.Column("investigation_type", sa.String(40), nullable=False,
                  server_default="OTHER"),
        sa.Column("location_text", sa.String(300)),
        sa.Column("geo_lat", sa.Numeric(9, 6)),
        sa.Column("geo_lng", sa.Numeric(9, 6)),
        sa.Column("created_by", pg.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("jurisdiction_id", pg.UUID, sa.ForeignKey("jurisdictions.id"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("investigation_type IN " + TYPES, name="ck_inv_type"),
        sa.CheckConstraint("status IN " + STATUSES, name="ck_inv_status"),
    )
    op.create_index("idx_inv_jurisdiction", "investigations",
                    ["jurisdiction_id", sa.text("opened_at DESC")])
    op.create_index("idx_inv_officer", "investigations",
                    ["created_by", sa.text("opened_at DESC")])
    op.create_index("idx_inv_open", "investigations", ["status"],
                    postgresql_where=sa.text("status = 'OPEN'"))

    op.create_table(
        "investigation_notes",
        sa.Column("id", pg.UUID, primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", pg.UUID,
                  sa.ForeignKey("investigations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("author_id", pg.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("storage_key", sa.String),
        sa.Column("sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_inv_note", "investigation_notes",
                    ["investigation_id", sa.text("created_at DESC")])

    op.add_column("scans", sa.Column(
        "investigation_id", pg.UUID,
        sa.ForeignKey("investigations.id", ondelete="SET NULL")))
    op.create_index("idx_scans_investigation", "scans",
                    ["investigation_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_scans_investigation", table_name="scans")
    op.drop_column("scans", "investigation_id")
    op.drop_index("idx_inv_note", table_name="investigation_notes")
    op.drop_table("investigation_notes")
    for name in ("idx_inv_open", "idx_inv_officer", "idx_inv_jurisdiction"):
        op.drop_index(name, table_name="investigations")
    op.drop_table("investigations")
