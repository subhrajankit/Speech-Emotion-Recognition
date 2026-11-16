"""
Pytest configuration and fixtures for backend tests.
"""

import io
from pathlib import Path
import pytest
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import create_app


from tests.test_doubles import (
    FakeSenseVoiceEngine,
    FakeIndicConformerEngine,
    FakeEmbeddings,
    FakeStreamingSileroVAD,
)
from backend.app.services.speech_service import speech_service
from backend.app.services.rag_service import rag_service


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_db():
    """
    Creates the schema once per session on the isolated test database.
    tests/conftest.py sets DATABASE_URL to a temp SQLite file before any
    backend.app import, so engine/SessionLocal (and therefore get_db,
    get_db_session, and history_service persistence) all bind to it.
    """
    import backend.app.models  # noqa: F401 - register all tables on Base
    from backend.app.core.database import Base, engine

    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


@pytest.fixture
def app(monkeypatch):
    """Provides a fresh FastAPI application instance with explicit test doubles injected."""
    original_auth_required = settings.AUTH_REQUIRED
    settings.AUTH_REQUIRED = False
    # Synthetic test tones score ~0.0 on real Silero VAD; without a
    # speech-positive double, stop-flush tests could only pass via the removed
    # idle pre-buffer path. Default: every frame is speech so stop-flush
    # exercises the genuine in-speech segment.
    monkeypatch.setattr(
        "backend.app.websocket.speech_socket.SileroVAD",
        FakeStreamingSileroVAD,
    )
    from ai.routing.language_router import LanguageRouter
    fake_sv = FakeSenseVoiceEngine()
    fake_ic = FakeIndicConformerEngine()
    speech_service._sensevoice = fake_sv
    speech_service._indicconformer = fake_ic
    speech_service._engine = fake_sv
    speech_service._router = LanguageRouter(
        default_engine="sensevoice",
        default_language="en",
        lid_confidence_threshold=settings.LID_CONFIDENCE_THRESHOLD,
    )
    speech_service._init_error = None
    speech_service._indic_init_error = None
    speech_service._is_initialized = True

    if not rag_service.is_initialized or rag_service.embedder is None:
        rag_service.embedder = FakeEmbeddings()
        rag_service.is_initialized = True
        rag_service._init_error = None

    application = create_app()
    yield application
    settings.AUTH_REQUIRED = original_auth_required


@pytest.fixture
def client(app):
    """Provides a TestClient context."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_wav_bytes() -> bytes:
    """Returns valid WAV speech audio bytes from sample_chinese_speech.wav."""
    sample_path = Path("tests/samples/sample_chinese_speech.wav")
    if sample_path.is_file():
        return sample_path.read_bytes()

    # Fallback to 1.0s synthetic audio
    t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
    samples = 0.5 * np.sin(2 * np.pi * 440 * t)
    buf = io.BytesIO()
    sf.write(buf, samples, 16000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@pytest.fixture
def empty_audio_bytes() -> bytes:
    """Returns 0-byte audio."""
    return b""


@pytest.fixture
def oversized_audio_bytes() -> bytes:
    """Returns bytes exceeding MAX_UPLOAD_SIZE_BYTES."""
    return b"0" * (settings.MAX_UPLOAD_SIZE_BYTES + 1024)
