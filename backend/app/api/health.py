"""
Health check API router for VoiceSense AI.
Handles GET /api/health returning per-component readiness and overall health.
"""

from fastapi import APIRouter
from backend.app.services.speech_service import speech_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """
    Returns system health status:
    - per-component status: asr, emotion, and placeholders for llm, rag, tts, db as 'not_configured'
    - overall status: 'ok' or 'degraded' (never fails just because optional components are down)
    """
    return speech_service.get_health_status()
