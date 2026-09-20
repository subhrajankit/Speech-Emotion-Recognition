"""
Global Pytest Configuration and Isolation Fixtures for SenseAI (Phase 13).

Ensures all tests across unit, integration, api, and e2e suites run
consistently without cross-test mock contamination, rate-limit pollution,
or lingering singleton state.
"""

import math
import os
import struct
import sys
from pathlib import Path

# Enforce 1 OpenBLAS thread to prevent memory allocation failures on Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"

# Ensure repo root is at the head of sys.path, and tests dir does not shadow root packages
_repo_root = str(Path(__file__).parent.parent.resolve())
_tests_dir = str(Path(__file__).parent.resolve())
while _tests_dir in sys.path:
    sys.path.remove(_tests_dir)
while _repo_root in sys.path:
    sys.path.remove(_repo_root)
sys.path.insert(0, _repo_root)

import pytest
from typing import Generator

from src.backend.config import settings
from src.backend.models.manager import model_manager
from src.backend.telemetry import benchmark_collector
from src.backend.security.rate_limiter import rate_limiter
from src.backend.security.auth import create_access_token


@pytest.fixture(autouse=True)
def isolate_test_environment() -> Generator[None, None, None]:
    """
    Autouse fixture that runs around every test function.
    Resets global configuration flags, in-memory buffers, and rate limiters.
    """
    # 1. Snapshot original settings
    orig_mock = settings.MOCK_MODELS
    orig_auth = settings.REQUIRE_AUTH
    orig_rate = settings.RATE_LIMIT_UTTERANCES_PER_MINUTE
    orig_provider = settings.LLM_PROVIDER
    orig_gemini_key = settings.GEMINI_API_KEY

    # 2. Enforce test defaults
    settings.MOCK_MODELS = True
    settings.REQUIRE_AUTH = False
    settings.LLM_PROVIDER = "local"

    # 3. Clear in-memory buffers
    benchmark_collector.clear()
    rate_limiter._utterance_history.clear()
    from src.backend.llm.router import llm_router
    llm_router.reset()

    # 4. Ensure model manager is loaded in mock mode and circuit breaker is reset
    if not model_manager.initialized:
        model_manager.initialize()
    if model_manager.llm:
        model_manager.llm.mock = True
        if hasattr(model_manager.llm, "circuit_breaker"):
            model_manager.llm.circuit_breaker.reset()
    if model_manager.tts:
        model_manager.tts.mock = True
    if model_manager.asr:
        model_manager.asr.mock = True

    yield

    # 5. Teardown: restore snapshots and clear session records
    settings.MOCK_MODELS = orig_mock
    settings.REQUIRE_AUTH = orig_auth
    settings.RATE_LIMIT_UTTERANCES_PER_MINUTE = orig_rate
    settings.LLM_PROVIDER = orig_provider
    settings.GEMINI_API_KEY = orig_gemini_key
    benchmark_collector.clear()
    rate_limiter._utterance_history.clear()
    llm_router.reset()
    if model_manager.initialized and model_manager.llm:
        model_manager.llm.mock = True
        if hasattr(model_manager.llm, "circuit_breaker"):
            model_manager.llm.circuit_breaker.reset()


@pytest.fixture
def auth_token() -> str:
    """Provides a fresh, valid HS256 JWT access token for test requests."""
    return create_access_token(session_id="test_fixture_session", client_id="pytest")


@pytest.fixture
def synthetic_speech_audio() -> bytes:
    """
    Generates 1.0 second (32,000 bytes) of synthetic 16kHz mono PCM16 audio
    containing a 440Hz tone simulating an active speech utterance.
    """
    sample_rate = 16000
    duration_sec = 1.0
    num_samples = int(sample_rate * duration_sec)
    frequency = 440.0
    amplitude = 16000  # PCM16 range: -32768 to 32767

    raw_bytes = bytearray()
    for i in range(num_samples):
        val = int(amplitude * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
        raw_bytes.extend(struct.pack("<h", val))

    return bytes(raw_bytes)
