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
    assert components.get("llm") in ("ok", "degraded", "unhealthy")

    # Optional / not configured placeholders
    assert components.get("rag") == "not_configured"
    assert components.get("tts") == "not_configured"
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
