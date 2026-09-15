"""Reports, rulepacks, amendment ledger, audit (Part 13.5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, ForeignKey,
                        Index, Integer, String, UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from .base import BIGSERIAL, Base, INET, JSONB, UtcDateTime, UuidCol

RULEPACK_STATES = ("CANDIDATE", "ACTIVE", "ARCHIVED")
LEDGER_STATUSES = ("QUARANTINED", "APPROVED", "REJECTED")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


REPORT_KINDS = ("FIELD", "FINALIZED")


class ComplianceReport(Base):
    """A rendered report. Two kinds, one registry.

    FIELD is the copy a capturing officer generates for themselves — watermarked, and
    explicitly not a legal finding. FINALIZED is the reviewer-signed document. They share
    one per-owner version sequence: separate sequences would produce two different
    documents both labelled "v1", which is exactly the ambiguity a legal record cannot
    carry.
    """

    __tablename__ = "compliance_reports"
    id: Mapped[uuid.UUID] = mapped_column(UuidCol, primary_key=True, default=uuid.uuid4)
    # Nullable since an investigation-level report belongs to a folder, not one scan.
    scan_id: Mapped[uuid.UUID | None] = mapped_column(UuidCol, ForeignKey("scans.id"))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidCol, ForeignKey("investigations.id", ondelete="CASCADE"))
    report_kind: Mapped[str] = mapped_column(String(12), default="FINALIZED")
    generated_by: Mapped[uuid.UUID | None] = mapped_column(UuidCol, ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer)
    overall_status: Mapped[str] = mapped_column(String(24))
    pdf_storage_key: Mapped[str | None] = mapped_column(String)
    docx_storage_key: Mapped[str | None] = mapped_column(String)
    content_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSONB)             # Part 11.2
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UuidCol, ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(String)
    finalized_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    __table_args__ = (
        CheckConstraint("report_kind IN " + _in(REPORT_KINDS), name="ck_report_kind"),
        # Both engines treat NULLs as distinct in a unique constraint, so the scan-scoped
        # and investigation-scoped sequences coexist without a partial index.
        UniqueConstraint(scan_id, report_kind, version, name="uq_report_version"),
        UniqueConstraint(investigation_id, report_kind, version,
                         name="uq_investigation_report_version"),
    )


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
    built_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UuidCol, ForeignKey("users.id"))
    approval_confirmations: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("state IN " + _in(RULEPACK_STATES), name="ck_rulepack_state"),
        # Partial UNIQUE: exactly one ACTIVE rulepack, any number of CANDIDATE or
        # ARCHIVED ones. sqlite_where is not decoration — without it the index degrades
        # to UNIQUE(state) and a second ARCHIVED rulepack becomes unstorable.
        Index("one_active_rulepack", state, unique=True,
              postgresql_where=text("state = 'ACTIVE'"),
              sqlite_where=text("state = 'ACTIVE'")),
    )


class AmendmentLedger(Base):
    __tablename__ = "amendment_ledger"
    id: Mapped[uuid.UUID] = mapped_column(UuidCol, primary_key=True, default=uuid.uuid4)
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
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UuidCol, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    reject_reason: Mapped[str | None] = mapped_column(String)
    __table_args__ = (
        CheckConstraint("status IN " + _in(LEDGER_STATUSES), name="ck_ledger_status"),
        Index("idx_ledger_node", node),
        Index("idx_ledger_status", status,
              postgresql_where=text("status = 'QUARANTINED'"),
              sqlite_where=text("status = 'QUARANTINED'")),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BIGSERIAL, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UuidCol)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UuidCol, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    diff: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    __table_args__ = (
        Index("idx_audit_entity", entity_type, entity_id),
        Index("idx_audit_time", occurred_at.desc()),
    )
