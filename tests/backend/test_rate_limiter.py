"""
Unit and integration tests for Rate Limiting & Abuse Prevention.
"""

import pytest
from fastapi import HTTPException
from backend.app.core.rate_limiter import (
    SessionRateLimiter,
    IPRateLimiter,
    UtteranceRateLimitExceeded,
    AudioDurationLimitExceeded,
    UploadSizeLimitExceeded,
)


def test_session_rate_limiter_utterance_threshold():
    """Verifies that exceeding utterances per minute raises UtteranceRateLimitExceeded."""
    limiter = SessionRateLimiter(max_utterances_per_minute=3)
    session_id = "test_sess_limit"

    limiter.record_utterance(session_id)
    limiter.record_utterance(session_id)
    limiter.record_utterance(session_id)

    # 4th utterance within 60s must raise
    with pytest.raises(UtteranceRateLimitExceeded):
        limiter.record_utterance(session_id)

    # A different session must not be affected
    limiter.record_utterance("other_session")


def test_session_rate_limiter_audio_duration_cap():
    """Verifies that exceeding max utterance audio duration raises AudioDurationLimitExceeded."""
    limiter = SessionRateLimiter(max_utterance_duration_sec=5.0)

    # 5.0 seconds at 16kHz PCM16 (32,000 bytes/s) = 160,000 bytes
    valid_bytes = 16000 * 2 * 4  # 4.0s
    dur = limiter.validate_audio_chunk(valid_bytes, sample_rate=16000)
    assert dur == 4.0

    oversized_bytes = 16000 * 2 * 6  # 6.0s
    with pytest.raises(AudioDurationLimitExceeded):
        limiter.validate_audio_chunk(oversized_bytes, sample_rate=16000)


def test_session_rate_limiter_upload_size_limit():
    """Verifies that exceeding upload size limit raises UploadSizeLimitExceeded."""
    limiter = SessionRateLimiter(max_upload_size_bytes=1000)

    limiter.validate_upload_size(500)
    limiter.validate_upload_size(1000)

    with pytest.raises(UploadSizeLimitExceeded):
        limiter.validate_upload_size(1001)


def test_ip_rate_limiter():
    """Verifies client IP rate limiter and HTTP 429 response."""
    limiter = IPRateLimiter(limit=2, window_seconds=60.0)

    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is False

    # Check method raises HTTP 429
    class DummyRequest:
        client = type("Client", (), {"host": "127.0.0.1"})()

    with pytest.raises(HTTPException) as exc_info:
        limiter.check(DummyRequest())
    assert exc_info.value.status_code == 429
