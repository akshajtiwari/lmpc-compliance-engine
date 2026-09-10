"""Declarative base and the Postgres types every Part 13 table shares."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import UserDefinedType
from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401  (re-exported)
from sqlalchemy.dialects.postgresql import ARRAY  # noqa: F401


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
