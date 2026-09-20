"""
Unit tests for LLM Provider Router and Gemini 3 Flash Client (Phase 17).
Verifies provider selection, per-request overrides, local resilience when GEMINI_API_KEY is missing,
and sentence chunking compatibility.
"""

import pytest
from src.backend.config import settings
from src.backend.llm.router import LLMRouter, get_llm_client, get_active_provider
from src.backend.llm.qwen import QwenClient
from src.backend.llm.gemini import GeminiClient
from src.backend.pipeline.chunker import SentenceBoundaryChunker


def test_default_provider_is_local():
    """Default configuration must strictly be 'local' (offline privacy preserved)."""
    router = LLMRouter()
    assert router.resolve_provider() == "local"
    client = router.get_client()
    assert isinstance(client, QwenClient)


def test_cloud_provider_selection(monkeypatch):
    """When LLM_PROVIDER='cloud', router selects GeminiClient."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    router = LLMRouter()
    assert router.resolve_provider() == "cloud"
    client = router.get_client()
    assert isinstance(client, GeminiClient)


def test_per_request_override(monkeypatch):
    """Per-request override takes precedence over settings.LLM_PROVIDER."""
    # Config is local, override with cloud
    monkeypatch.setattr(settings, "LLM_PROVIDER", "local")
    router = LLMRouter()
    assert router.resolve_provider(provider_override="cloud") == "cloud"
    client = router.get_client(provider_override="cloud")
    assert isinstance(client, GeminiClient)

    # Config is cloud, override with local
    monkeypatch.setattr(settings, "LLM_PROVIDER", "cloud")
    assert router.resolve_provider(provider_override="local") == "local"
    client = router.get_client(provider_override="local")
    assert isinstance(client, QwenClient)


@pytest.mark.asyncio
async def test_local_path_works_with_gemini_key_unset(monkeypatch):
    """Local inference must function 100% normally when GEMINI_API_KEY is empty or missing."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "local")
    monkeypatch.setattr(settings, "MOCK_MODELS", True)

    client = get_llm_client()
    assert isinstance(client, QwenClient)
    assert (await client.check_health()) is True


@pytest.mark.asyncio
async def test_gemini_client_streaming_and_chunking():
    """
    Tests that GeminiClient streams tokens that feed into SentenceBoundaryChunker
    identically to QwenClient without breaking sentence boundaries.
    """
    client = GeminiClient(mock=True)
    assert client.check_health() is True

    chunker = SentenceBoundaryChunker()
    collected_sentences = []

    async for token in client.stream_response(prompt="Explain the weather in Bangalore."):
        sentences = chunker.add_token(token)
        collected_sentences.extend(sentences)

    remaining = chunker.flush()
    if remaining:
        collected_sentences.append(remaining)

    assert len(collected_sentences) > 0
    full_text = " ".join(collected_sentences)
    assert "[Gemini 3 Flash]" in full_text
    assert "Bangalore" in full_text
