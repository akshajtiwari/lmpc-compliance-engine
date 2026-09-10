"""Managed users and one-use mobile device enrollment.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_enrollments",
        sa.Column("id", pg.UUID, primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", pg.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("server_url", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("device_name", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_device_enrollment_user", "device_enrollments", ["user_id"])
    op.create_index("idx_device_enrollment_expiry", "device_enrollments", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_device_enrollment_expiry", table_name="device_enrollments")
    op.drop_index("idx_device_enrollment_user", table_name="device_enrollments")
    op.drop_table("device_enrollments")
