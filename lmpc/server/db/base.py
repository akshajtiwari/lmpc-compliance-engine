"""Declarative base and the Postgres types every Part 13 table shares."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401  (re-exported)
from sqlalchemy.dialects.postgresql import ARRAY  # noqa: F401


class Base(DeclarativeBase):
    pass