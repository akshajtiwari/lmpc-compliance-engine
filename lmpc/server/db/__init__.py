"""Database layer (Part 13). Models mirror the spec tables; Alembic owns the DDL.

Two engines are supported. PostgreSQL is the departmental deployment. SQLite is the
single-user desktop build, which has to keep a durable repository on a laptop with no
Docker — see `lmpc/desktop.py`.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings

_engine = None
_sessions = None


def _tune_sqlite(dbapi_connection, _record) -> None:
    """WAL so a reader never blocks the writer, and foreign keys ON.

    SQLite leaves foreign keys off by default. Leaving them off would let the desktop
    build accept rows PostgreSQL would reject, which is the one difference between the
    two backends that must never exist.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def engine(url: str | None = None):
    """One engine per process. connect_args keeps a connection usable after idle."""
    global _engine
    if url is None:
        url = Settings.from_env().db_url
    if not url:
        raise RuntimeError("LMPC_DB_URL is not configured — persistence is mandatory")
    if _engine is None or _engine.url.render_as_string() != url:
        if url.startswith("sqlite"):
            # FastAPI runs sync route handlers in a threadpool, so the connection is
            # not confined to the thread that opened it.
            _engine = create_engine(url, connect_args={"check_same_thread": False})
            event.listen(_engine, "connect", _tune_sqlite)
        else:
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def sessionmaker_of(url: str | None = None) -> sessionmaker[Session]:
    global _sessions
    if _sessions is None or _sessions.kw["bind"] is not engine(url):
        _sessions = sessionmaker(bind=engine(url), expire_on_commit=False)
    return _sessions
