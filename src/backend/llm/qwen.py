"""
Qwen3-1.7B LLM client interface via llama.cpp.
Provides typed access to the local Qwen3-1.7B (Q4_K_M GGUF) model served on 127.0.0.1.
"""
import logging
from typing import Optional, List, Dict, Any
from ..models.llm import LlamaCppClient
from ..config import settings

logger = logging.getLogger(__name__)

class QwenClient(LlamaCppClient):
    """
    Client for local Qwen3-1.7B (Q4_K_M GGUF) via llama.cpp server.
    Configured for low-memory footprint (~1.2GB VRAM) suitable for 4GB shared GPUs (RTX 2050).
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        mock: Optional[bool] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        circuit_breaker: Optional[Any] = None,
        enable_thinking: Optional[bool] = None
    ):
        base_url = base_url or settings.LLAMA_CPP_URL
        model_name = model_name or settings.LLAMA_MODEL_NAME
        timeout = timeout if timeout is not None else settings.LLAMA_TIMEOUT_SECONDS
        mock = mock if mock is not None else settings.MOCK_MODELS
        max_retries = max_retries if max_retries is not None else settings.LLM_MAX_RETRIES
        backoff_factor = backoff_factor if backoff_factor is not None else settings.LLM_BACKOFF_FACTOR
        enable_thinking = enable_thinking if enable_thinking is not None else settings.LLM_ENABLE_THINKING

        super().__init__(
            base_url=base_url,
            model_name=model_name,
            timeout=timeout,
            mock=mock,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            circuit_breaker=circuit_breaker,
            enable_thinking=enable_thinking
        )
        logger.info(f"Initialized QwenClient with model '{self.model_name}' at '{self.base_url}' (mock={self.mock}, enable_thinking={self.enable_thinking}).")

def get_qwen_client(enable_thinking: Optional[bool] = None) -> QwenClient:
    """
    Helper function to instantiate or retrieve configured Qwen3-1.7B client.
    """
    return QwenClient(enable_thinking=enable_thinking)
