"""
Health check API router for VoiceSense AI.
Handles GET /api/health returning per-component readiness and overall health.
Reports DB status as 'ok', 'unavailable', or 'not_configured' without failing overall status.
"""

from fastapi import APIRouter
from backend.app.core.database import check_db_health
from backend.app.services.speech_service import speech_service
from backend.app.services.llm_service import llm_service
from backend.app.services.rag_service import rag_service
from backend.app.services.tts_service import tts_service

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """
    Returns system health status:
    - per-component status: asr, emotion, llm, rag, tts, db
    - overall status: 'ok' or 'degraded' (never fails just because optional components or DB are down)
    """
    health = speech_service.get_health_status()
    await llm_service.check_health()
    llm_report = llm_service.get_health_status()
    health["components"]["llm"] = "ok" if llm_report["status"] == "ok" else "unavailable"
    health["details"]["llm"] = llm_report

    rag_report = rag_service.get_health_status()
    health["components"]["rag"] = rag_report["status"]
    health["details"]["rag"] = rag_report

    tts_report = tts_service.get_health_status()
    health["components"]["tts"] = tts_report.get("status", "unavailable")
    health["details"]["tts"] = tts_report

    # Database health check
    db_status = check_db_health()
    health["components"]["db"] = db_status
    health["details"]["db"] = {"status": db_status}

    return health
