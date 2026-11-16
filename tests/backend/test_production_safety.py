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
        AUTH_REQUIRED=True,
    )
    assert s.APP_ENV == "production"


STRONG_SECRET = "a-very-strong-production-secret-key-with-64-characters-randomly-generated-here"


def test_environment_only_production_still_validates_secret():
    """ENVIRONMENT=production alone must trigger validation even when APP_ENV stays default."""
    with pytest.raises(ValueError, match="refuses to start"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="voicesense-insecure-secret-key-change-in-prod",
            AUTH_REQUIRED=True,
        )


def test_environment_only_production_accepts_strong_config():
    """ENVIRONMENT=production with strong secret and auth enforced starts cleanly."""
    s = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=STRONG_SECRET,
        AUTH_REQUIRED=True,
    )
    assert s.ENVIRONMENT == "production"


def test_production_refuses_dev_compose_secret():
    """The dev docker-compose default JWT secret must be rejected in production."""
    with pytest.raises(ValueError, match="refuses to start"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="voicesense-dev-only-secret-change-in-prod-min-32-bytes",
            AUTH_REQUIRED=True,
        )


def test_production_refuses_auth_required_false():
    """APP_ENV=production must refuse to start with AUTH_REQUIRED=false."""
    with pytest.raises(ValueError, match="AUTH_REQUIRED"):
        Settings(
            APP_ENV="production",
            JWT_SECRET=STRONG_SECRET,
            AUTH_REQUIRED=False,
        )


def test_production_refuses_auth_required_false_via_environment():
    """ENVIRONMENT=production must also refuse AUTH_REQUIRED=false."""
    with pytest.raises(ValueError, match="AUTH_REQUIRED"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET=STRONG_SECRET,
            AUTH_REQUIRED=False,
        )


def test_development_allows_auth_required_false():
    """Development defaults remain unchanged: AUTH_REQUIRED=false is permitted."""
    s = Settings(APP_ENV="development", ENVIRONMENT="development", AUTH_REQUIRED=False)
    assert s.AUTH_REQUIRED is False
