"""
Authentication and JWT management for VoiceSense AI Backend.
Provides zero-dependency HMAC-SHA256 (HS256) JWT generation and verification.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

from backend.app.core.config import settings


class AuthenticationError(Exception):
    """Raised when token validation or session authentication fails."""
    pass


def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding as per RFC 7515."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _base64url_decode(data_str: str) -> bytes:
    """Base64url decode with padding restoration."""
    rem = len(data_str) % 4
    if rem > 0:
        data_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data_str.encode("utf-8"))


def create_access_token(
    session_id: str,
    client_id: str = "web-client",
    expires_in_minutes: Optional[int] = None,
    custom_claims: Optional[Dict[str, Any]] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Generate an HS256 JWT access token for WebSocket / WebTransport sessions.
    """
    secret = (secret_key or settings.JWT_SECRET).encode("utf-8")
    now = int(time.time())
    ttl = (expires_in_minutes if expires_in_minutes is not None else settings.SESSION_TIMEOUT_MINUTES) * 60
    exp = now + ttl

    header = {
        "alg": "HS256",
        "typ": "JWT",
    }

    payload: Dict[str, Any] = {
        "sub": session_id,
        "client_id": client_id,
        "iat": now,
        "nbf": now,
        "exp": exp,
    }
    if custom_claims:
        payload.update(custom_claims)

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    encoded_header = _base64url_encode(header_bytes)
    encoded_payload = _base64url_encode(payload_bytes)

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    encoded_signature = _base64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def verify_access_token(
    token: str,
    secret_key: Optional[str] = None,
    leeway_seconds: int = 10,
) -> Dict[str, Any]:
    """
    Validate an HS256 JWT access token and return its payload.

    Raises AuthenticationError if:
      - Token format is malformed.
      - Algorithm is not HS256.
      - Signature is invalid.
      - Token is expired or not yet valid.
    """
    if not token or not isinstance(token, str):
        raise AuthenticationError("Token must be a non-empty string")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise AuthenticationError("Malformed token: expected header.payload.signature")

    encoded_header, encoded_payload, encoded_signature = parts

    # 1. Parse and verify header
    try:
        header_bytes = _base64url_decode(encoded_header)
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as e:
        raise AuthenticationError(f"Invalid token header: {e}")

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise AuthenticationError(f"Unsupported algorithm '{header.get('alg')}': only HS256 is permitted")

    # 2. Verify signature using constant-time comparison
    secret = (secret_key or settings.JWT_SECRET).encode("utf-8")
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _base64url_decode(encoded_signature)
    except Exception as e:
        raise AuthenticationError(f"Invalid signature encoding: {e}")

    if not hmac.compare_digest(actual_sig, expected_sig):
        raise AuthenticationError("Token signature verification failed")

    # 3. Parse and verify payload
    try:
        payload_bytes = _base64url_decode(encoded_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise AuthenticationError(f"Invalid token payload: {e}")

    if not isinstance(payload, dict):
        raise AuthenticationError("Token payload must be a JSON object")

    now = time.time()

    # Expiration check
    exp = payload.get("exp")
    if exp is not None:
        if not isinstance(exp, (int, float)):
            raise AuthenticationError("Claim 'exp' must be numeric timestamp")
        if now > (exp + leeway_seconds):
            raise AuthenticationError("Token has expired")

    # Not Before check
    nbf = payload.get("nbf")
    if nbf is not None:
        if not isinstance(nbf, (int, float)):
            raise AuthenticationError("Claim 'nbf' must be numeric timestamp")
        if now < (nbf - leeway_seconds):
            raise AuthenticationError("Token is not yet active (nbf check failed)")

    return payload
