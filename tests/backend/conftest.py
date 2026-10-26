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


from tests.test_doubles import FakeSenseVoiceEngine, FakeIndicConformerEngine
from backend.app.services.speech_service import speech_service


@pytest.fixture
def app():
    """Provides a fresh FastAPI application instance with explicit test doubles injected."""
    settings.AUTH_REQUIRED = False
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

    application = create_app()
    return application


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
