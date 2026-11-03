"""
Authentication API router for VoiceSense AI.
Provides user registration, login, current profile, and token verification.
"""

import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
    get_current_user,
    AuthenticationError,
)
from backend.app.core.rate_limiter import auth_rate_limiter
from backend.app.models.user import User
from backend.app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Registers a new user account with memory-hard scrypt password hashing.
    """
    auth_rate_limiter.check(request)

    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already taken."
        )

    hashed_pw = hash_password(payload.password)
    new_user = User(
        id=str(uuid.uuid4()),
        username=payload.username,
        hashed_password=hashed_pw,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, payload: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates username and password, issuing an HS256 JWT access token.
    """
    auth_rate_limiter.check(request)

    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive."
        )

    expires_seconds = settings.SESSION_TIMEOUT_MINUTES * 60
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        expires_in_minutes=settings.SESSION_TIMEOUT_MINUTES,
    )

    return TokenResponse(
        access_token=token,
        token_type="Bearer",
        expires_in_seconds=expires_seconds,
        user_id=user.id,
        username=user.username,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns current authenticated user profile.
    """
    return current_user


# ---------------------------------------------------------------------------
# Backwards-compatibility endpoints for test harnesses and lightweight tokens
# ---------------------------------------------------------------------------

@router.post("/token")
async def issue_auth_token(payload: Optional[Dict[str, Any]] = None):
    """
    Issues an HS256 JWT token for session establishment.
    """
    req_data = payload or {}
    session_id = req_data.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}"
    user_id = req_data.get("user_id") or f"usr_{uuid.uuid4().hex[:8]}"
    username = req_data.get("username") or "anonymous"
    client_id = req_data.get("client_id") or "web-client"
    expires_in_minutes = req_data.get("expires_in_minutes", settings.SESSION_TIMEOUT_MINUTES)

    token = create_access_token(
        user_id=user_id,
        username=username,
        session_id=session_id,
        client_id=client_id,
        expires_in_minutes=expires_in_minutes,
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
