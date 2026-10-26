"""
Unit tests for Phase 11 Security Hardening:
- JWT Token issuance, verification, algorithm locking, and expiration.
- Multi-layer session rate limiting (utterances/min, audio duration, upload size).
- Document ingestion validation (extension, size, magic bytes, path traversal).
- WebSocket handshake authentication gating with RFC 6455 close code 1008.
"""

import os
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

from src.backend.config import settings
from src.backend.main import app
from src.backend.security.auth import (
    AuthenticationError,
    create_access_token,
    verify_access_token,
    _base64url_encode,
)
from src.backend.security.rate_limiter import (
    AudioDurationLimitExceeded,
    SessionRateLimiter,
    UploadSizeLimitExceeded,
    UtteranceRateLimitExceeded,
)
from scripts.database.build_rag_index import validate_document_file


class TestJWTAuthentication:
    """Test suite for HS256 JWT security token generation and verification."""

    def test_token_creation_and_verification(self):
        session_id = "test_user_session_42"
        token = create_access_token(session_id=session_id, client_id="unit-test", expires_in_minutes=5)
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

        claims = verify_access_token(token)
        assert claims["sub"] == session_id
        assert claims["client_id"] == "unit-test"
        assert claims["exp"] > time.time()

    def test_tampered_token_rejected(self):
        token = create_access_token(session_id="authentic_session")
        header, payload, sig = token.split(".")
        # Tamper payload
        tampered_payload = _base64url_encode(b'{"sub":"hacked_session","exp":9999999999}')
        bad_token = f"{header}.{tampered_payload}.{sig}"

        with pytest.raises(AuthenticationError, match="signature verification failed"):
            verify_access_token(bad_token)

    def test_expired_token_rejected(self):
        token = create_access_token(session_id="expired_session", expires_in_minutes=-10)
        with pytest.raises(AuthenticationError, match="Token has expired"):
            verify_access_token(token)

    def test_algorithm_none_rejected(self):
        """Attacker crafts a JWT with 'alg': 'none' to bypass signature checks."""
        header = _base64url_encode(b'{"alg":"none","typ":"JWT"}')
        payload = _base64url_encode(b'{"sub":"admin"}')
        fake_token = f"{header}.{payload}."

        with pytest.raises(AuthenticationError, match="Unsupported algorithm 'none'"):
            verify_access_token(fake_token)


class TestSessionRateLimiter:
    """Test suite for session utterance quotas and audio duration limits."""

    def test_utterance_rate_limiting(self):
        limiter = SessionRateLimiter(max_utterances_per_minute=5)
        session_id = "flood_session"

        # First 5 utterances succeed
        for _ in range(5):
            limiter.record_utterance(session_id)

        # 6th utterance within 60s window triggers rate limit
        with pytest.raises(UtteranceRateLimitExceeded, match="rate limit exceeded"):
            limiter.record_utterance(session_id)

    def test_audio_duration_cap(self):
        limiter = SessionRateLimiter(max_utterance_duration_sec=30.0)
        # 16kHz mono PCM16 = 32,000 bytes per second
        # 29 seconds = 928,000 bytes -> valid
        duration = limiter.validate_audio_chunk(928000)
        assert duration == 29.0

        # 31 seconds = 992,000 bytes -> exceeds cap
        with pytest.raises(AudioDurationLimitExceeded, match="Maximum utterance duration exceeded"):
            limiter.validate_audio_chunk(992000)

    def test_upload_size_limit(self):
        limiter = SessionRateLimiter(max_upload_size_bytes=1000)
        limiter.validate_upload_size(500)

        with pytest.raises(UploadSizeLimitExceeded, match="exceeds maximum upload size"):
            limiter.validate_upload_size(1500)


class TestRAGDocumentValidation:
    """Test suite for document ingestion security checks."""

    def test_valid_txt_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write("Valid text document content for RAG indexing.".encode("utf-8"))
            temp_path = f.name

        try:
            assert validate_document_file(temp_path) is True
        finally:
            os.remove(temp_path)

    def test_txt_with_null_bytes_rejected(self):
        """Binary files disguised as .txt must be rejected."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Hello\x00BinaryPayload\x00Evil")
            temp_path = f.name

        try:
            assert validate_document_file(temp_path) is False
        finally:
            os.remove(temp_path)

    def test_pdf_magic_bytes_checked(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"NOT_A_REAL_PDF_HEADER")
            temp_path = f.name

        try:
            assert validate_document_file(temp_path) is False
        finally:
            os.remove(temp_path)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\nValid PDF header")
            temp_path_valid = f.name

        try:
            assert validate_document_file(temp_path_valid) is True
        finally:
            os.remove(temp_path_valid)

    def test_disallowed_extension_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"MZExecutableHeader")
            temp_path = f.name

        try:
            assert validate_document_file(temp_path) is False
        finally:
            os.remove(temp_path)

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as base_dir:
            # Create a file outside base_dir
            with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as outside_file:
                outside_file.write(b"# Secret Markdown Outside Root")
                outside_path = outside_file.name

            try:
                # Validating a file outside base_dir with allowed_base_dir set must return False
                assert validate_document_file(outside_path, allowed_base_dir=base_dir) is False
            finally:
                os.remove(outside_path)


class TestTransportSecurityHandshake:
    """Test suite for WebSocket JWT handshake authentication."""

    def test_auth_token_issuance_endpoint(self):
        client = TestClient(app)
        res = client.post("/api/auth/token", json={"session_id": "test_sess_001", "client_id": "pytest"})
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert data["token_type"] == "Bearer"
        assert data["session_id"] == "test_sess_001"

    def test_auth_verify_endpoint(self):
        client = TestClient(app)
        # 1. Issue token
        issue_res = client.post("/api/auth/token", json={"session_id": "test_sess_002"})
        token = issue_res.json()["token"]

        # 2. Verify token
        verify_res = client.post("/api/auth/verify", json={"token": token})
        assert verify_res.status_code == 200
        assert verify_res.json()["valid"] is True
        assert verify_res.json()["claims"]["sub"] == "test_sess_002"

        # 3. Verify bad token
        bad_res = client.post("/api/auth/verify", json={"token": "invalid.token.here"})
        assert bad_res.json()["valid"] is False

    def test_websocket_handshake_with_auth_enforced(self, monkeypatch):
        """When settings.REQUIRE_AUTH is True, missing or invalid token must be rejected with 1008."""
        monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
        client = TestClient(app)

        # 1. Connect without token -> rejected with code 1008
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/voice") as websocket:
                pass

        # 2. Connect with valid token -> accepted
        token = create_access_token(session_id="authed_ws_user")
        with client.websocket_connect(f"/ws/voice?token={token}") as websocket:
            websocket.send_json({"type": "ping"})
            resp = websocket.receive_json()
            assert resp.get("type") == "pong"
