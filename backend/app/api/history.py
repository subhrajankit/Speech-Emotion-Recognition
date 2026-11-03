"""
History API router for VoiceSense AI.
Provides session listing, inspection, deletion, and complete data purge.
All operations are strictly isolated to the authenticated user.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.user import User
from backend.app.models.session import Session as DBSession
from backend.app.models.prediction import Prediction
from backend.app.schemas.history import (
    SessionSummarySchema,
    SessionDetailSchema,
    DeleteHistoryResponse,
)

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/sessions", response_model=List[SessionSummarySchema])
async def list_user_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all conversational sessions owned by the authenticated user.
    """
    sessions = (
        db.query(
            DBSession.id,
            DBSession.primary_language,
            DBSession.created_at,
            DBSession.updated_at,
            func.count(Prediction.id).label("turn_count"),
        )
        .outerjoin(Prediction, Prediction.session_id == DBSession.id)
        .filter(DBSession.user_id == current_user.id)
        .group_by(DBSession.id)
        .order_by(DBSession.updated_at.desc())
        .all()
    )

    return [
        SessionSummarySchema(
            id=s.id,
            primary_language=s.primary_language,
            created_at=s.created_at,
            updated_at=s.updated_at,
            turn_count=s.turn_count,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailSchema)
async def get_session_detail(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves complete session details including predictions, transcripts,
    emotion results, and messages for the authenticated user.
    Strict user isolation enforced: accessing another user's session returns 404.
    """
    session = (
        db.query(DBSession)
        .filter(DBSession.id == session_id, DBSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found."
        )

    return session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deletes a specific session belonging to the authenticated user.
    Cascading foreign keys purge all associated predictions, transcripts, and messages.
    """
    session = (
        db.query(DBSession)
        .filter(DBSession.id == session_id, DBSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found."
        )

    db.delete(session)
    db.commit()
    return {"deleted": True, "session_id": session_id}


@router.delete("", response_model=DeleteHistoryResponse)
async def delete_all_user_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete-My-Data endpoint: permanently purges ALL sessions, transcripts,
    predictions, and messages for the authenticated user.
    """
    sessions = db.query(DBSession).filter(DBSession.user_id == current_user.id).all()
    count = len(sessions)
    for s in sessions:
        db.delete(s)
    db.commit()

    return DeleteHistoryResponse(
        deleted=True,
        purged_sessions_count=count,
        message=f"Purged {count} session(s) and all associated transcripts and history.",
    )
