"""
Authentication and JWT management for VoiceSense AI Backend.
Provides zero-dependency HMAC-SHA256 (HS256) JWT generation and verification,
stdlib scrypt memory-hard password hashing, and FastAPI authentication dependencies.
"""

import os
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


class AuthenticationError(Exception):
    """Raised when token validation or session authentication fails."""
    pass


# ---------------------------------------------------------------------------
# Password Hashing via Python stdlib hashlib.scrypt (zero native dependencies)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """
    Hashes a password using stdlib hashlib.scrypt with a 16-byte cryptographically secure salt.
    Format: $scrypt$ln=14,r=8,p=1$<salt_b64>$<hash_b64>
    """
    if not password:
        raise ValueError("Password cannot be empty")
    salt = os.urandom(16)
    # n = 2**14 = 16384, r = 8, p = 1, maxmem = 32MB
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        maxmem=32 * 1024 * 1024
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"$scrypt$ln=14,r=8,p=1${salt_b64}${hash_b64}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against an scrypt hash using constant-time comparison.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        if not hashed_password.startswith("$scrypt$"):
            return False
        parts = hashed_password.split("$")
        # Format: ["", "scrypt", "ln=14,r=8,p=1", salt_b64, hash_b64]
        if len(parts) != 5:
            return False
        _params, salt_b64, hash_b64 = parts[2], parts[3], parts[4]
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_hash = base64.b64decode(hash_b64.encode("ascii"))
        derived = hashlib.scrypt(
            plain_password.encode("utf-8"),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            maxmem=32 * 1024 * 1024
        )
        return hmac.compare_digest(derived, expected_hash)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Zero-dependency RFC 7515 HS256 JWT Token Management
# ---------------------------------------------------------------------------

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
    user_id: str,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
    client_id: str = "web-client",
    expires_in_minutes: Optional[int] = None,
    custom_claims: Optional[Dict[str, Any]] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Generate an HS256 JWT access token for REST and WebSocket sessions.
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
        "sub": user_id,
        "username": username or "",
        "session_id": session_id,
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


# ---------------------------------------------------------------------------
# FastAPI Authentication Dependencies
# ---------------------------------------------------------------------------

def extract_token_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Helper to extract bearer token from standard Authorization header."""
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    auth_header_token: Optional[str] = Depends(extract_token_from_header),
    db: Session = Depends(get_db),
):
    """
    Returns the authenticated User or None if unauthenticated.
    Accepts token from either OAuth2 scheme or Authorization header.
    """
    raw_token = token or auth_header_token
    if not raw_token:
        return None

    try:
        payload = verify_access_token(raw_token)
    except AuthenticationError:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    from backend.app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None

    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    auth_header_token: Optional[str] = Depends(extract_token_from_header),
    db: Session = Depends(get_db),
):
    """
    Strict authentication dependency. Raises HTTP 401 if token is missing, expired, or invalid.
    """
    raw_token = token or auth_header_token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_access_token(raw_token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from backend.app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user
