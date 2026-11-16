"""
Regression tests: SQLite foreign-key enforcement on the canonical engine.

All tests run against the isolated temporary test database configured by
tests/conftest.py (DATABASE_URL -> temp SQLite file). They never touch
database/dev.db.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base, engine, _create_configured_engine
from backend.app.models.user import User
from backend.app.models.session import Session as DBSession
from backend.app.core.security import hash_password


def _fk_status(dbapi_conn) -> int:
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA foreign_keys")
        return cur.fetchone()[0]
    finally:
        cur.close()


def test_sqlite_connections_enforce_foreign_keys():
    """Every pooled DBAPI connection reports PRAGMA foreign_keys = 1."""
    with engine.connect() as conn1, engine.connect() as conn2:
        # Two simultaneously checked-out connections are distinct DBAPI conns
        assert _fk_status(conn1.connection.dbapi_connection) == 1
        assert _fk_status(conn2.connection.dbapi_connection) == 1


def test_new_engine_also_enforces_foreign_keys(tmp_path):
    """_create_configured_engine applies the pragma to any new SQLite engine."""
    db_file = tmp_path / "fk_check.db"
    eng = _create_configured_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        with eng.connect() as conn:
            assert _fk_status(conn.connection.dbapi_connection) == 1
    finally:
        eng.dispose()


def test_orphan_session_insert_fails():
    """Inserting a session with a nonexistent users.id raises IntegrityError."""
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(DBSession(
            id=f"sess_fk_{uuid.uuid4().hex[:8]}",
            user_id="usr_does_not_exist",
            primary_language="en",
        ))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    finally:
        db.close()


def test_user_delete_cascades_to_sessions():
    """Deleting a user applies ON DELETE CASCADE to its sessions."""
    Session = sessionmaker(bind=engine)
    db = Session()
    user_id = f"usr_fk_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_fk_{uuid.uuid4().hex[:8]}"
    try:
        db.add(User(
            id=user_id,
            username=f"fk_{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("x" * 12),
            is_active=True,
        ))
        db.add(DBSession(id=sess_id, user_id=user_id, primary_language="en"))
        db.commit()

        db.delete(db.query(User).filter(User.id == user_id).one())
        db.commit()

        remaining = db.query(DBSession).filter(DBSession.id == sess_id).count()
        assert remaining == 0
    finally:
        db.rollback()
        db.close()
