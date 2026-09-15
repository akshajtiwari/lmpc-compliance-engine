"""First-run setup for the portable desktop build.

The desktop build has to pair with a phone, and pairing structurally needs a relational
store: enrollments live in `device_enrollments`, sessions in `refresh_tokens`, identities
in `users`. So the portable executable seeds a real SQLite database instead of the
session-lifetime in-memory repository it used before.

This is deliberately not an extension of `db/bootstrap.py`. That seed is PostgreSQL-shaped,
demands `LMPC_BOOTSTRAP_PASSWORD`, and creates exactly one administrator. The desktop needs
two identities — an administrator to issue enrollments and a field officer for the phone to
become — and it has to invent both passwords itself, because nobody types them.
"""
from __future__ import annotations

import json
import secrets
import stat
import uuid
from pathlib import Path

from ..svc.auth_core import hash_password
from . import engine, sessionmaker_of
from .base import Base
from .models import Jurisdiction, User

#: Raised by one and bumped by the other: any change to the SQLite schema that
#: `create_all` would no longer produce from an existing file.
SCHEMA_GENERATION = 1

CREDENTIALS_FILE = "desktop.json"
_ALPHABET = "abcdefghijkmnopqrstuvwxyz23456789"   # no look-alikes; these get read aloud


def _password() -> str:
    return "-".join("".join(secrets.choice(_ALPHABET) for _ in range(4))
                    for _ in range(3))


def _write_private(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)          # 0600
    except OSError:                                       # pragma: no cover - Windows ACLs
        pass


def credentials_path(data_root: Path) -> Path:
    return data_root / CREDENTIALS_FILE


def run(data_root: Path, db_url: str) -> dict:
    """Create the database if absent, seed two identities, return the credentials.

    Idempotent: a second run reads the existing file back and changes nothing.
    """
    if not db_url.startswith("sqlite"):
        raise RuntimeError("the desktop bootstrap only manages the local SQLite database")

    path = credentials_path(data_root)
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        _guard_schema(stored)
        Base.metadata.create_all(engine(db_url))   # no-op when the tables are there
        return stored

    Base.metadata.create_all(engine(db_url))
    jurisdiction_id, admin_id, officer_id = (uuid.uuid4() for _ in range(3))
    record = {
        "schema_generation": SCHEMA_GENERATION,
        "jurisdiction_id": str(jurisdiction_id),
        "admin": {"id": str(admin_id), "email": "supervisor@lmpc.local",
                  "password": _password()},
        "officer": {"id": str(officer_id), "email": "officer@lmpc.local",
                    "password": _password()},
    }
    with sessionmaker_of(db_url)() as session:
        session.add(Jurisdiction(id=jurisdiction_id, name="This computer",
                                 state="Local", path="local"))
        session.add_all([
            User(id=admin_id, full_name="Supervisor", email=record["admin"]["email"],
                 role="ADMIN", jurisdiction_id=jurisdiction_id, is_legal_reviewer=True,
                 password_hash=hash_password(record["admin"]["password"])),
            User(id=officer_id, full_name="Field Officer",
                 email=record["officer"]["email"], role="FIELD_OFFICER",
                 jurisdiction_id=jurisdiction_id,
                 password_hash=hash_password(record["officer"]["password"])),
        ])
        session.commit()
    _write_private(path, record)
    return record


def _guard_schema(stored: dict) -> None:
    """Refuse to open a database this build no longer knows how to read.

    There is no Alembic path for SQLite — migrations 0001-0007 are PostgreSQL DDL, down to
    `CREATE EXTENSION`. `create_all` adds missing tables but never alters an existing one,
    so a changed column would be silently ignored and the mismatch would surface later as
    corrupt evidence. Stopping here is the honest failure.
    """
    found = stored.get("schema_generation")
    if found != SCHEMA_GENERATION:
        raise RuntimeError(
            f"this database was created by a different version of LMPC Compliance "
            f"(schema {found}, this build expects {SCHEMA_GENERATION}). Move "
            f"lmpc.sqlite3 and {CREDENTIALS_FILE} aside to start a new one; the old "
            f"evidence stays readable by the build that wrote it.")


def environment(data_root: Path, record: dict, db_url: str) -> dict[str, str]:
    """The LMPC_* variables the portable launcher exports for this database."""
    return {
        "LMPC_DB_URL": db_url,
        "LMPC_AUTH_MODE": "local",
        "LMPC_DESKTOP_MODE": "true",
        "LMPC_OFFICER_UUID": record["officer"]["id"],
        "LMPC_JURISDICTION_UUID": record["jurisdiction_id"],
        # Default is relative to the working directory, which for a double-clicked
        # executable is wherever the user happened to be. An RSA private key must not
        # land there.
        "LMPC_JWT_KEY_PATH": str(data_root / "auth" / "jwt-private.pem"),
    }
