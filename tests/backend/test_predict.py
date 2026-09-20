"""
Tests for POST /api/predict endpoint.
Verifies SpeechResult return structure and optional assistant block.
"""

def test_predict_returns_speech_result_with_assistant_block(client, valid_wav_bytes):
    """Verifies that /api/predict returns all SpeechResult fields plus assistant block."""
    files = {"file": ("test.wav", valid_wav_bytes, "audio/wav")}
    response = client.post("/api/predict", files=files)

    assert response.status_code == 200
    data = response.json()

    # Base SpeechResult fields
    assert "transcript" in data
    assert "language" in data
    assert "emotion" in data
    assert "processing_time_ms" in data
    assert "model_version" in data

    # Assistant field defaults to None
    assert "assistant" in data
    assert data["assistant"] is None


def test_predict_with_assistant_flag(client, valid_wav_bytes):
    """Verifies that include_assistant=True populates assistant placeholder."""
    files = {"file": ("test.wav", valid_wav_bytes, "audio/wav")}
    form = {"include_assistant": "true"}
    response = client.post("/api/predict", files=files, data=form)

    assert response.status_code == 200
    data = response.json()
    assert data["assistant"] is not None
    assert data["assistant"]["status"] == "not_configured"


def test_predict_shares_error_behavior_with_upload(client, empty_audio_bytes):
    """Verifies that validation errors on /api/predict match /api/speech/upload."""
    files = {"file": ("empty.wav", empty_audio_bytes, "audio/wav")}
    response = client.post("/api/predict", files=files)

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "EMPTY_AUDIO"
