"""
Fault Isolation Tests: Database Failure during WebSocket Voice Turns.
Verifies that if the database is unreachable or down, the WebSocket STILL delivers
speech_result and llm_done without interruption, with the persistence error logged and swallowed.
"""

import json
import time
import sys
from pathlib import Path
import pytest
import soundfile as sf
import httpx
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.core.security import create_access_token
from backend.app.services.llm_service import llm_service


def test_websocket_delivers_events_when_db_is_down(client, monkeypatch, caplog):
    token = create_access_token(user_id="usr_fault_test", username="fault_tester")

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"Hello from Qwen3!"}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    from tests.backend.test_tts_service import FakeEngineForTests
    from backend.app.services.tts_service import tts_service
    monkeypatch.setattr(tts_service, "_engine_override", FakeEngineForTests())

    with patch(
        "backend.app.services.history_service.HistoryService.persist_turn_sync",
        side_effect=RuntimeError("Simulated DB Connection Refused (DB Down)"),
    ):
        with client.websocket_connect("/ws/speech") as ws:
            ws.send_json({
                "type": "start",
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
                "language_hint": "en",
                "auth_token": token,
            })
            ready = ws.receive_json()
            assert ready.get("type") == "ready"

            sample_path = Path("tests/samples/sample_chinese_speech.wav")
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()

            chunk_size = 1024
            for i in range(0, len(pcm_bytes), chunk_size):
                ws.send_bytes(pcm_bytes[i : i + chunk_size])

            ws.send_json({"type": "stop"})

            messages = []
            for _ in range(25):
                msg = ws.receive()
                if "text" in msg and msg["text"]:
                    data = json.loads(msg["text"])
                    messages.append(data)
                    if data.get("type") in ("llm_done", "error"):
                        break

            msg_types = [m.get("type") for m in messages]
            assert "speech_result" in msg_types, f"speech_result missing: {msg_types}"
            assert "llm_done" in msg_types, f"llm_done missing: {msg_types}"

            time.sleep(0.1)

            assert any(
                "Persistence failed" in record.message or "Simulated DB Connection Refused" in record.message
                for record in caplog.records
            ), "Expected DB persistence error to be logged"
