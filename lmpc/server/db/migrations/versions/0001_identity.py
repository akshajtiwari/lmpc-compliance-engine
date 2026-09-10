"""Identity and access (Part 13.1)

Revision ID: 0001
Revises:
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from lmpc.server.db.base import CITEXT, LTREE

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.create_table(
        "jurisdictions",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("parent_jurisdiction_id", pg.UUID, sa.ForeignKey("jurisdictions.id")),
        sa.Column("path", LTREE()),
        sa.UniqueConstraint("name", "state", name="uq_jurisdiction_name_state"),
    )
    op.execute("CREATE INDEX idx_jurisdiction_path ON jurisdictions USING gist (path)")
    op.create_table(
        "users",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", CITEXT(), nullable=False, unique=True),
        sa.Column("phone", sa.String(20)),
        sa.Column("role", sa.String(30), nullable=False),
        sa.CheckConstraint(
            "role IN ('FIELD_OFFICER','REVIEWING_OFFICER','ADMIN','AUDITOR')",
            name="ck_users_role"),
        sa.Column("is_legal_reviewer", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("jurisdiction_id", pg.UUID, sa.ForeignKey("jurisdictions.id")),
        sa.Column("department", sa.String(150)),
        sa.Column("external_subject", sa.String(255), unique=True),
        sa.Column("password_hash", sa.Text),
        sa.Column("mfa_secret_enc", sa.LargeBinary),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.Text),
        sa.Column("ip", pg.INET),
    )
    op.execute("CREATE INDEX idx_refresh_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL")


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("jurisdictions")
