import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.backend.llm.qwen import QwenClient, get_qwen_client
from src.backend.models.llm import LlamaCppClient
from src.backend.config import settings

@pytest.mark.asyncio
async def test_llm_client_default_enable_thinking_false():
    """
    Asserts that QwenClient defaults enable_thinking to False, and that
    chat_template_kwargs.enable_thinking is False in the payload sent to llama.cpp.
    """
    client = QwenClient(mock=False)
    assert client.enable_thinking is False

    captured_payload = {}

    class MockStreamResponse:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            chunk = {
                "choices": [{
                    "delta": {"content": "Hello there!"}
                }]
            }
            yield f"data: {json.dumps(chunk)}"
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_stream(method, url, json=None, **kwargs):
        captured_payload.update(json)
        return MockStreamResponse()

    with patch("httpx.AsyncClient.stream", side_effect=mock_stream):
        response = await client.generate_response("hii")
        assert response == "Hello there!"
        assert "chat_template_kwargs" in captured_payload
        assert captured_payload["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_llm_client_per_request_thinking_override():
    """
    Asserts that per-request enable_thinking overrides the default false in the payload.
    """
    client = QwenClient(mock=False)
    captured_payload = {}

    class MockStreamResponse:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            chunk = {
                "choices": [{
                    "delta": {"content": "Reasoned response."}
                }]
            }
            yield f"data: {json.dumps(chunk)}"
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_stream(method, url, json=None, **kwargs):
        captured_payload.update(json)
        return MockStreamResponse()

    with patch("httpx.AsyncClient.stream", side_effect=mock_stream):
        tokens = []
        async for tok in client.stream_response("solve 2+2", enable_thinking=True):
            tokens.append(tok)
        assert "".join(tokens) == "Reasoned response."
        assert captured_payload["chat_template_kwargs"]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_llm_client_instance_level_thinking_toggle():
    """
    Asserts that initializing QwenClient with enable_thinking=True sets default payload to True.
    """
    client = QwenClient(mock=False, enable_thinking=True)
    assert client.enable_thinking is True

    captured_payload = {}

    class MockStreamResponse:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            chunk = {
                "choices": [{
                    "delta": {"content": "Thinking enabled."}
                }]
            }
            yield f"data: {json.dumps(chunk)}"
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_stream(method, url, json=None, **kwargs):
        captured_payload.update(json)
        return MockStreamResponse()

    with patch("httpx.AsyncClient.stream", side_effect=mock_stream):
        response = await client.generate_response("test")
        assert captured_payload["chat_template_kwargs"]["enable_thinking"] is True
