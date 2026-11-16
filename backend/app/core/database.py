"""
Database engine and session management for VoiceSense AI.
Supports SQLite (development) and PostgreSQL (production) via SQLAlchemy 2.x.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import StaticPool

from backend.app.core.config import settings

logger = logging.getLogger("voicesense.database")


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.x declarative models."""
    pass


def _create_configured_engine(database_url: str):
    if not database_url:
        return None

    connect_args = {}
    engine_kwargs = {"echo": False}

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # If SQLite file path has directories, ensure they exist
        if ":///" in database_url:
            path = database_url.split(":///", 1)[1]
            if path and path != ":memory:":
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

        # In-memory SQLite needs StaticPool to preserve tables across connections
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        **engine_kwargs
    )

    if database_url.startswith("sqlite"):
        # SQLite ignores foreign keys unless enabled per-connection. The pragma
        # is connection-scoped, so it must run on every new DBAPI connection —
        # including each pooled connection — not once per engine.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


# Application-level engine and sessionmaker
engine = _create_configured_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
) if engine is not None else None


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a synchronous SQLAlchemy session.
    Closes the session after the request finishes.
    """
    if SessionLocal is None:
        raise RuntimeError("Database engine is not configured (DATABASE_URL is empty).")
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for background threadpool tasks.
    Example:
        with get_db_session() as db:
            db.add(...)
            db.commit()
    """
    if SessionLocal is None:
        raise RuntimeError("Database engine is not configured (DATABASE_URL is empty).")
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> str:
    """
    Performs a lightweight connectivity check.
    Returns:
        "ok" - Connection succeeded and returned expected result.
        "unavailable" - Connection failed or raised an exception.
        "not_configured" - DATABASE_URL is unset.
    """
    if not settings.DATABASE_URL or engine is None:
        return "not_configured"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return "unavailable"
