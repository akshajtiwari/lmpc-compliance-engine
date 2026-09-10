"""Idempotent local-development identity seed.

Production identity is supplied by OIDC. This seed only makes the local PostgreSQL server
runnable with the fixed UUIDs documented in .env.example.
"""
from __future__ import annotations

import uuid

from ..config import Settings
from ..svc.auth_core import hash_password, password_matches
from . import sessionmaker_of
from .models import Jurisdiction, User


def run(settings: Settings | None = None) -> None:
    values = settings or Settings.from_env()
    if not values.db_url or not values.officer_uuid or not values.jurisdiction_uuid:
        raise RuntimeError("local bootstrap requires LMPC_DB_URL and both bootstrap UUIDs")
    jurisdiction_id = uuid.UUID(values.jurisdiction_uuid)
    officer_id = uuid.UUID(values.officer_uuid)
    if values.auth_mode == "local" and not values.bootstrap_password:
        raise RuntimeError("LMPC_AUTH_MODE=local requires LMPC_BOOTSTRAP_PASSWORD")
    if values.bootstrap_role not in {"FIELD_OFFICER", "REVIEWING_OFFICER", "ADMIN", "AUDITOR"}:
        raise RuntimeError("LMPC_BOOTSTRAP_ROLE is not a supported role")
    with sessionmaker_of(values.db_url)() as session:
        if session.get(Jurisdiction, jurisdiction_id) is None:
            session.add(Jurisdiction(
                id=jurisdiction_id, name="Local Development", state="Local",
                path="local"))
        user = session.get(User, officer_id)
        if user is None:
            user = User(
                id=officer_id, full_name="Local Administrator",
                email=values.bootstrap_email, role=values.bootstrap_role,
                jurisdiction_id=jurisdiction_id)
            session.add(user)
        if values.auth_mode == "local":
            user.full_name = "Local Administrator"
            user.email = values.bootstrap_email
            user.role = values.bootstrap_role
            user.jurisdiction_id = jurisdiction_id
            if not password_matches(user.password_hash, values.bootstrap_password):
                user.password_hash = hash_password(values.bootstrap_password)
        session.commit()


if __name__ == "__main__":
    run()
