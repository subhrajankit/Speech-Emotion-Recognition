import pytest
from src.backend.models.llm import LlamaCppClient

@pytest.mark.asyncio
async def test_llm_mock_generation():
    client = LlamaCppClient(mock=True)
    assert client.is_loaded is True

    prompt = "What is the capital of France?"
    response = await client.generate_response(prompt)
    assert isinstance(response, str)
    assert len(response) > 0

@pytest.mark.asyncio
async def test_llm_empty_prompt():
    client = LlamaCppClient(mock=True)
    response = await client.generate_response("")
    assert "did not receive" in response.lower()
