"""Reports, rulepacks, amendment ledger, audit (Part 13.5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
                        Index, Integer, String, UniqueConstraint, Uuid, func, text)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, JSONB

RULEPACK_STATES = ("CANDIDATE", "ACTIVE", "ARCHIVED")
LEDGER_STATUSES = ("QUARANTINED", "APPROVED", "REJECTED")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scans.id"))
    version: Mapped[int] = mapped_column(Integer)
    overall_status: Mapped[str] = mapped_column(String(24))
    pdf_storage_key: Mapped[str | None] = mapped_column(String)
    docx_storage_key: Mapped[str | None] = mapped_column(String)
    content_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSONB)             # Part 11.2
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(String)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint(scan_id, version, name="uq_report_version"),)


class Rulepack(Base):
    __tablename__ = "rulepacks"
    version: Mapped[str] = mapped_column(String(60), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(12), default="CANDIDATE")
    newest_instrument: Mapped[str | None] = mapped_column(String(40))
    chain_links: Mapped[int | None] = mapped_column(Integer)
    chain_complete: Mapped[bool | None] = mapped_column(Boolean)
    disclosures: Mapped[dict | None] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approval_confirmations: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("state IN " + _in(RULEPACK_STATES), name="ck_rulepack_state"),
        Index("one_active_rulepack", state, unique=True,
              postgresql_where=text("state = 'ACTIVE'")),
    )


class AmendmentLedger(Base):
    __tablename__ = "amendment_ledger"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    instrument_key: Mapped[str] = mapped_column(String(40))   # "G.S.R. 875(E)@2016" (P2)
    family: Mapped[str | None] = mapped_column(String(40))
    prev_key: Mapped[str | None] = mapped_column(String(40))
    op: Mapped[str | None] = mapped_column(String(20))
    node: Mapped[str | None] = mapped_column(String(80))
    quote: Mapped[str | None] = mapped_column(String)
    source_file: Mapped[str | None] = mapped_column(String)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    page: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="QUARANTINED")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(String)
    __table_args__ = (
        CheckConstraint("status IN " + _in(LEDGER_STATUSES), name="ck_ledger_status"),
        Index("idx_ledger_node", node),
        Index("idx_ledger_status", status, postgresql_where=text("status = 'QUARANTINED'")),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    diff: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("idx_audit_entity", entity_type, entity_id),
        Index("idx_audit_time", occurred_at.desc()),
    )
