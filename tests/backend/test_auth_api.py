"""
Authentication, Password Hashing, and JWT Tests for VoiceSense AI.
"""

import time
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
    AuthenticationError,
)
from backend.app.core.rate_limiter import auth_rate_limiter


def test_scrypt_password_hashing():
    """Verifies stdlib scrypt password hashing and verification."""
    password = "MySecurePassword#2026"
    hashed = hash_password(password)

    assert hashed.startswith("$scrypt$ln=14,r=8,p=1$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(password, "invalid_hash") is False


def test_jwt_tamper_and_expiration():
    """Verifies HS256 JWT rejection on tampering and expiration."""
    secret = "test-secret-at-least-32-chars-long-12345"

    # 1. Normal token
    token = create_access_token(user_id="user_123", username="alice", secret_key=secret, expires_in_minutes=10)
    claims = verify_access_token(token, secret_key=secret)
    assert claims["sub"] == "user_123"
    assert claims["username"] == "alice"

    # 2. Tampered signature
    parts = token.split(".")
    tampered_sig = parts[2][:-4] + "AAAA"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
    with pytest.raises(AuthenticationError, match="signature verification failed"):
        verify_access_token(tampered_token, secret_key=secret)

    # 3. Expired token (expires_in_minutes = -1)
    expired_token = create_access_token(user_id="user_123", secret_key=secret, expires_in_minutes=-1)
    with pytest.raises(AuthenticationError, match="expired"):
        verify_access_token(expired_token, secret_key=secret, leeway_seconds=0)

    # 4. Malformed tokens
    with pytest.raises(AuthenticationError):
        verify_access_token("not-a-token")
    with pytest.raises(AuthenticationError):
        verify_access_token("")


def test_auth_registration_and_login_flow(client: TestClient):
    """Verifies /api/auth/register, /api/auth/login, and /api/auth/me endpoints."""
    auth_rate_limiter.reset()
    username = f"testuser_{int(time.time() * 1000)}"
    password = "CorrectHorseBatteryStaple99"

    # 1. Register
    reg_resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert reg_resp.status_code == 201, reg_resp.text
    user_data = reg_resp.json()
    assert user_data["username"] == username
    assert "id" in user_data

    # 2. Duplicate registration -> 409
    dup_resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert dup_resp.status_code == 409

    # 3. Login with wrong password -> 401
    bad_login = client.post("/api/auth/login", json={"username": username, "password": "WrongPassword"})
    assert bad_login.status_code == 401

    # 4. Login with correct password -> 200
    good_login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert good_login.status_code == 200
    token_data = good_login.json()
    assert "access_token" in token_data
    assert token_data["username"] == username
    token = token_data["access_token"]

    # 5. Access /api/auth/me with valid Bearer token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == username
    assert me_resp.json()["id"] == user_data["id"]

    # 6. Access /api/auth/me without token -> 401
    unauth_resp = client.get("/api/auth/me")
    assert unauth_resp.status_code == 401

    # 7. Access /api/auth/me with invalid token -> 401
    invalid_resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert invalid_resp.status_code == 401
