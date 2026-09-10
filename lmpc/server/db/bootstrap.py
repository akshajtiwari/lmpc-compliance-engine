"""Idempotent local-development identity seed.

Production identity is supplied by OIDC. This seed only makes the local PostgreSQL server
runnable with the fixed UUIDs documented in .env.example.
"""
from __future__ import annotations

import uuid

from ..config import Settings
from . import sessionmaker_of
from .models import Jurisdiction, User


def run(settings: Settings | None = None) -> None:
    values = settings or Settings.from_env()
    if not values.db_url or not values.officer_uuid or not values.jurisdiction_uuid:
        raise RuntimeError("local bootstrap requires LMPC_DB_URL and both bootstrap UUIDs")
    jurisdiction_id = uuid.UUID(values.jurisdiction_uuid)
    officer_id = uuid.UUID(values.officer_uuid)
    with sessionmaker_of(values.db_url)() as session:
        if session.get(Jurisdiction, jurisdiction_id) is None:
            session.add(Jurisdiction(
                id=jurisdiction_id, name="Local Development", state="Local",
                path="local"))
        if session.get(User, officer_id) is None:
            session.add(User(
                id=officer_id, full_name="Local Field Officer",
                email="officer@local.invalid", role="FIELD_OFFICER",
                jurisdiction_id=jurisdiction_id))
        session.commit()


if __name__ == "__main__":
    run()
