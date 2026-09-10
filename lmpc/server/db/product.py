"""Product domain tables (Part 13.2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Computed, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, JSONB


class CommodityCategory(Base):
    __tablename__ = "commodity_categories"
    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    fssai_overlap: Mapped[bool] = mapped_column(Boolean, default=False)
    default_exemptions: Mapped[dict] = mapped_column(JSONB, default=list)


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    registered_address: Mapped[str | None] = mapped_column(String)
    external_registry_ref: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """dedup_key is a stored generated column — the database, not application code,
    decides that two products are the same (13.2)."""
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    brand_name: Mapped[str | None] = mapped_column(String(255))
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("manufacturers.id"))
    category_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("commodity_categories.code"))
    barcode: Mapped[str | None] = mapped_column(String(50))
    declared_net_quantity: Mapped[str | None] = mapped_column(String(50))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dedup_key: Mapped[str | None] = mapped_column(
        String(500), Computed(
            "lower(coalesce(brand_name, '') || '|' || coalesce(manufacturer_id::text, '')"
            " || '|' || coalesce(barcode, ''))", persisted=True), unique=True)