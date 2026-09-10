"""Product domain (Part 13.2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "commodity_categories",
        sa.Column("code", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("fssai_overlap", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("default_exemptions", pg.JSONB, nullable=False, server_default=sa.text("'[]'")),
    )
    categories = sa.table(
        "commodity_categories", sa.column("code", sa.String), sa.column("name", sa.String),
        sa.column("fssai_overlap", sa.Boolean), sa.column("default_exemptions", pg.JSONB))
    names = {
        "FOOD": "Food", "COSMETIC": "Cosmetic", "GENERIC": "Generic commodity",
        "CEMENT": "Cement", "FERTILIZER": "Fertilizer", "FARM_PRODUCE": "Farm produce",
        "TOBACCO": "Tobacco", "DRUG_FORMULATION": "Drug formulation",
        "MEDICAL_DEVICE": "Medical device",
        "RESTAURANT_FAST_FOOD": "Restaurant or hotel fast food",
        "HANDLOOM_THREAD_COIL": "Handloom thread in coil",
    }
    op.bulk_insert(categories, [{"code": code, "name": name,
                                 "fssai_overlap": code == "FOOD",
                                 "default_exemptions": []}
                                for code, name in names.items()])
    op.create_table(
        "manufacturers",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("registered_address", sa.Text),
        sa.Column("external_registry_ref", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("CREATE INDEX idx_manufacturers_name_trgm ON manufacturers"
               " USING gin (name gin_trgm_ops)")
    op.create_table(
        "products",
        sa.Column("id", pg.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand_name", sa.String(255)),
        sa.Column("manufacturer_id", pg.UUID, sa.ForeignKey("manufacturers.id")),
        sa.Column("category_code", sa.String(50),
                  sa.ForeignKey("commodity_categories.code"), nullable=False),
        sa.Column("barcode", sa.String(50)),
        sa.Column("declared_net_quantity", sa.String(50)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("dedup_key", sa.String(500),
                  sa.Computed("lower(coalesce(brand_name,'') || '|' ||"
                              " coalesce(manufacturer_id::text,'') || '|' ||"
                              " coalesce(barcode,''))", persisted=True),
                  unique=True),
    )
    op.execute("CREATE INDEX idx_products_brand_trgm ON products"
               " USING gin (brand_name gin_trgm_ops)")


def downgrade() -> None:
    op.drop_index("idx_products_brand_trgm", table_name="products")
    op.drop_table("products")
    op.drop_index("idx_manufacturers_name_trgm", table_name="manufacturers")
    op.drop_table("manufacturers")
    op.drop_table("commodity_categories")
