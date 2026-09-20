import json
import logging
import uuid
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from .audio.vad import VADSpeechSegmenter
from .config import settings
from .models.manager import model_manager
from .pipeline import VoicePipeline
from .transport.websocket_fallback import websocket_voice_endpoint as ws_voice_handler
from .transport.webtransport import webtransport_manager
from .telemetry import benchmark_collector
from .security import (
    AuthenticationError,
    create_access_token,
    verify_access_token,
)

# Setup Logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("senseai.backend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Rule: Load every model once at startup. Never load per-request.
    logger.info("Initializing SenseAI Voice Assistant models at startup...")
    model_manager.initialize()
    logger.info("Startup complete. SenseAI server ready.")
    yield
    logger.info("Shutting down SenseAI backend.")

app = FastAPI(
    title="SenseAI Voice Assistant Backend",
    version="0.11.0",
    description="Phase 11: Security hardening with JWT auth, rate limiting, and document validation",
    lifespan=lifespan
)

# CORS configuration for local React Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = VoicePipeline()

@app.post("/api/auth/token")
async def issue_auth_token(payload: Optional[dict] = None):
    """
    Issues an HS256 JWT access token for establishing authenticated WebSocket/WebTransport sessions.
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

@app.post("/api/auth/verify")
async def verify_auth_token(payload: dict):
    """
    Validates a JWT token and returns claims if valid.
    """
    token = payload.get("token", "")
    try:
        claims = verify_access_token(token)
        return {"valid": True, "claims": claims}
    except AuthenticationError as e:
        return {"valid": False, "error": str(e)}

@app.get("/health")
async def health_check():
    """
    Health check endpoint reporting model loading and service readiness.
    """
    return await model_manager.get_health_status()

@app.get("/api/emotion/history/{conversation_id}")
async def get_conversation_emotion_history(conversation_id: str, limit: int = 10):
    """
    Retrieves stored emotion trajectory for a given conversation.
    """
    if model_manager.emotion_storage:
        return model_manager.emotion_storage.get_history(conversation_id, limit=limit)
    return []

@app.get("/api/benchmark/metrics")
async def get_benchmark_metrics(limit: int = 50):
    """
    Returns the last N requests with per-stage timings:
    (audio_received, vad, asr, emotion, router, rag, llm_ttft, llm_total, tts_ttfa, total)
    """
    return benchmark_collector.get_recent(limit=limit)

@app.get("/api/benchmark/summary")
async def get_benchmark_summary():
    """
    Returns aggregate per-stage latency statistics (min, avg, max, p95).
    """
    return benchmark_collector.get_summary()

@app.post("/api/benchmark/reset")
async def reset_benchmark_metrics():
    """
    Clears in-memory benchmark metrics buffer.
    """
    benchmark_collector.clear()
    return {"status": "cleared", "count": 0}

@app.get("/api/transport/capabilities")
async def get_transport_capabilities():
    """
    Returns supported transport capabilities (WebTransport multi-stream + WebSocket fallback).
    """
    return webtransport_manager.get_capabilities()

@app.get("/wt")
async def webtransport_info():
    """
    WebTransport information and session capability descriptor endpoint.
    HTTP/3 clients initiate WebTransport sessions via HTTP CONNECT or WebTransport handshake.
    """
    return {
        "transport": "webtransport",
        "status": "ready",
        "capabilities": webtransport_manager.get_capabilities()
    }

@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    WebSocket voice endpoint (delegates to transport.websocket_fallback).
    Preserves 100% backward compatibility for tests and client fallback.
    """
    await ws_voice_handler(websocket, pipeline=pipeline)

