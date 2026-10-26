import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.config import settings

def test_health_endpoint():
    # Force mock mode for deterministic testing
    settings.MOCK_MODELS = True
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "models" in data
        assert "sensevoice_asr" in data["models"]
        assert "llama_cpp_llm" in data["models"]
        assert "indic_parler_tts" in data["models"]
