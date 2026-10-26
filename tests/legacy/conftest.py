"""
Legacy Pytest Configuration and Isolation Fixtures for src.backend (Legacy Tree).

Preserved for tests under tests/legacy/.
Configures model_manager and isolates legacy test runs.
"""

import math
import struct
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
    Autouse fixture that runs around every legacy test function.
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
    """Provides a fresh, valid HS256 JWT access token for legacy test requests."""
    return create_access_token(session_id="test_fixture_session", client_id="pytest")
