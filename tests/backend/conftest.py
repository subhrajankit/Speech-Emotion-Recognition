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


@pytest.fixture
def app():
    """Provides a fresh FastAPI application instance for tests."""
    settings.MOCK_MODELS = True
    settings.AUTH_REQUIRED = False
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
