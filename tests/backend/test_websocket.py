"""
Tests for WebSocket /ws/speech streaming endpoint.
Covers protocol v1 handshake, audio streaming, speech_result emission,
keepalives, buffer limits, and authentication gating.
"""

import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.core.config import settings
from backend.app.core.security import create_access_token


def test_websocket_start_audio_stop_sequence(client):
    """
    Verifies full streaming lifecycle:
    start -> ready -> audio -> stop -> speech_result
    """
    with client.websocket_connect("/ws/speech") as ws:
        # 1. Send start
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })

        # 2. Expect ready
        ready_event = ws.receive_json()
        assert ready_event.get("type") == "ready"

        # 3. Send 1.0s of audible synthetic speech-like signal (16kHz PCM16)
        t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
        samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
        pcm_bytes = samples.tobytes()

        # Send in 512-sample (1024-byte) chunks
        chunk_size = 1024
        for i in range(0, len(pcm_bytes), chunk_size):
            ws.send_bytes(pcm_bytes[i : i + chunk_size])

        # 4. Send stop
        ws.send_json({"type": "stop"})

        # 5. Receive events until speech_result
        received_types = []
        speech_result = None

        for _ in range(5):
            try:
                event = ws.receive_json()
                evt_type = event.get("type")
                received_types.append(evt_type)
                if evt_type == "speech_result":
                    speech_result = event
                    break
            except Exception:
                break

        assert "speech_result" in received_types
        assert speech_result is not None
        assert "transcript" in speech_result
        assert "language" in speech_result
        assert "emotion" in speech_result
        assert "processing_time_ms" in speech_result


def test_websocket_keepalive_ping_pong(client):
    """Verifies ping -> pong keepalive."""
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "ping"})
        response = ws.receive_json()
        assert response.get("type") == "pong"


def test_websocket_unknown_and_reserved_messages_ignored(client):
    """Verifies reserved (llm_delta, tts_chunk) and unknown frames are safely ignored."""
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start"})
        assert ws.receive_json().get("type") == "ready"

        # Send reserved types
        ws.send_json({"type": "llm_delta", "text": "streaming..."})
        ws.send_json({"type": "tts_chunk", "index": 1})
        ws.send_json({"type": "custom_unknown_action"})

        # Send ping to verify socket is still responsive
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong.get("type") == "pong"


def test_websocket_audio_before_start_returns_error(client):
    """Verifies sending audio before start emits error frame."""
    with client.websocket_connect("/ws/speech") as ws:
        dummy_pcm = b"\x00" * 1024
        ws.send_bytes(dummy_pcm)

        err = ws.receive_json()
        assert err.get("type") == "error"
        assert err.get("code") == "NOT_STARTED"


def test_websocket_buffer_limit_enforcement(client):
    """Verifies that exceeding buffer limit emits BUFFER_OVERFLOW error."""
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start"})
        assert ws.receive_json().get("type") == "ready"

        # Send chunk exceeding WS_MAX_BUFFER_BYTES
        giant_chunk = b"\x00" * (settings.WS_MAX_BUFFER_BYTES + 1024)
        ws.send_bytes(giant_chunk)

        err = ws.receive_json()
        assert err.get("type") == "error"
        assert err.get("code") == "BUFFER_OVERFLOW"


def test_websocket_auth_required_rejection(client):
    """Verifies that when AUTH_REQUIRED=true, unauthenticated sockets are rejected."""
    settings.AUTH_REQUIRED = True
    try:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/speech"):
                pass
        assert excinfo.value.code == 1008
    finally:
        settings.AUTH_REQUIRED = False


def test_websocket_auth_required_accepted_with_token(client):
    """Verifies that valid JWT token permits connection when AUTH_REQUIRED=true."""
    settings.AUTH_REQUIRED = True
    try:
        token = create_access_token(session_id="test_session_123")
        with client.websocket_connect(f"/ws/speech?token={token}") as ws:
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong.get("type") == "pong"
    finally:
        settings.AUTH_REQUIRED = False
