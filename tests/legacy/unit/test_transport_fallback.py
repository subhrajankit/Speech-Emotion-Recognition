import asyncio
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.config import settings
from src.backend.transport.webtransport import WebTransportManager, WebTransportSession, StreamTypes
from src.backend.transport.websocket_fallback import websocket_voice_endpoint
from src.backend.pipeline.orchestrator import VoicePipeline

@pytest.fixture(autouse=True)
def enable_mock_models():
    settings.MOCK_MODELS = True

def test_capabilities_endpoint():
    """
    Verifies that /api/transport/capabilities advertises both WebTransport and WebSocket
    with multi-stream specifications and datagram support.
    """
    client = TestClient(app)
    response = client.get("/api/transport/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["webtransport"] is True
    assert data["websocket"] is True
    assert "stream_a" in data["streams"]
    assert "stream_b" in data["streams"]
    assert "stream_c" in data["streams"]
    assert "stream_d" in data["streams"]
    assert data["datagrams"]["supported"] is True

def test_webtransport_descriptor_endpoint():
    """
    Verifies that /wt returns transport readiness status and capability details.
    """
    client = TestClient(app)
    response = client.get("/wt")
    assert response.status_code == 200
    data = response.json()
    assert data["transport"] == "webtransport"
    assert data["status"] == "ready"
    assert data["capabilities"]["webtransport"] is True

def test_websocket_fallback_independent():
    """
    Verifies that the extracted websocket_fallback.py operates independently
    as a complete, self-contained transport.
    """
    client = TestClient(app)
    with client.websocket_connect("/ws/voice") as ws:
        # Ping/pong over WebSocket
        ws.send_json({"type": "ping"})
        msg = ws.receive_json()
        assert msg["type"] == "pong"
        assert "conversation_id" in msg

        # Reset command
        ws.send_json({"action": "reset"})
        msg = ws.receive_json()
        assert msg["type"] == "status"
        assert "reset" in msg["message"].lower()

@pytest.mark.asyncio
async def test_webtransport_stream_demuxing():
    """
    Verifies WebTransport multi-stream separation:
    - Stream A: Mic audio chunks
    - Stream B: Control messages
    - Stream C: Transcripts and sentence events
    - Stream D: Binary TTS WAV frames
    - Datagrams: Emotion and latency telemetry
    """
    stream_c_messages = []
    stream_d_audio_chunks = []
    datagram_messages = []

    async def mock_stream_c_send(payload):
        stream_c_messages.append(payload)

    async def mock_stream_d_send(wav_bytes):
        stream_d_audio_chunks.append(wav_bytes)

    async def mock_datagram_send(payload):
        datagram_messages.append(payload)

    manager = WebTransportManager()
    session = manager.create_session(
        on_stream_c_send=mock_stream_c_send,
        on_stream_d_send=mock_stream_d_send,
        on_datagram_send=mock_datagram_send,
    )

    # 1. Test Stream B Control: Ping / Pong
    pong = await session.handle_stream_b_control({"action": "ping"})
    assert pong["type"] == "pong"
    assert pong["session_id"] == session.session_id

    # 2. Test Stream B Control: Reset
    reset_resp = await session.handle_stream_b_control({"action": "reset"})
    assert reset_resp["type"] == "status"
    assert "reset" in reset_resp["message"].lower()

    # 3. Test Stream A Audio ingestion
    mock_pcm = np.random.randint(-1000, 1000, 16000, dtype=np.int16).tobytes()
    res = await session.handle_stream_a_audio(mock_pcm)
    assert res is not None
    assert "status" in res

    # 4. Trigger end-of-utterance via Stream B
    flush_resp = await session.handle_stream_b_control({"action": "end-of-utterance"})
    assert flush_resp["type"] == "status"

    # Wait briefly for async generator pipeline
    await asyncio.sleep(0.1)

    # Assert Stream C received transcript & pipeline events
    c_types = [m.get("type") for m in stream_c_messages]
    assert "status" in c_types
    assert "llm_start" in c_types
    assert "sentence_start" in c_types
    assert "sentence_end" in c_types
    assert "turn_complete" in c_types

    # Assert Stream D received binary WAV frames
    assert len(stream_d_audio_chunks) >= 1
    assert len(stream_d_audio_chunks[0]) > 44
    assert stream_d_audio_chunks[0][:4] == b"RIFF"

    # Assert Datagrams received emotion updates
    assert len(datagram_messages) >= 1
    assert datagram_messages[0]["type"] == "emotion_update"
    assert "emotion" in datagram_messages[0]

    # Test Datagram Inbound
    client_datagram = json.dumps({"type": "heartbeat", "rtt_ms": 12.5}).encode("utf-8")
    dg_in_res = await session.handle_datagram(client_datagram)
    assert dg_in_res is not None
    assert dg_in_res["status"] == "received"
    assert dg_in_res["data"]["type"] == "heartbeat"

    # 5. Session Cleanup
    manager.remove_session(session.session_id)
    assert manager.get_session(session.session_id) is None
    assert session.is_active is False
