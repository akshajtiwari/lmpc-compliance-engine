"""Local-password lockout and refresh-token family rotation.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "failed_login_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("failed_login_window_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True)))
    op.add_column("refresh_tokens", sa.Column("family_id", pg.UUID))
    op.execute("UPDATE refresh_tokens SET family_id = gen_random_uuid() WHERE family_id IS NULL")
    op.alter_column("refresh_tokens", "family_id", nullable=False)
    op.create_index("idx_refresh_family", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_family", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "family_id")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_window_at")
    op.drop_column("users", "failed_login_count")
