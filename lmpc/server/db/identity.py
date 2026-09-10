"""Identity and access tables (Part 13.1)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary,
                        String, Text, Uuid, func, text)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CITEXT, LTREE

ROLES = ("FIELD_OFFICER", "REVIEWING_OFFICER", "ADMIN", "AUDITOR")


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    state: Mapped[str] = mapped_column(String(100))
    parent_jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jurisdictions.id"))
    path: Mapped[str | None] = mapped_column(LTREE)
    __table_args__ = (Index("uq_jurisdiction_name_state", name, state, unique=True),
                      Index("idx_jurisdiction_path", path, postgresql_using="gist"))


class User(Base):
    """A local password is optional; OIDC-only users keep password_hash NULL."""
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(30))
    is_legal_reviewer: Mapped[bool] = mapped_column(Boolean, default=False)
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jurisdictions.id"))
    department: Mapped[str | None] = mapped_column(String(150))
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)   # NULL when SSO-only
    mfa_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_login_window_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 only
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    __table_args__ = (
        Index("idx_refresh_user", user_id,
              postgresql_where=text("revoked_at IS NULL")),
        Index("idx_refresh_family", family_id),
    )
