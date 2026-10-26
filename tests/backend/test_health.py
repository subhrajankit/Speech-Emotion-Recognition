"""
Tests for GET /api/health endpoint.
"""

def test_health_check_structure(client):
    """Verifies that /api/health returns per-component status and overall status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] in ("ok", "degraded")

    assert "components" in data
    components = data["components"]

    # Required components
    assert "asr" in components
    assert components["asr"] in ("ok", "degraded")

    assert "emotion" in components
    assert components["emotion"] in ("ok", "degraded")

    # Configured in Phase 6: LLM
    assert components.get("llm") in ("ok", "unavailable")

    # Phase 7: RAG reports real status ('ok', 'no_index', or 'unavailable')
    assert components.get("rag") in ("ok", "no_index", "unavailable")
    # Phase 8: TTS reports real status ('ok', 'not_loaded', 'unavailable', or 'disabled')
    assert components.get("tts") in ("ok", "not_loaded", "unavailable", "disabled")
    assert components.get("db") == "not_configured"


    # Details
    assert "details" in data
    assert "concurrency_limit" in data["details"]


def test_health_never_fails_for_optional_components(client):
    """Confirms system does not report failure when optional components are not configured."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] != "unhealthy"
    assert data["status"] != "error"
