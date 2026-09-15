"""Two kinds of report, and reports that belong to an investigation.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("compliance_reports", sa.Column(
        "report_kind", sa.String(12), nullable=False, server_default="FINALIZED"))
    op.add_column("compliance_reports", sa.Column(
        "generated_by", pg.UUID, sa.ForeignKey("users.id")))
    op.add_column("compliance_reports", sa.Column(
        "investigation_id", pg.UUID,
        sa.ForeignKey("investigations.id", ondelete="CASCADE")))
    op.create_check_constraint(
        "ck_report_kind", "compliance_reports",
        "report_kind IN ('FIELD', 'FINALIZED')")
    # An investigation report has no single scan.
    op.alter_column("compliance_reports", "scan_id", nullable=True)
    op.drop_constraint("uq_report_version", "compliance_reports", type_="unique")
    op.create_unique_constraint(
        "uq_report_version", "compliance_reports", ["scan_id", "report_kind", "version"])
    op.create_unique_constraint(
        "uq_investigation_report_version", "compliance_reports",
        ["investigation_id", "report_kind", "version"])


def downgrade() -> None:
    op.drop_constraint("uq_investigation_report_version", "compliance_reports",
                       type_="unique")
    op.drop_constraint("uq_report_version", "compliance_reports", type_="unique")
    op.create_unique_constraint(
        "uq_report_version", "compliance_reports", ["scan_id", "version"])
    op.alter_column("compliance_reports", "scan_id", nullable=False)
    op.drop_constraint("ck_report_kind", "compliance_reports", type_="check")
    for column in ("investigation_id", "generated_by", "report_kind"):
        op.drop_column("compliance_reports", column)
