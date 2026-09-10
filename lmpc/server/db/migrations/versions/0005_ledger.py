"""Reports, rulepacks, amendment ledger, audit (Part 13.5)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_N = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "compliance_reports",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", pg.UUID, sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("overall_status", sa.String(24), nullable=False),
        sa.Column("pdf_storage_key", sa.Text), sa.Column("docx_storage_key", sa.Text),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("manifest", pg.JSONB, nullable=False),
        sa.Column("reviewed_by", pg.UUID, sa.ForeignKey("users.id")),
        sa.Column("review_notes", sa.Text),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
        sa.UniqueConstraint("scan_id", "version", name="uq_report_version"),
    )
    op.create_table(
        "rulepacks",
        sa.Column("version", sa.String(60), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(12), nullable=False, server_default=sa.text("'CANDIDATE'")),
        sa.Column("newest_instrument", sa.String(40)),
        sa.Column("chain_links", sa.Integer), sa.Column("chain_complete", sa.Boolean),
        sa.Column("disclosures", pg.JSONB),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", pg.UUID, sa.ForeignKey("users.id")),
        sa.Column("approval_confirmations", pg.JSONB),
        sa.CheckConstraint("state IN ('CANDIDATE','ACTIVE','ARCHIVED')", name="ck_rulepack_state"),
    )
    op.execute("CREATE UNIQUE INDEX one_active_rulepack ON rulepacks((state))"
               " WHERE state = 'ACTIVE'")
    op.create_table(
        "amendment_ledger",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("instrument_key", sa.String(40), nullable=False),
        sa.Column("family", sa.String(40)), sa.Column("prev_key", sa.String(40)),
        sa.Column("op", sa.String(20)), sa.Column("node", sa.String(80)),
        sa.Column("quote", sa.Text),
        sa.Column("source_file", sa.Text), sa.Column("source_sha256", sa.String(64)),
        sa.Column("page", sa.Integer),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'QUARANTINED'")),
        sa.Column("approved_by", pg.UUID, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("reject_reason", sa.Text),
        sa.CheckConstraint("status IN ('QUARANTINED','APPROVED','REJECTED')",
                           name="ck_ledger_status"),
    )
    op.execute("CREATE INDEX idx_ledger_node ON amendment_ledger(node)")
    op.execute("CREATE INDEX idx_ledger_status ON amendment_ledger(status)"
               " WHERE status = 'QUARANTINED'")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", pg.UUID),
        sa.Column("actor_id", pg.UUID, sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("diff", pg.JSONB), sa.Column("ip", pg.INET),
        sa.Column("user_agent", sa.Text),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=_N),
    )
    op.execute("CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_audit_time ON audit_log(occurred_at DESC)")


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("amendment_ledger")
    op.drop_table("rulepacks")
    op.drop_table("compliance_reports")