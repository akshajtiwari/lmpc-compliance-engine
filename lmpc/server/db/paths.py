"""Jurisdiction containment, in whichever dialect the session is bound to.

A jurisdiction tree is stored as a dotted path. PostgreSQL has LTREE and the `<@`
containment operator; SQLite has neither, so containment there is the equivalent
prefix match. Keeping both in one place means the scoping rule is written once —
an access-control predicate that disagrees between two backends is a security bug,
not a portability detail.
"""
from __future__ import annotations

import uuid

from sqlalchemy import exists, or_, select

from .models import Jurisdiction


def contains(dialect_name: str, path_column, root_path):
    """True where `path_column` is `root_path` or a descendant of it.

    `root_path` may be a plain string or a SQL expression (a scalar subquery that
    looks the path up by id). `||` is the concatenation operator in both engines.
    """
    if dialect_name == "postgresql":
        return path_column.op("<@")(root_path)
    prefix = (root_path.op("||")(".%") if hasattr(root_path, "op")
              else root_path + ".%")
    return or_(path_column == root_path, path_column.like(prefix))


def jurisdiction_contains(session, root: str | None, target: str | None) -> bool:
    """True when jurisdiction `target` is `root` or sits beneath it in the tree."""
    if not root or not target:
        return False
    root_path = select(Jurisdiction.path).where(
        Jurisdiction.id == uuid.UUID(root)).scalar_subquery()
    return bool(session.scalar(select(exists().where(
        Jurisdiction.id == uuid.UUID(target),
        contains(session.get_bind().dialect.name, Jurisdiction.path, root_path)))))
