"""Investigations: the folder an officer works inside (Part 13.6).

A scan used to be the only unit of work, which left an officer with a flat list of
inspections and no way to say "these forty belong to the Britannia sweep". An
investigation groups them: a name, a place, a type, and everything captured under it.

Access is by **jurisdiction, not by officer**. Two officers walking the same market feed
one case file, so `created_by` records who opened it while `jurisdiction_id` decides who
may see it. This is deliberately wider than the own-scans-only rule a field officer has
over individual scans.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (CheckConstraint, ForeignKey, Index, String, Text, func,
                        text)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ScaledNumeric, UtcDateTime, UuidCol

TYPES = ("RETAIL_SWEEP", "MANUFACTURER_AUDIT", "ECOMMERCE_SWEEP", "COMPLAINT",
         "MARKET_SURVEY", "OTHER")
STATUSES = ("OPEN", "CLOSED")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[uuid.UUID] = mapped_column(UuidCol, primary_key=True, default=uuid.uuid4)
    # Created on the phone, possibly with no network. The same UUID arrives again on every
    # retry, and UNIQUE is what makes the retry idempotent — exactly as scans.client_uuid
    # does for an inspection.
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(UuidCol, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    subject_brand: Mapped[str | None] = mapped_column(String(200))
    investigation_type: Mapped[str] = mapped_column(String(40), default="OTHER")
    location_text: Mapped[str | None] = mapped_column(String(300))
    geo_lat: Mapped[Decimal | None] = mapped_column(ScaledNumeric(9, 6))
    geo_lng: Mapped[Decimal | None] = mapped_column(ScaledNumeric(9, 6))

    created_by: Mapped[uuid.UUID] = mapped_column(UuidCol, ForeignKey("users.id"))
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UuidCol, ForeignKey("jurisdictions.id"))

    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    __table_args__ = (
        CheckConstraint("investigation_type IN " + _in(TYPES), name="ck_inv_type"),
        CheckConstraint("status IN " + _in(STATUSES), name="ck_inv_status"),
        Index("idx_inv_jurisdiction", jurisdiction_id, opened_at.desc()),
        Index("idx_inv_officer", created_by, opened_at.desc()),
        Index("idx_inv_open", status,
              postgresql_where=text("status = 'OPEN'"),
              sqlite_where=text("status = 'OPEN'")),
    )


class InvestigationNote(Base):
    """Append-only. An editable notes blob would destroy the attribution trail: a report
    that quotes an officer's note has to be able to say who wrote it and when."""

    __tablename__ = "investigation_notes"
    id: Mapped[uuid.UUID] = mapped_column(UuidCol, primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UuidCol, ForeignKey("investigations.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID] = mapped_column(UuidCol, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(String)   # one optional photo
    sha256: Mapped[str | None] = mapped_column(String(64))
    # Python-side default, not server_default: SQLite's CURRENT_TIMESTAMP resolves to a
    # whole second, and two notes typed in the same second would then sort arbitrarily.
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=lambda: datetime.now(UTC), server_default=func.now())
    __table_args__ = (Index("idx_inv_note", investigation_id, created_at.desc()),)
