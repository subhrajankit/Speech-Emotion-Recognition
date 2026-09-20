"""API routers package."""
from .health import router as health_router
from .speech import router as speech_router
from .prediction import router as prediction_router
from .auth import router as auth_router

__all__ = [
    "health_router",
    "speech_router",
    "prediction_router",
    "auth_router",
]
