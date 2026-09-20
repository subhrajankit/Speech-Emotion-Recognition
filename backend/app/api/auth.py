"""
Authentication API router for VoiceSense AI.
Re-homes existing endpoints:
- POST /api/auth/token
- POST /api/auth/verify
"""

import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status

from backend.app.core.config import settings
from backend.app.core.security import create_access_token, verify_access_token, AuthenticationError
from backend.app.schemas.errors import create_error_payload

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token")
async def issue_auth_token(payload: Optional[Dict[str, Any]] = None):
    """
    Issues an HS256 JWT access token for establishing authenticated WebSocket sessions.
    """
    req_data = payload or {}
    session_id = req_data.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}"
    client_id = req_data.get("client_id") or "web-client"
    expires_in_minutes = req_data.get("expires_in_minutes", settings.SESSION_TIMEOUT_MINUTES)

    token = create_access_token(
        session_id=session_id,
        client_id=client_id,
        expires_in_minutes=expires_in_minutes
    )
    return {
        "token": token,
        "token_type": "Bearer",
        "session_id": session_id,
        "expires_in_seconds": expires_in_minutes * 60,
    }


@router.post("/verify")
async def verify_token_endpoint(payload: Dict[str, Any]):
    """
    Validates a JWT token and returns claims if valid.
    """
    token = payload.get("token", "")
    try:
        claims = verify_access_token(token)
        return {"valid": True, "claims": claims}
    except AuthenticationError as e:
        return {"valid": False, "error": str(e)}
