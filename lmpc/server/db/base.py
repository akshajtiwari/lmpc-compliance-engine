"""Declarative base and the column types every Part 13 table shares.

PostgreSQL is the deployment database. SQLite is the single-user desktop build
(`lmpc/desktop.py`), which must keep a durable repository without Docker.

Every type below keeps its PostgreSQL form as the *default* and attaches a SQLite
variant. The direction matters: `str(column.type)` must still read "CITEXT" and "LTREE"
so the schema keeps describing itself in PostgreSQL's words, and so the Alembic
migrations — which only ever run against PostgreSQL — are unaffected.
"""
from __future__ import annotations

from datetime import UTC, date as _date, datetime
from decimal import ROUND_HALF_UP, Decimal

import uuid as _uuid

from sqlalchemy import (BigInteger, Date, DateTime, Integer, JSON, Numeric,
                        String, Uuid)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator, UserDefinedType


class Base(DeclarativeBase):
    pass


class LTREE(UserDefinedType):
    """PostgreSQL's materialised-tree path type."""

    cache_ok = True

    def get_col_spec(self, **_kw) -> str:
        return "LTREE"


class CITEXT(UserDefinedType):
    """Case-insensitive text; the migration installs the PostgreSQL extension."""

    cache_ok = True

    def get_col_spec(self, **_kw) -> str:
        return "CITEXT"


class ScaledNumeric(TypeDecorator):
    """A fixed-point number that stores and reads back identically on both engines.

    PostgreSQL rounds a NUMERIC(p, s) half-away-from-zero as it stores it. SQLite
    stores REAL and SQLAlchemy rounds half-to-even on the way back out, so a value
    landing exactly on the half — 9.9995 at scale 3 — becomes 10.000 on one engine and
    9.999 on the other. `store_records` then calls float() on it and the result reaches
    the millimetre checks in the rule engine, where a value sitting on a Table I
    threshold would be judged differently depending on which database the server
    happened to be running.

    Quantising on the way *in* is what fixes it: the stored number is already the one
    PostgreSQL would have stored, so both engines read back the same value.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int, scale: int, **kw):
        super().__init__(precision=precision, scale=scale, **kw)
        self._quantum = Decimal(1).scaleb(-scale)

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return Decimal(str(value)).quantize(self._quantum, rounding=ROUND_HALF_UP)


class UtcDateTime(TypeDecorator):
    """A timestamp that comes back timezone-aware on both engines.

    PostgreSQL's TIMESTAMPTZ returns an aware datetime. SQLite has no such type, so
    SQLAlchemy hands back a naive one, and comparing it against `datetime.now(UTC)`
    raises TypeError rather than returning a wrong answer — which is how this was found:
    device enrollment could not check its own expiry on the desktop build.

    Everything is normalised to UTC on the way in, so what is stored is unambiguous.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self, **kw):
        super().__init__(timezone=True, **kw)

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class UuidCol(TypeDecorator):
    """A UUID column that also accepts the string form of one.

    psycopg adapts a string to a UUID on its own, so on PostgreSQL every write path could
    hand this column either. SQLite's driver does not, and the API layer carries ids as
    strings — `client_uuid` arrives on a multipart form, investigation ids arrive in JSON.
    Coercing here keeps one write path working identically on both engines instead of
    requiring every caller to remember which shape this particular column wants.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return _uuid.UUID(value) if isinstance(value, str) else value


class DateCol(TypeDecorator):
    """A date column that also accepts the ISO string form.

    The same leniency gap as UuidCol: psycopg parses '2026-09-15' for us, SQLite refuses
    anything but a date object, and `captured_at` arrives as a string on a multipart form.
    That date decides which version of the law judges the scan, so it is parsed strictly —
    a malformed one must fail here, not silently become today.
    """

    impl = Date
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return _date.fromisoformat(value) if isinstance(value, str) else value


#: JSONB on PostgreSQL, portable JSON text on SQLite. One shared instance: SQLAlchemy
#: type objects are immutable and are meant to be reused across columns.
JSONB = postgresql.JSONB().with_variant(JSON(), "sqlite")

#: A client address. PostgreSQL validates it; SQLite stores the text.
INET = postgresql.INET().with_variant(String(45), "sqlite")

#: SQLite only auto-increments an INTEGER PRIMARY KEY, never a BIGINT one.
BIGSERIAL = BigInteger().with_variant(Integer(), "sqlite")

#: Case-insensitive email. NOCASE collation is SQLite's equivalent of CITEXT.
CI_TEXT = CITEXT().with_variant(String(320, collation="NOCASE"), "sqlite")

#: A jurisdiction path. On SQLite it is the same dotted string in a plain column;
#: containment becomes a prefix match — see `db/paths.py`.
TREE_PATH = LTREE().with_variant(String(500), "sqlite")


def ARRAY(item_type):
    """A list column: a real PostgreSQL array, a JSON list on SQLite.

    Safe because every array column in this schema (`scans.panels_captured`) is read
    and written whole, in Python — `set()`, `list()`, `in` — and no SQL array operator
    appears anywhere in the request path. An in-place append would not flush on the
    SQLite side; none exists today, and none should be added without a MutableList.
    """
    return postgresql.ARRAY(item_type).with_variant(JSON(), "sqlite")
