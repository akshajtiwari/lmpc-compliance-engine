"""Portable-launcher paths and safety defaults."""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import select

from lmpc import desktop
from lmpc.server.db import desktop_bootstrap, sessionmaker_of
from lmpc.server.db.models import Jurisdiction, User


@pytest.fixture()
def portable(tmp_path):
    """_configure_environment writes a dozen LMPC_* variables, so snapshot the whole
    environment rather than the three this test sets. Leaving LMPC_AUTH_MODE=local behind
    makes every later test that builds an app fail for want of a database."""
    saved = os.environ.copy()
    os.environ.update({"LMPC_DESKTOP_DATA_DIR": str(tmp_path / "portable"),
                       "LMPC_DB_URL": "postgresql://must-not-be-used",
                       "LMPC_S3_BUCKET": "must-not-be-used"})
    try:
        yield desktop._configure_environment()
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_the_portable_build_keeps_a_local_database_and_no_s3(portable, tmp_path):
    assert portable == (tmp_path / "portable").resolve()
    assert os.environ["LMPC_DB_URL"] == f"sqlite+pysqlite:///{portable / 'lmpc.sqlite3'}"
    assert os.environ["LMPC_S3_BUCKET"] == ""
    assert os.environ["LMPC_STORAGE_ROOT"] == str(portable / "objects")
    assert os.environ["LMPC_RULEPACK_PATH"].endswith("rulepack/current.json")
    assert (portable / "lmpc.sqlite3").exists()


def test_authentication_is_on_so_the_build_can_issue_an_enrollment(portable):
    """Disabled auth is what made the shipped preview unable to pair at all:
    AccountService refuses to manage accounts without it."""
    assert os.environ["LMPC_AUTH_MODE"] == "local"
    assert os.environ["LMPC_DESKTOP_MODE"] == "true"


def test_the_signing_key_lands_beside_the_data_not_in_the_working_directory(portable):
    """The default path is relative, and a double-clicked executable inherits whatever
    directory the user happened to be in. An RSA private key must not be written there."""
    assert os.environ["LMPC_JWT_KEY_PATH"] == str(portable / "auth" / "jwt-private.pem")


def test_first_run_seeds_a_supervisor_and_a_field_officer(portable):
    record = json.loads(desktop_bootstrap.credentials_path(portable).read_text())
    assert record["admin"]["password"] != record["officer"]["password"]
    with sessionmaker_of(os.environ["LMPC_DB_URL"])() as session:
        roles = dict(session.execute(select(User.email, User.role)).all())
        assert roles == {"supervisor@lmpc.local": "ADMIN",
                         "officer@lmpc.local": "FIELD_OFFICER"}
        assert session.scalar(select(Jurisdiction.path)) == "local"


def test_credentials_are_not_world_readable(portable):
    mode = desktop_bootstrap.credentials_path(portable).stat().st_mode
    assert mode & 0o077 == 0, "desktop.json holds two plaintext passwords"


def test_a_second_run_reuses_the_same_identities(portable):
    before = json.loads(desktop_bootstrap.credentials_path(portable).read_text())
    desktop._configure_environment()
    after = json.loads(desktop_bootstrap.credentials_path(portable).read_text())
    assert before == after


def test_the_fingerprint_changes_when_a_column_is_added():
    """A constant somebody has to remember to bump is not a guard. The first version of
    this was exactly that, and the next schema change forgot to bump it — which is how a
    desktop database survived a migration it had not had and then failed mid-report on a
    missing column."""
    from sqlalchemy import Column, String, Table

    from lmpc.server.db.base import Base

    before = desktop_bootstrap.schema_fingerprint()
    probe = Table("fingerprint_probe", Base.metadata, Column("id", String, primary_key=True))
    try:
        assert desktop_bootstrap.schema_fingerprint() != before
    finally:
        Base.metadata.remove(probe)
    assert desktop_bootstrap.schema_fingerprint() == before


def test_a_database_from_another_schema_generation_is_refused(portable):
    """create_all adds missing tables but never alters an existing one, and there is no
    Alembic path for SQLite. Opening a stale database would surface later as corrupt
    evidence, so the build stops instead."""
    path = desktop_bootstrap.credentials_path(portable)
    record = json.loads(path.read_text())
    record["schema_generation"] = "0000000000000000"
    path.write_text(json.dumps(record))
    with pytest.raises(RuntimeError, match="different version"):
        desktop._configure_environment()


def test_desktop_rejects_invalid_port():
    assert desktop.main(["--port", "0", "--no-browser"]) == 2


def test_the_portable_build_can_actually_accept_a_scan(portable):
    """Commodity categories arrive with Alembic on PostgreSQL, and the desktop build runs
    no migrations. Without seeding them here every scan dies on a foreign key — a 500 with
    nothing in it for the officer to act on."""
    from sqlalchemy import func, select

    from lmpc.server.db.models import CommodityCategory
    from lmpc.server.db.reference import COMMODITY_CATEGORIES

    with sessionmaker_of(os.environ["LMPC_DB_URL"])() as session:
        seeded = session.scalar(select(func.count()).select_from(CommodityCategory))
        assert seeded == len(COMMODITY_CATEGORIES)
        assert session.get(CommodityCategory, "FOOD").fssai_overlap is True
