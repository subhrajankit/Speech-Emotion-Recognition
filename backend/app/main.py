"""
VoiceSense AI Backend FastAPI Application.
Provides application factory create_app(), lifespan lifecycle, CORS middleware,
modular API and WebSocket routers, and consistent error handling.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.logging import setup_logging, logger
from backend.app.schemas.errors import create_error_payload
from backend.app.services.speech_service import speech_service
from backend.app.services.rag_service import rag_service

from backend.app.api.health import router as health_router
from backend.app.api.speech import router as speech_router
from backend.app.api.prediction import router as prediction_router
from backend.app.api.auth import router as auth_router
from backend.app.api.history import router as history_router
from backend.app.websocket.speech_socket import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Rule: Load every model ONCE at startup. Never load per-request.
    """
    setup_logging()
    logger.info("Initializing VoiceSense AI Backend services at startup...")
    speech_service.initialize()
    rag_service.initialize()
    logger.info("Startup complete. VoiceSense server ready.")
    yield
    logger.info("Shutting down VoiceSense AI Backend.")


def create_app() -> FastAPI:
    """
    Application factory for VoiceSense AI Backend.
    """
    app = FastAPI(
        title="VoiceSense AI Backend",
        version="0.2.0",
        description="Phase 2: Modular FastAPI backend with non-blocking speech perception and WebSocket v1.",
        lifespan=lifespan
    )

    # CORS configuration from settings/env
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Standardized HTTP error handling
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # If detail is already formatted with error dictionary
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_payload(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail)
            )
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled server error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=create_error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred.",
                details={"error_type": type(exc).__name__}
            )
        )

    # Mount routers
    app.include_router(health_router)
    app.include_router(speech_router)
    app.include_router(prediction_router)
    app.include_router(auth_router)
    app.include_router(history_router)
    app.include_router(websocket_router)

    return app


# Default app instance for uvicorn
app = create_app()
