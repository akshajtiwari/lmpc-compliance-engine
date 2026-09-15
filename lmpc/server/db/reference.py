"""Reference data every deployment needs before it can accept a single scan.

On PostgreSQL these rows arrive with Alembic migration 0002. The desktop build creates its
schema with `create_all` and never runs a migration, so it has to seed the same rows itself
— without them a scan fails on a foreign key and the officer sees a 500 with no
explanation. `tests/test_db_models.py` pins the two lists together so they cannot drift.
"""
from __future__ import annotations

#: code -> display name. FSSAI overlap is true for food only (Rule 6 note).
COMMODITY_CATEGORIES = {
    "FOOD": "Food",
    "COSMETIC": "Cosmetic",
    "GENERIC": "Generic commodity",
    "CEMENT": "Cement",
    "FERTILIZER": "Fertilizer",
    "FARM_PRODUCE": "Farm produce",
    "TOBACCO": "Tobacco",
    "DRUG_FORMULATION": "Drug formulation",
    "MEDICAL_DEVICE": "Medical device",
    "RESTAURANT_FAST_FOOD": "Restaurant or hotel fast food",
    "HANDLOOM_THREAD_COIL": "Handloom thread in coil",
}


def seed_categories(session, model) -> int:
    """Insert any missing commodity category. Idempotent; returns how many were added."""
    existing = {code for (code,) in session.query(model.code).all()}
    missing = [model(code=code, name=name, fssai_overlap=code == "FOOD",
                     default_exemptions=[])
               for code, name in COMMODITY_CATEGORIES.items() if code not in existing]
    session.add_all(missing)
    return len(missing)
