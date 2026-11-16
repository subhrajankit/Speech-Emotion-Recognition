"""
Regression tests for bounded upload reading in process_audio_upload.

Uses a small patched MAX_UPLOAD_SIZE_BYTES so tests never allocate large files.
The fake upload object proves the oversize path stops reading early instead of
buffering the entire body.
"""

import pytest
from fastapi import HTTPException

from backend.app.api.speech import process_audio_upload
from backend.app.core.config import settings
from backend.app.services.speech_service import speech_service
from ai.inference.types import SpeechResult


class FakeUpload:
    """Duck-typed UploadFile: serves fixed-size chunks, tracks read calls."""

    def __init__(self, data: bytes, chunk_size: int = 4,
                 filename: str = "test.bin", content_type: str = "audio/wav"):
        self._data = data
        self._pos = 0
        self._chunk = chunk_size
        self.content_type = content_type
        self.filename = filename
        self.read_calls = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if self._pos >= len(self._data):
            return b""
        n = min(self._chunk, len(self._data) - self._pos)
        chunk = self._data[self._pos:self._pos + n]
        self._pos += n
        return chunk

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def small_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 10)


@pytest.mark.asyncio
async def test_upload_at_size_limit_passes_size_check(small_limit, monkeypatch):
    """A file exactly at the limit is not rejected by the size check."""
    async def fake_transcribe(**kwargs):
        return SpeechResult(transcript="ok", language="en",
                            processing_time_ms=1, model_version="test")

    monkeypatch.setattr(speech_service, "transcribe_audio_bytes", fake_transcribe)
    upload = FakeUpload(b"\x00" * 10)  # exactly 10 bytes, non-WAV name skips container check

    result = await process_audio_upload(file=upload, language_hint="en")
    assert result.transcript == "ok"
    assert upload.closed is False


@pytest.mark.asyncio
async def test_upload_one_byte_over_limit_returns_413(small_limit):
    """One byte over the limit returns structured 413 FILE_TOO_LARGE."""
    upload = FakeUpload(b"x" * 11)

    with pytest.raises(HTTPException) as exc_info:
        await process_audio_upload(file=upload, language_hint="en")

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["error"]["code"] == "FILE_TOO_LARGE"
    assert upload.closed is True


@pytest.mark.asyncio
async def test_oversize_path_stops_reading_early(small_limit):
    """Oversize detection aborts mid-stream; remaining bytes are never read."""
    # 100 bytes available, limit 10, 4-byte chunks -> stops after 3rd read (12 > 10)
    upload = FakeUpload(b"y" * 100, chunk_size=4)

    with pytest.raises(HTTPException) as exc_info:
        await process_audio_upload(file=upload, language_hint="en")

    assert exc_info.value.status_code == 413
    assert upload.read_calls == 3, (
        f"Expected exactly 3 read calls before abort, got {upload.read_calls}"
    )
    assert upload._pos == 12  # only 12 of 100 bytes consumed


@pytest.mark.asyncio
async def test_empty_upload_still_returns_400(small_limit):
    """0-byte uploads retain the existing EMPTY_AUDIO behavior."""
    upload = FakeUpload(b"")

    with pytest.raises(HTTPException) as exc_info:
        await process_audio_upload(file=upload, language_hint="en")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"]["code"] == "EMPTY_AUDIO"


# --- Chunk 7.4D: error-detail sanitization ---

FAKE_PATH = r"C:\internal\secret_model_weights\model.pt"


@pytest.mark.asyncio
async def test_decode_error_sanitizes_internal_details(small_limit, monkeypatch, caplog):
    """ValueError from decoding -> 400 DECODE_ERROR with no internal path leaked."""
    async def bad_decode(**kwargs):
        raise ValueError(f"Could not decode audio data: file not found {FAKE_PATH}")

    monkeypatch.setattr(speech_service, "transcribe_audio_bytes", bad_decode)
    upload = FakeUpload(b"\x00" * 10)

    with caplog.at_level("ERROR", logger="voicesense.api.speech"):
        with pytest.raises(HTTPException) as exc_info:
            await process_audio_upload(file=upload, language_hint="en")

    assert exc_info.value.status_code == 400
    body = str(exc_info.value.detail)
    assert exc_info.value.detail["error"]["code"] == "DECODE_ERROR"
    assert FAKE_PATH not in body
    assert "model.pt" not in body
    # original exception preserved server-side
    assert FAKE_PATH in caplog.text


@pytest.mark.asyncio
async def test_inference_error_sanitizes_internal_details(small_limit, monkeypatch, caplog):
    """Non-ValueError from inference -> 500 INFERENCE_ERROR with no internal path leaked."""
    async def bad_inference(**kwargs):
        raise RuntimeError(f"CUDA OOM loading {FAKE_PATH}")

    monkeypatch.setattr(speech_service, "transcribe_audio_bytes", bad_inference)
    upload = FakeUpload(b"\x00" * 10)

    with caplog.at_level("ERROR", logger="voicesense.api.speech"):
        with pytest.raises(HTTPException) as exc_info:
            await process_audio_upload(file=upload, language_hint="en")

    assert exc_info.value.status_code == 500
    body = str(exc_info.value.detail)
    assert exc_info.value.detail["error"]["code"] == "INFERENCE_ERROR"
    assert FAKE_PATH not in body
    assert "model.pt" not in body
    assert FAKE_PATH in caplog.text
