"""
SenseAI Security Subsystem (Phase 11).
"""

from src.backend.security.auth import (
    AuthenticationError,
    create_access_token,
    verify_access_token,
)
from src.backend.security.rate_limiter import (
    AudioDurationLimitExceeded,
    RateLimitError,
    SessionRateLimiter,
    UploadSizeLimitExceeded,
    UtteranceRateLimitExceeded,
    rate_limiter,
)

__all__ = [
    "AuthenticationError",
    "create_access_token",
    "verify_access_token",
    "RateLimitError",
    "UtteranceRateLimitExceeded",
    "AudioDurationLimitExceeded",
    "UploadSizeLimitExceeded",
    "SessionRateLimiter",
    "rate_limiter",
]
