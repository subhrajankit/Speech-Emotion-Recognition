"""
Production Safety and Secret Validation Tests for VoiceSense AI.
Verifies that APP_ENV=production strictly refuses startup with missing, default, or weak secrets.
"""

import pytest
from backend.app.core.config import Settings


def test_production_refuses_default_jwt_secret():
    """APP_ENV=production must reject default development secret."""
    with pytest.raises(ValueError, match="refuses to start"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="voicesense-insecure-secret-key-change-in-prod",
        )


def test_production_refuses_empty_jwt_secret():
    """APP_ENV=production must reject empty or missing secret."""
    with pytest.raises(ValueError, match="refuses to start"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="",
        )


def test_production_refuses_short_jwt_secret():
    """APP_ENV=production must reject secrets shorter than 32 characters."""
    with pytest.raises(ValueError, match="must be >= 32 characters"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="short-secret-under-32-chars",
        )


def test_production_accepts_strong_secret():
    """APP_ENV=production starts successfully with a strong 32+ character secret."""
    s = Settings(
        APP_ENV="production",
        JWT_SECRET="a-very-strong-production-secret-key-with-64-characters-randomly-generated-here",
    )
    assert s.APP_ENV == "production"
