"""
CRUD, Alembic, and Schema Integrity Tests for VoiceSense AI.
"""

import os
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.user import User
from backend.app.models.session import Session as DBSession
from backend.app.models.model_version import ModelVersion
from backend.app.models.prediction import Prediction
from backend.app.models.transcript import Transcript
from backend.app.models.emotion import EmotionResult
from backend.app.models.message import Message
from backend.app.core.security import hash_password
from backend.app.services.history_service import history_service


@pytest.fixture
def sqlite_test_db(tmp_path):
    """Provides a fresh SQLite database and session factory."""
    db_file = tmp_path / "test_crud.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_alembic_upgrade_downgrade_cycle(tmp_path):
    """
    Acceptance Criterion:
    alembic upgrade head on a fresh SQLite file; downgrade base; upgrade head.
    """
    import subprocess
    db_file = tmp_path / "test_migration_cycle.db"
    db_url = f"sqlite:///{db_file}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    # 1. upgrade head
    cmd1 = [".venv/Scripts/python.exe", "-m", "alembic", "upgrade", "head"]
    res1 = subprocess.run(cmd1, env=env, capture_output=True, text=True)
    assert res1.returncode == 0, f"alembic upgrade head failed: {res1.stderr}"

    # 2. downgrade base
    cmd2 = [".venv/Scripts/python.exe", "-m", "alembic", "downgrade", "base"]
    res2 = subprocess.run(cmd2, env=env, capture_output=True, text=True)
    assert res2.returncode == 0, f"alembic downgrade base failed: {res2.stderr}"

    # 3. upgrade head again
    cmd3 = [".venv/Scripts/python.exe", "-m", "alembic", "upgrade", "head"]
    res3 = subprocess.run(cmd3, env=env, capture_output=True, text=True)
    assert res3.returncode == 0, f"second alembic upgrade head failed: {res3.stderr}"


def test_full_model_crud_and_cascade(sqlite_test_db):
    """Tests creating all 7 entities and verifies cascading deletes."""
    db = sqlite_test_db

    # 1. Create User
    user = User(
        id=str(uuid.uuid4()),
        username="crud_tester",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    db.commit()

    # 2. Create ModelVersion
    mv_id = history_service.get_or_create_model_version(
        db=db,
        engine_name="sensevoice",
        model_id="iic/SenseVoiceSmall",
        pinned_revision=None,
        decoder_type="funasr",
    )
    db.commit()
    assert mv_id is not None

    # 3. Create Session
    session = DBSession(
        id=f"sess_{uuid.uuid4().hex[:12]}",
        user_id=user.id,
        primary_language="en",
    )
    db.add(session)
    db.commit()

    # 4. Create Prediction
    pred = Prediction(
        id=str(uuid.uuid4()),
        session_id=session.id,
        model_version_id=mv_id,
        audio_duration_ms=2020.0,
        processing_time_ms=450.0,
        confidence=None,
    )
    db.add(pred)
    db.commit()

    # 5. Create Transcript
    transcript = Transcript(
        id=str(uuid.uuid4()),
        prediction_id=pred.id,
        session_id=session.id,
        text="Hello world",
        language="en",
        script="latin",
        mixed_language=False,
        audio_events=["Speech"],
    )
    db.add(transcript)

    # 6. Create EmotionResult
    emotion = EmotionResult(
        id=str(uuid.uuid4()),
        prediction_id=pred.id,
        session_id=session.id,
        primary_emotion="happy",
        confidence=0.95,
        valence=0.8,
        arousal=0.6,
        raw_tags=["<|HAPPY|>"],
    )
    db.add(emotion)

    # 7. Create Messages
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session.id,
        prediction_id=pred.id,
        role="user",
        text="Hello world",
    )
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session.id,
        prediction_id=pred.id,
        role="assistant",
        text="Hello! How can I assist you today?",
        sources=[{"doc_name": "policy.md", "score": 0.9}],
    )
    db.add_all([user_msg, assistant_msg])
    db.commit()

    # Verify counts
    assert db.query(User).count() == 1
    assert db.query(DBSession).count() == 1
    assert db.query(Prediction).count() == 1
    assert db.query(Transcript).count() == 1
    assert db.query(EmotionResult).count() == 1
    assert db.query(Message).count() == 2

    # Verify relationships
    queried_session = db.query(DBSession).filter(DBSession.id == session.id).first()
    assert len(queried_session.predictions) == 1
    assert len(queried_session.messages) == 2
    assert queried_session.predictions[0].transcript.text == "Hello world"
    assert queried_session.predictions[0].emotion_result.primary_emotion == "happy"

    # Test Cascade Deletion: Deleting the User must cascade and delete everything except ModelVersion
    db.delete(user)
    db.commit()

    assert db.query(User).count() == 0
    assert db.query(DBSession).count() == 0
    assert db.query(Prediction).count() == 0
    assert db.query(Transcript).count() == 0
    assert db.query(EmotionResult).count() == 0
    assert db.query(Message).count() == 0
    # ModelVersion is preserved
    assert db.query(ModelVersion).count() == 1
