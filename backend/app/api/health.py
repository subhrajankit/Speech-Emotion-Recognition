"""
Health check API router for VoiceSense AI.
Handles GET /api/health returning per-component readiness and overall health.
"""

from fastapi import APIRouter
from backend.app.services.speech_service import speech_service
from backend.app.services.llm_service import llm_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """
    Returns system health status:
    - per-component status: asr, emotion, llm, and placeholders for rag, tts, db
    - overall status: 'ok' or 'degraded' (never fails just because optional components are down)
    """
    health = speech_service.get_health_status()
    await llm_service.check_health()
    llm_report = llm_service.get_health_status()
    health["components"]["llm"] = llm_report["status"]
    health["details"]["llm"] = llm_report
    return health
