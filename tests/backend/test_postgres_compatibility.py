"""
PostgreSQL Dialect Compatibility Test for VoiceSense AI.
Skips cleanly unless DATABASE_URL_TEST is provided in the environment.
"""

import os
import pytest
from sqlalchemy import create_engine, text

from backend.app.core.database import Base
import backend.app.models  # Register all models


@pytest.mark.postgres
def test_postgres_schema_creation_and_migration():
    """
    Verifies that declarative models and DDL execute cleanly on PostgreSQL.
    Skips if DATABASE_URL_TEST is not provided.
    """
    db_url = os.environ.get("DATABASE_URL_TEST")
    if not db_url:
        pytest.skip("PostgreSQL test skipped: DATABASE_URL_TEST environment variable not set.")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # Test table creation
        Base.metadata.create_all(bind=engine)

        with engine.connect() as conn:
            res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
            tables = [r[0] for r in res.fetchall()]
            assert "users" in tables
            assert "sessions" in tables
            assert "predictions" in tables
            assert "transcripts" in tables
            assert "emotion_results" in tables
            assert "messages" in tables
            assert "model_versions" in tables

    finally:
        engine.dispose()
