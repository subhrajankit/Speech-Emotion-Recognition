from .speech_service import speech_service, SpeechService
from .llm_service import (
    llm_service,
    LLMService,
    LLMError,
    LLMUnavailable,
    LLMTimeout,
    LLMResponseError,
)
from .prompt_builder import PromptBuilder


def __getattr__(name: str):
    if name in ("rag_service", "RAGService", "RAGTurnResult"):
        from . import rag_service as _rag_mod
        return getattr(_rag_mod, name)
    if name in ("tts_service", "TTSService", "TTSChunk", "TTSError"):
        from . import tts_service as _tts_mod
        return getattr(_tts_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "speech_service",
    "SpeechService",
    "llm_service",
    "LLMService",
    "LLMError",
    "LLMUnavailable",
    "LLMTimeout",
    "LLMResponseError",
    "PromptBuilder",
    "rag_service",
    "RAGService",
    "RAGTurnResult",
    "tts_service",
    "TTSService",
    "TTSChunk",
    "TTSError",
]

