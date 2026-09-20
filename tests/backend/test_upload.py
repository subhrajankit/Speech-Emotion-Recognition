"""
Tests for POST /api/speech/upload endpoint.
Covers valid uploads and input validation (wrong type, oversize, empty, decode error).
"""

from pathlib import Path


def test_upload_valid_audio_returns_speech_result(client, valid_wav_bytes):
    """Verifies that uploading valid audio returns schema-compliant SpeechResult."""
    files = {"file": ("test.wav", valid_wav_bytes, "audio/wav")}
    response = client.post("/api/speech/upload", files=files)

    assert response.status_code == 200
    data = response.json()

    assert "transcript" in data
    assert "language" in data
    assert "emotion" in data
    assert "processing_time_ms" in data
    assert "model_version" in data
    assert data["processing_time_ms"] >= 0


def test_upload_wrong_content_type_returns_415(client):
    """Verifies that non-audio content types are rejected with 415 and error schema."""
    files = {"file": ("notes.txt", b"Hello, this is not an audio file.", "text/plain")}
    response = client.post("/api/speech/upload", files=files)

    assert response.status_code == 415
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_CONTENT_TYPE"
    assert "message" in data["error"]


def test_upload_oversized_audio_returns_413(client, oversized_audio_bytes):
    """Verifies that uploads exceeding MAX_UPLOAD_SIZE_BYTES return 413 with error schema."""
    files = {"file": ("giant.wav", oversized_audio_bytes, "audio/wav")}
    response = client.post("/api/speech/upload", files=files)

    assert response.status_code == 413
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_empty_audio_returns_400(client, empty_audio_bytes):
    """Verifies that 0-byte audio uploads return 400 with error schema."""
    files = {"file": ("empty.wav", empty_audio_bytes, "audio/wav")}
    response = client.post("/api/speech/upload", files=files)

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "EMPTY_AUDIO"


def test_upload_corrupt_audio_returns_decode_error(client):
    """Verifies that un-decodable audio data returns 400 DECODE_ERROR with error schema."""
    files = {"file": ("corrupt.wav", b"RIFFcorrupteddatahere12345", "audio/wav")}
    response = client.post("/api/speech/upload", files=files)

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "DECODE_ERROR"


def test_upload_with_language_hint(client, valid_wav_bytes):
    """Verifies optional language hint is respected."""
    files = {"file": ("speech.wav", valid_wav_bytes, "audio/wav")}
    data = {"language_hint": "en"}
    response = client.post("/api/speech/upload", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["language"] == "en"
