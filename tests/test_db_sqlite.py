"""The desktop build keeps a durable repository on SQLite, with no Docker.

PostgreSQL stays the deployment database. These tests pin the two things that make a
second dialect safe rather than merely possible: the whole Part 13 schema has to build,
and a number has to mean the same thing on both engines. A px_per_mm that rounds one way
on PostgreSQL and another on SQLite would let the same evidence produce different
verdicts at a Table I threshold, which is the exact failure this project exists to avoid.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from lmpc.server.db import _tune_sqlite
from lmpc.server.db.base import Base, ScaledNumeric
from lmpc.server.db.models import (AuditLog, CommodityCategory, Jurisdiction, Scan,
                                   ScanImage, User)
from lmpc.server.db.paths import contains


@pytest.fixture()
def sqlite_sessions(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'lmpc.sqlite3'}",
                           connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _tune_sqlite)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _seed(session):
    jurisdiction = Jurisdiction(name="Local", state="Local", path="local")
    session.add(jurisdiction)
    session.flush()
    officer = User(full_name="Field Officer", email="Officer@Local.Invalid",
                   role="FIELD_OFFICER", jurisdiction_id=jurisdiction.id)
    session.add_all([officer, CommodityCategory(code="FOOD", name="Food",
                                                default_exemptions=[])])
    session.flush()
    return jurisdiction, officer


def test_the_whole_part13_schema_builds_on_sqlite(sqlite_sessions):
    assert set(Base.metadata.tables) <= set(
        sqlite_sessions.kw["bind"].dialect.get_table_names(
            sqlite_sessions.kw["bind"].connect()))


def test_a_scan_round_trips_with_its_evidence(sqlite_sessions):
    with sqlite_sessions() as session:
        jurisdiction, officer = _seed(session)
        scan = Scan(client_uuid=uuid.uuid4(), captured_at=dt.date(2026, 9, 15),
                    mode="PHYSICAL_PACKAGE", category_code="FOOD",
                    officer_id=officer.id, jurisdiction_id=jurisdiction.id,
                    panels_captured=["FRONT", "BACK"], coverage_asserted=True)
        session.add(scan)
        session.flush()
        session.add(ScanImage(scan_id=scan.id, panel_label="FRONT",
                              storage_key="images/aa/bb", sha256="a" * 64,
                              quality={"sharpness": 41.2}, upload_status="UPLOADED"))
        session.commit()

        stored = session.scalar(select(Scan))
        # The PostgreSQL ARRAY becomes a JSON list here; it must still read as a list.
        assert stored.panels_captured == ["FRONT", "BACK"]
        assert session.scalar(select(ScanImage.quality)) == {"sharpness": 41.2}


def test_email_matching_stays_case_insensitive_without_citext(sqlite_sessions):
    with sqlite_sessions() as session:
        _seed(session)
        session.commit()
        assert session.scalar(
            select(User).where(User.email == "officer@local.invalid")) is not None


def test_audit_log_autoincrements_without_bigserial(sqlite_sessions):
    with sqlite_sessions() as session:
        _, officer = _seed(session)
        session.add_all([AuditLog(entity_type="scan", actor_id=officer.id,
                                  action="SCAN_CREATE", diff={"n": n},
                                  ip="192.168.1.20") for n in (1, 2)])
        session.commit()
        assert sorted(session.scalars(select(AuditLog.id))) == [1, 2]


def test_jurisdiction_containment_matches_the_ltree_rule(sqlite_sessions):
    with sqlite_sessions() as session:
        session.add_all([Jurisdiction(name=name, state="S", path=path) for name, path in
                         (("root", "in"), ("child", "in.mh"), ("other", "xx"))])
        session.commit()
        found = session.scalars(select(Jurisdiction.name).where(
            contains("sqlite", Jurisdiction.path, "in"))).all()
        assert sorted(found) == ["child", "root"]


@pytest.mark.parametrize("raw", ["12.3456", "0.0005", "9.9995", "1.0005", "12.345"])
def test_fixed_point_numbers_round_the_way_postgresql_rounds(sqlite_sessions, raw):
    """SQLite stores REAL and rounds half-to-even; PostgreSQL rounds half-away-from-zero.

    Without ScaledNumeric quantising on the way in, 9.9995 is stored as 9.999 here and
    10.000 there — enough to flip a minimum-height verdict sitting on the threshold.
    """
    with sqlite_sessions() as session:
        jurisdiction, officer = _seed(session)
        session.add(Scan(client_uuid=uuid.uuid4(), captured_at=dt.date(2026, 9, 15),
                         mode="PHYSICAL_PACKAGE", category_code="FOOD",
                         officer_id=officer.id, jurisdiction_id=jurisdiction.id,
                         px_per_mm=Decimal(raw)))
        session.commit()
        postgres_would_store = Decimal(raw).quantize(Decimal("0.001"),
                                                     rounding=ROUND_HALF_UP)
        assert session.scalar(select(Scan.px_per_mm)) == postgres_would_store


def test_scaled_numeric_leaves_postgresql_values_untouched():
    """The quantisation is a SQLite correction only; PostgreSQL already does it."""
    column = ScaledNumeric(8, 3)
    postgres = type("D", (), {"name": "postgresql"})()
    assert column.process_bind_param(Decimal("9.9995"), postgres) == Decimal("9.9995")
