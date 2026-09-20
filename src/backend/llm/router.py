"""
LLM Provider Router (Phase 17).
Selects between the local Qwen3-1.7B model and cloud Gemini 3 Flash.
Guarantees identical downstream interface and behavior for sentence chunking and TTS.
"""

import logging
from typing import Optional, Union, Any

from ..config import settings
from .qwen import QwenClient, get_qwen_client
from .gemini import GeminiClient, get_gemini_client

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM reasoning requests to either local Qwen3 or cloud Gemini.
    Strict Invariant:
    - Default is ALWAYS 'local' (offline privacy preserved).
    - 'cloud' is an explicit opt-in selection via env var or per-request override.
    """

    def __init__(self):
        self._local_client: Optional[QwenClient] = None
        self._cloud_client: Optional[GeminiClient] = None

    @property
    def local_client(self) -> QwenClient:
        if self._local_client is None or self._local_client.mock != settings.MOCK_MODELS:
            self._local_client = get_qwen_client()
        return self._local_client

    @property
    def cloud_client(self) -> GeminiClient:
        if self._cloud_client is None or self._cloud_client.mock != settings.MOCK_MODELS:
            self._cloud_client = get_gemini_client()
        return self._cloud_client

    def reset(self):
        """Clears cached clients so updated settings immediately take effect."""
        self._local_client = None
        self._cloud_client = None

    def resolve_provider(self, provider_override: Optional[str] = None) -> str:
        """
        Determines the active provider ('local' or 'cloud').
        Prioritizes per-request override, falling back to settings.LLM_PROVIDER.
        """
        if provider_override and provider_override.lower() in ("cloud", "gemini"):
            return "cloud"
        if provider_override and provider_override.lower() in ("local", "qwen"):
            return "local"

        configured = getattr(settings, "LLM_PROVIDER", "local").lower()
        if configured in ("cloud", "gemini"):
            return "cloud"
        return "local"

    def get_client(self, provider_override: Optional[str] = None) -> Any:
        """
        Returns the appropriate LLM client matching the resolved provider.
        """
        provider = self.resolve_provider(provider_override)
        if provider == "cloud":
            logger.info("[LLMRouter] Routing request to Cloud Gemini 3 Flash provider.")
            return self.cloud_client
        else:
            return self.local_client


# Module-level singleton
llm_router = LLMRouter()


def get_llm_client(provider_override: Optional[str] = None) -> Any:
    """Convenience helper to retrieve the active LLM client."""
    return llm_router.get_client(provider_override)


def get_active_provider(provider_override: Optional[str] = None) -> str:
    """Convenience helper to get the active provider name ('local' or 'cloud')."""
    return llm_router.resolve_provider(provider_override)
