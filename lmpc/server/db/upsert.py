"""Insert-if-absent, in whichever dialect the session is bound to.

Idempotency is a database guarantee here, not a service promise: `scans.client_uuid`
is UNIQUE and the insert is ON CONFLICT DO NOTHING, so two racing submissions — the
offline queue retrying after a timeout — cannot create a second scan (Part 12.3).
Both PostgreSQL and SQLite (>= 3.35) support the clause and RETURNING; only the
constructor differs.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert


def insert_ignore(session, table, *, values: dict, index_elements: list, returning):
    """Insert `values`, do nothing if `index_elements` already match a row.

    Returns the first RETURNING row, or None when the conflict fired — which is how
    the caller learns it lost the race and should read the winning row instead.
    """
    builder = (_sqlite_insert if session.get_bind().dialect.name == "sqlite"
               else _pg_insert)
    statement = (builder(table)
                 .values(**values)
                 .on_conflict_do_nothing(index_elements=index_elements)
                 .returning(returning))
    return session.execute(statement).first()
