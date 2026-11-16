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


def _register_login(client: TestClient, prefix: str) -> tuple[dict, str]:
    """Registers a user, logs in, and returns (user_data, access_token)."""
    auth_rate_limiter.reset()
    username = f"{prefix}_{int(time.time() * 1000)}"
    password = "RegressionPassword123!"
    reg = client.post("/api/auth/register", json={"username": username, "password": password})
    assert reg.status_code == 201, reg.text
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return reg.json(), login.json()["access_token"]


def test_auth_token_endpoint_removed(client: TestClient):
    """
    VS-CRIT-001 regression: POST /api/auth/token must not exist.
    Anonymous callers must not be able to mint JWTs for arbitrary
    user_id / username / session_id / expires_in_minutes.
    """
    auth_rate_limiter.reset()
    payloads = [
        {},
        {"user_id": "victim_user_id", "username": "victim"},
        {"session_id": "arbitrary_session", "client_id": "attacker"},
        {"user_id": "victim", "username": "victim", "session_id": "s", "expires_in_minutes": 10080},
        {"user_id": "victim", "username": "victim", "expires_in_minutes": -1},
    ]
    for payload in payloads:
        resp = client.post("/api/auth/token", json=payload)
        assert resp.status_code == 404, f"Unexpected success for payload {payload}: {resp.text}"
    assert client.get("/api/auth/token").status_code == 404
    assert client.post("/api/auth/token").status_code == 404


def test_forged_token_cannot_impersonate_user(client: TestClient):
    """
    VS-CRIT-001 regression: a JWT asserting another user's identity must be
    rejected — wrong signing key and unknown 'sub' both yield 401.
    """
    victim_data, _victim_token = _register_login(client, "victim")

    # 1. Token signed with an attacker-controlled secret
    forged_wrong_key = create_access_token(
        user_id=victim_data["id"],
        username=victim_data["username"],
        secret_key="attacker-controlled-secret-key-0123456789",
    )
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged_wrong_key}"})
    assert resp.status_code == 401

    # 2. Properly signed token for a user_id that does not exist in the DB
    ghost_token = create_access_token(user_id="usr_does_not_exist", username="ghost")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {ghost_token}"})
    assert resp.status_code == 401

    # 3. Valid login token still resolves to the correct user (sanity)
    _data, real_token = _register_login(client, "realuser")
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {real_token}"})
    assert me.status_code == 200
    assert me.json()["username"].startswith("realuser_")


def test_auth_verify_endpoint(client: TestClient):
    """POST /api/auth/verify validates tokens without minting new ones."""
    _data, token = _register_login(client, "verifyuser")

    ok = client.post("/api/auth/verify", json={"token": token})
    assert ok.status_code == 200
    assert ok.json()["valid"] is True
    assert ok.json()["claims"]["sub"]

    bad = client.post("/api/auth/verify", json={"token": "invalid.token.value"})
    assert bad.status_code == 200
    assert bad.json()["valid"] is False


def test_websocket_accepts_legitimate_login_token(client: TestClient):
    """
    WS /ws/speech authentication still works with a token issued by /api/auth/login.
    """
    from backend.app.core.config import settings as app_settings

    _data, token = _register_login(client, "wsuser")

    app_settings.AUTH_REQUIRED = True
    try:
        with client.websocket_connect("/ws/speech") as ws:
            ws.send_json({
                "type": "start",
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
                "auth_token": token,
            })
            assert ws.receive_json().get("type") == "ready"
            ws.send_json({"type": "ping"})
            assert ws.receive_json().get("type") == "pong"
    finally:
        app_settings.AUTH_REQUIRED = False
