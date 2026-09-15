"""Declarative base and the column types every Part 13 table shares.

PostgreSQL is the deployment database. SQLite is the single-user desktop build
(`lmpc/desktop.py`), which must keep a durable repository without Docker.

Every type below keeps its PostgreSQL form as the *default* and attaches a SQLite
variant. The direction matters: `str(column.type)` must still read "CITEXT" and "LTREE"
so the schema keeps describing itself in PostgreSQL's words, and so the Alembic
migrations — which only ever run against PostgreSQL — are unaffected.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import BigInteger, Integer, JSON, Numeric, String
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
