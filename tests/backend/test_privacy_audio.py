"""
Privacy & Audio Retention Invariant Tests for VoiceSense AI.
Verifies that raw audio is NEVER persisted to database tables, file systems, or temp caches.
Verifies STORE_TRANSCRIPTS privacy policy enforcement.
"""

import os
import glob
import time
import tempfile
from pathlib import Path
import pytest
import soundfile as sf
import httpx
from sqlalchemy import LargeBinary, BLOB
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.database import Base, get_db_session
from backend.app.core.security import create_access_token
from backend.app.services.llm_service import llm_service
from backend.app.models.transcript import Transcript
from backend.app.models.message import Message


def test_no_raw_audio_columns_in_database_schema():
    """
    Acceptance Criterion:
    Proves that the database schema contains zero BLOB or LargeBinary columns for storing audio.
    """
    forbidden_types = (LargeBinary, BLOB)
    audio_columns = []

    for table_name, table in Base.metadata.tables.items():
        for column in table.columns:
            if isinstance(column.type, forbidden_types):
                audio_columns.append(f"{table_name}.{column.name} ({column.type})")
            if any(term in column.name.lower() for term in ("audio_bytes", "raw_audio", "wav_blob", "pcm_blob")):
                audio_columns.append(f"{table_name}.{column.name}")

    assert not audio_columns, f"Forbidden audio storage columns detected in schema: {audio_columns}"


def test_no_audio_files_persisted_to_temp_or_disk(client: TestClient, monkeypatch):
    """
    Acceptance Criterion:
    Inspects temp directories and ensures no raw audio (.wav, .pcm) is persisted during/after a turn.
    """
    temp_dir = tempfile.gettempdir()
    before_wavs = set(glob.glob(os.path.join(temp_dir, "*.wav")))
    before_pcms = set(glob.glob(os.path.join(temp_dir, "*.pcm")))

    token = create_access_token(user_id="usr_privacy_test", username="privacy_tester")

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"Privacy check response"}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    def mock_handler(request):
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
            "auth_token": token,
        })
        assert ws.receive_json()["type"] == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        data, _ = sf.read(str(sample_path), dtype="int16")
        pcm_bytes = data[:32000].tobytes()

        chunk_size = 1024
        for i in range(0, len(pcm_bytes), chunk_size):
            ws.send_bytes(pcm_bytes[i : i + chunk_size])

        ws.send_json({"type": "stop"})

        # Wait for completion with bounded loop
        for _ in range(15):
            try:
                msg = ws.receive_json()
                if msg.get("type") in ("llm_done", "error"):
                    break
            except Exception:
                break

    after_wavs = set(glob.glob(os.path.join(temp_dir, "*.wav")))
    after_pcms = set(glob.glob(os.path.join(temp_dir, "*.pcm")))

    new_wavs = after_wavs - before_wavs
    new_pcms = after_pcms - before_pcms

    assert not new_wavs, f"Unexpected WAV audio files persisted in temp: {new_wavs}"
    assert not new_pcms, f"Unexpected PCM audio files persisted in temp: {new_pcms}"


def test_store_transcripts_policy(client: TestClient, monkeypatch):
    """
    Acceptance Criterion:
    When STORE_TRANSCRIPTS=False, user speech transcripts are redacted.
    """
    orig_policy = settings.STORE_TRANSCRIPTS
    try:
        settings.STORE_TRANSCRIPTS = False
        token = create_access_token(user_id="usr_redaction_test", username="redaction_tester")

        sse_chunks = [
            b'data: {"choices":[{"delta":{"content":"Redaction check response"}}]}\n\n',
            b'data: [DONE]\n\n',
        ]

        def mock_handler(request):
            return httpx.Response(200, content=b"".join(sse_chunks))

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
        monkeypatch.setattr(llm_service, "_custom_client", mock_client)

        with client.websocket_connect("/ws/speech") as ws:
            ws.send_json({
                "type": "start",
                "session_id": "sess_redaction_check",
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
                "language_hint": "en",
                "auth_token": token,
            })
            assert ws.receive_json()["type"] == "ready"

            sample_path = Path("tests/samples/sample_chinese_speech.wav")
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()

            chunk_size = 1024
            for i in range(0, len(pcm_bytes), chunk_size):
                ws.send_bytes(pcm_bytes[i : i + chunk_size])

            ws.send_json({"type": "stop"})

            for _ in range(15):
                try:
                    msg = ws.receive_json()
                    if msg.get("type") in ("llm_done", "error"):
                        break
                except Exception:
                    break

        time.sleep(0.1)

        # Inspect DB specifically for this session
        with get_db_session() as db:
            transcripts = db.query(Transcript).filter(Transcript.session_id == "sess_redaction_check").all()
            assert len(transcripts) > 0, "Expected transcript row to be created for session"
            for t in transcripts:
                assert t.text == "[REDACTED_BY_POLICY]" or t.text == ""

    finally:
        settings.STORE_TRANSCRIPTS = orig_policy
