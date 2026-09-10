"""Alembic environment: the target schema is the ORM metadata, never a copy of it."""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from lmpc.server.db.models import Base

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("LMPC_DB_URL", "")
    if not url:
        raise RuntimeError("LMPC_DB_URL must be set for alembic")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()