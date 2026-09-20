"""
Unit tests for LLMService, PromptBuilder, and thinking-mode filters.
Uses httpx fault injection (MockTransport) to verify typed error handling,
streaming SSE parsing, cool-down logic, and prompt construction.
"""

import json
import pytest
import httpx

from backend.app.services.llm_service import (
    LLMService,
    LLMUnavailable,
    LLMTimeout,
    LLMResponseError,
    ThinkingFilter,
    strip_thinking_tags,
)
from backend.app.services.prompt_builder import PromptBuilder, estimate_tokens


# ==============================================================================
# PromptBuilder Tests
# ==============================================================================

def test_prompt_builder_emotion_and_language_conditioning():
    prompt = PromptBuilder.build_system_prompt(emotion="happy", language="en")
    assert "happy" in prompt
    assert "English" in prompt
    assert "1 to 2 clear sentences" in prompt

    hindi_sad_prompt = PromptBuilder.build_system_prompt(emotion="sad", language="hi")
    assert "sad" in hindi_sad_prompt
    assert "Hindi" in hindi_sad_prompt
    assert "empathy" in hindi_sad_prompt

    neutral_prompt = PromptBuilder.build_system_prompt(emotion="neutral", language="en")
    assert "calm or neutral" in neutral_prompt


def test_prompt_builder_conversation_history_token_budget():
    history = [
        {"role": "user", "content": "Turn 1: Very old context from earlier in the day."},
        {"role": "assistant", "content": "Turn 1 reply: Yes, that was long ago."},
        {"role": "user", "content": "Turn 2: Recent context."},
        {"role": "assistant", "content": "Turn 2 reply: Yes, right now."},
    ]

    # With a small budget, older turns should be truncated while recent ones are preserved
    messages = PromptBuilder.build_chat_messages(
        transcript="Turn 3: Latest question.",
        conversation_history=history,
        emotion="neutral",
        language="en",
        max_history_tokens=20,  # Tight budget fitting only recent turns
    )

    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Turn 3: Latest question."

    # Turn 1 should be excluded if budget was constrained
    all_contents = [m["content"] for m in messages]
    assert "Turn 2: Recent context." in all_contents or "Turn 2 reply: Yes, right now." in all_contents
    assert "Turn 1: Very old context from earlier in the day." not in all_contents


# ==============================================================================
# Thinking Filter Tests
# ==============================================================================

def test_strip_thinking_tags_non_streaming():
    raw = "<think>Let me reason step by step.\nUser is asking for weather.</think>It is sunny today."
    cleaned = strip_thinking_tags(raw)
    assert cleaned == "It is sunny today."


def test_thinking_filter_streaming_split_chunks():
    flt = ThinkingFilter()
    chunks = ["<th", "ink>I am think", "ing deeply</think>Hello", " world!"]
    output = []
    for c in chunks:
        out = flt.process_chunk(c)
        if out:
            output.append(out)
    output.append(flt.flush())

    result = "".join(output)
    assert result == "Hello world!"
    assert "<think>" not in result
    assert "thinking deeply" not in result


# ==============================================================================
# LLMService Unit Tests with httpx MockTransport
# ==============================================================================

@pytest.mark.asyncio
async def test_llm_service_streaming_success():
    sse_events = [
        b'data: {"choices":[{"delta":{"content":"<think>planning</think>Hello"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" there!"}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, content=b"".join(sse_events))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = LLMService(base_url="http://127.0.0.1:8080", client=client)
        stream = await service.generate(
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )

        tokens = []
        async for token in stream:
            tokens.append(token)

        full_reply = "".join(tokens)
        assert full_reply == "Hello there!"
        assert "<think>" not in full_reply


@pytest.mark.asyncio
async def test_llm_service_non_streaming_success():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body.get("stream") is False
        assert body.get("chat_template_kwargs", {}).get("enable_thinking") is False

        resp_data = {
            "choices": [
                {"message": {"role": "assistant", "content": "<think>pondering</think>Direct answer."}}
            ]
        }
        return httpx.Response(200, json=resp_data)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = LLMService(base_url="http://127.0.0.1:8080", client=client)
        reply = await service.generate(
            messages=[{"role": "user", "content": "Question"}],
            stream=False,
        )
        assert reply == "Direct answer."


@pytest.mark.asyncio
async def test_llm_service_500_raises_llm_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error in llama.cpp")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = LLMService(base_url="http://127.0.0.1:8080", client=client)
        with pytest.raises(LLMUnavailable):
            await service.generate(
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )


@pytest.mark.asyncio
async def test_llm_service_timeout_raises_llm_timeout():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout waiting for first token")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = LLMService(base_url="http://127.0.0.1:8080", client=client)
        with pytest.raises(LLMTimeout):
            await service.generate(
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )


@pytest.mark.asyncio
async def test_llm_service_health_check_and_cooldown():
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": [{"id": "qwen3-1.7b"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = LLMService(base_url="http://127.0.0.1:8080", client=client)
        service._health_cache_ttl = 5.0

        # First check triggers network call
        h1 = await service.check_health()
        assert h1 is True
        assert call_count == 1

        # Immediate second check uses cache
        h2 = await service.check_health()
        assert h2 is True
        assert call_count == 1  # No second network call

    # Test cool-down after failure threshold
    async def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    failing_transport = httpx.MockTransport(failing_handler)
    async with httpx.AsyncClient(transport=failing_transport) as client:
        service = LLMService(base_url="http://127.0.0.1:8080", client=client)
        service._failure_threshold = 3
        service._cooldown_duration = 10.0

        for _ in range(3):
            await service.check_health(force=True)

        assert service.is_in_cooldown() is True
        report = service.get_health_status()
        assert report["status"] == "unhealthy"
        assert report["in_cooldown"] is True

        # When in cool-down, generate() must immediately raise LLMUnavailable without network call
        with pytest.raises(LLMUnavailable) as exc_info:
            await service.generate([{"role": "user", "content": "test"}], stream=False)
        assert "cooldown active" in str(exc_info.value)
