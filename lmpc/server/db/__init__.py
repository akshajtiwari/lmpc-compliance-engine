"""Database layer (Part 13). Models mirror the spec tables; Alembic owns the DDL."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings

_engine = None
_sessions = None


def engine(url: str | None = None):
    """One engine per process. connect_args keeps a connection usable after idle."""
    global _engine
    if url is None:
        url = Settings.from_env().db_url
    if not url:
        raise RuntimeError("LMPC_DB_URL is not configured — persistence is mandatory")
    if _engine is None or _engine.url.render_as_string() != url:
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def sessionmaker_of(url: str | None = None) -> sessionmaker[Session]:
    global _sessions
    if _sessions is None or _sessions.kw["bind"] is not engine(url):
        _sessions = sessionmaker(bind=engine(url), expire_on_commit=False)
    return _sessions