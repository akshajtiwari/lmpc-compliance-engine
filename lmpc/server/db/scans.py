"""Scans and evidence tables (Part 13.3)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
                        Integer, Numeric, String, UniqueConstraint, Uuid, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from .base import ARRAY, Base, JSONB

STATUSES = ("RECEIVED", "OCR_IN_PROGRESS", "OCR_COMPLETE", "EXTRACTION_COMPLETE",
            "EVALUATION_COMPLETE", "UNDER_REVIEW", "FINALIZED", "SYNC_CONFLICT",
            "FAILED")
MODES = ("PHYSICAL_PACKAGE", "ECOMMERCE_LISTING")
BUYER_TYPES = ("RETAIL", "INDUSTRIAL", "INSTITUTIONAL")
SCALE_TYPES = ("ISO_ID1_CARD", "APRILTAG_36H11", "MANUAL_DIMENSIONS", "NONE")
UPLOAD_STATUSES = ("PENDING", "UPLOADING", "UPLOADED", "FAILED")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("products.id"))
    officer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), default=uuid.uuid4)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jurisdictions.id"))

    captured_at: Mapped[date] = mapped_column(Date)          # P7 — the governing law
    mode: Mapped[str] = mapped_column(String(20))
    category_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("commodity_categories.code"))
    buyer_type: Mapped[str] = mapped_column(String(20), default="RETAIL")
    package_shape: Mapped[str | None] = mapped_column(String(20))

    coverage_asserted: Mapped[bool] = mapped_column(Boolean, default=False)  # P4
    panels_captured: Mapped[list] = mapped_column(ARRAY(String(10)), default=list)
    glyph_segmentation: Mapped[bool] = mapped_column(Boolean, default=False)

    scale_reference_type: Mapped[str | None] = mapped_column(String(20))
    scale_reference_data: Mapped[dict | None] = mapped_column(JSONB)
    px_per_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    pdp_h_cm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    pdp_w_cm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    pdp_area_cm2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    capacity_cm3: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    net_quantity_g: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    net_quantity_ml: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    is_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    is_molded: Mapped[bool] = mapped_column(Boolean, default=False)
    other_law_requires_same_info: Mapped[bool] = mapped_column(Boolean, default=False)

    ecommerce_url: Mapped[str | None] = mapped_column(String)
    ecommerce_text: Mapped[str | None] = mapped_column(String)
    geo_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    geo_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    rulepack_version: Mapped[str | None] = mapped_column(String(60))
    rulepack_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED")
    overall: Mapped[str | None] = mapped_column(String(24))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("status IN " + _in(STATUSES), name="ck_scans_status"),
        CheckConstraint("mode IN " + _in(MODES), name="ck_scans_mode"),
        CheckConstraint("buyer_type IN " + _in(BUYER_TYPES), name="ck_scans_buyer"),
        Index("idx_scans_jur_date", jurisdiction_id, captured_at.desc()),
        Index("idx_scans_status", status, postgresql_where=text("status <> 'FINALIZED'")),
        Index("idx_scans_officer", officer_id, created_at.desc()),
        Index("idx_scans_product", product_id),
    )


class ScanImage(Base):
    __tablename__ = "scan_images"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("scans.id", ondelete="CASCADE"))
    panel_label: Mapped[str] = mapped_column(String(10))
    storage_key: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String(64))
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    max_edge_used: Mapped[int | None] = mapped_column(Integer)
    quality: Mapped[dict | None] = mapped_column(JSONB)
    upload_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint(scan_id, panel_label, sha256, name="uq_scan_image"),
        CheckConstraint("upload_status IN " + _in(UPLOAD_STATUSES),
                        name="ck_scan_images_upload"),
    )