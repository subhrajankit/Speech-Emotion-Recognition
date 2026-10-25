"""
Health check API router for VoiceSense AI.
Handles GET /api/health returning per-component readiness and overall health.
"""

from fastapi import APIRouter
from backend.app.services.speech_service import speech_service
from backend.app.services.llm_service import llm_service
from backend.app.services.rag_service import rag_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """
    Returns system health status:
    - per-component status: asr, emotion, llm, rag, and placeholders for tts, db
    - overall status: 'ok' or 'degraded' (never fails just because optional components are down)
    """
    health = speech_service.get_health_status()
    await llm_service.check_health()
    llm_report = llm_service.get_health_status()
    health["components"]["llm"] = "ok" if llm_report["status"] == "ok" else "unavailable"
    health["details"]["llm"] = llm_report

    rag_report = rag_service.get_health_status()
    health["components"]["rag"] = rag_report["status"]
    health["details"]["rag"] = rag_report
    return health
