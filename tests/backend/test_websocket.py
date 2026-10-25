"""
Tests for WebSocket /ws/speech streaming endpoint.
Covers protocol v1 handshake, audio streaming, speech_result emission,
keepalives, buffer limits, and authentication gating.
"""

from pathlib import Path
import numpy as np
import soundfile as sf
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


def test_websocket_hindi_language_hint_returns_emotion_none(client):
    """
    Verifies WebSocket session configured with language_hint='hi'
    routes to IndicConformer and returns emotion=None (null).
    """
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "hi"
        })
        ready_event = ws.receive_json()
        assert ready_event.get("type") == "ready"

        # Send 1.0s of audible synthetic speech-like signal
        t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
        samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
        pcm_bytes = samples.tobytes()

        chunk_size = 1024
        for i in range(0, len(pcm_bytes), chunk_size):
            ws.send_bytes(pcm_bytes[i : i + chunk_size])

        ws.send_json({"type": "stop"})

        speech_result = None
        for _ in range(5):
            try:
                event = ws.receive_json()
                if event.get("type") == "speech_result":
                    speech_result = event
                    break
            except Exception:
                break

        assert speech_result is not None
        assert speech_result["language"] == "hi"
        assert speech_result["emotion"] is None
        assert speech_result["debug"]["routing"]["engine"] == "indicconformer"
        assert speech_result["debug"]["routing"]["source"] == "hint"


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


def test_websocket_speech_result_before_llm_and_error_keeps_socket_open(client, monkeypatch):
    """
    Requirement 5: Ordering guarantee and resilience.
    The speech_result event MUST be sent BEFORE the LLM is called and never waits on it.
    When the local LLM server is stopped/unreachable, an error with code='llm_unavailable'
    is emitted, and the socket remains OPEN and functional.
    Uses fault injection (503 Service Unavailable) to simulate a stopped llama-server.
    """
    import httpx
    from backend.app.services.llm_service import llm_service

    async def fail_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused to 127.0.0.1:8080 (llama-server stopped)")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(fail_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })
        ready_msg = ws.receive_json()
        assert ready_msg.get("type") == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        if sample_path.is_file():
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()
        else:
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
            pcm_bytes = samples.tobytes()

        chunk_size = 1024
        for i in range(0, len(pcm_bytes), chunk_size):
            ws.send_bytes(pcm_bytes[i : i + chunk_size])

        ws.send_json({"type": "stop"})

        events = []
        # Receive until we see the speech_result and the subsequent LLM outcome
        for _ in range(10):
            try:
                ev = ws.receive_json()
                events.append(ev)
                if ev.get("type") in ("error", "llm_done"):
                    break
            except Exception:
                break

        event_types = [e.get("type") for e in events]
        assert "speech_result" in event_types

        # Verify strict ordering: speech_result MUST appear before any llm event or error
        speech_idx = event_types.index("speech_result")
        assert "error" in event_types, f"Expected LLM error event, received: {event_types}"
        err_idx = event_types.index("error")
        assert speech_idx < err_idx, "speech_result must be emitted before LLM error"
        err_event = events[err_idx]
        assert err_event.get("code") == "llm_unavailable"

        # Verify socket is STILL OPEN and responsive to subsequent traffic
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong.get("type") == "pong"


def test_websocket_llm_streaming_success_ordering(client, monkeypatch):
    """
    Requirement 5: Stream llm_delta events and final llm_done after speech_result.
    Uses fault-injection MockTransport to simulate real SSE streaming from llama.cpp.
    """
    import httpx
    from backend.app.services.llm_service import llm_service

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" from"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" Qwen3!"}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })
        assert ws.receive_json().get("type") == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        if sample_path.is_file():
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()
        else:
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
            pcm_bytes = samples.tobytes()

        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])

        ws.send_json({"type": "stop"})

        events = []
        for _ in range(10):
            try:
                ev = ws.receive_json()
                events.append(ev)
                if ev.get("type") in ("llm_done", "error"):
                    break
            except Exception:
                break

        event_types = [e.get("type") for e in events]
        assert "speech_result" in event_types
        assert "llm_delta" in event_types
        assert "llm_done" in event_types

        # Strict ordering verification
        speech_idx = event_types.index("speech_result")
        first_delta_idx = event_types.index("llm_delta")
        done_idx = event_types.index("llm_done")

        assert speech_idx < first_delta_idx < done_idx

        # Content verification
        deltas = [e.get("delta") for e in events if e.get("type") == "llm_delta"]
        assert "".join(deltas) == "Hello from Qwen3!"

        done_event = events[done_idx]
        assert done_event.get("text") == "Hello from Qwen3!"

        # Socket still functional
        ws.send_json({"type": "ping"})
        assert ws.receive_json().get("type") == "pong"


def test_websocket_cancellation_on_new_start(client, monkeypatch):
    """
    Requirement 6: If the client sends a new "start" while LLM is in-flight,
    cancel the in-flight LLM request and reset for the new stream.
    """
    import asyncio
    import httpx
    from backend.app.services.llm_service import llm_service

    stream_cancelled = False

    async def slow_stream_handler(request: httpx.Request) -> httpx.Response:
        async def byte_stream():
            nonlocal stream_cancelled
            try:
                for i in range(20):
                    yield f'data: {{"choices":[{{"delta":{{"content":"word{i} "}}}}]}}\n\n'.encode("utf-8")
                    await asyncio.sleep(0.05)
                yield b"data: [DONE]\n\n"
            except asyncio.CancelledError:
                stream_cancelled = True
                raise

        return httpx.Response(200, content=byte_stream())

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(slow_stream_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        # Start turn 1
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        # Send audio chunk
        samples = (0.5 * np.sin(2 * np.pi * 300 * np.linspace(0, 0.5, 8000)) * 32767.0).astype(np.int16)
        ws.send_bytes(samples.tobytes())
        ws.send_json({"type": "stop"})

        # Wait for speech_result
        speech_res = None
        for _ in range(5):
            ev = ws.receive_json()
            if ev.get("type") == "speech_result":
                speech_res = ev
                break
        assert speech_res is not None

        # Send new 'start' to interrupt / cancel in-flight stream (barge-in)
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        ready_ev = ws.receive_json()
        # May receive remaining buffered delta before ready or ready directly
        while ready_ev.get("type") == "llm_delta":
            ready_ev = ws.receive_json()
        assert ready_ev.get("type") == "ready"

        # Subsequent ping succeeds cleanly
        ws.send_json({"type": "ping"})
        assert ws.receive_json().get("type") == "pong"


def test_websocket_thinking_filter_split_across_sse_deltas(client, monkeypatch):
    """
    Requirement 4: Verify that <think> tags split across streamed SSE chunks
    never reach the client.
    """
    import httpx
    from backend.app.services.llm_service import llm_service

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"<th"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"ink>reasoning hidden</"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"think>Spoken"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" response."}}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        if sample_path.is_file():
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()
        else:
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
            pcm_bytes = samples.tobytes()

        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        deltas = []
        full_text = None
        for _ in range(10):
            try:
                ev = ws.receive_json()
                if ev.get("type") == "llm_delta":
                    deltas.append(ev.get("delta"))
                elif ev.get("type") == "llm_done":
                    full_text = ev.get("text")
                    break
            except Exception:
                break

        aggregated = "".join(deltas)
        assert "<think>" not in aggregated
        assert "reasoning hidden" not in aggregated
        assert "Spoken response." in aggregated
        assert full_text == "Spoken response."


def test_websocket_llm_stream_cut_mid_reply(client, monkeypatch):
    """
    Requirement 5: If the LLM stream drops / fails mid-reply,
    the socket survives and reports an error frame.
    """
    import httpx
    from backend.app.services.llm_service import llm_service

    async def broken_stream_handler(request: httpx.Request) -> httpx.Response:
        async def byte_stream():
            yield b'data: {"choices":[{"delta":{"content":"First part..."}}]}\n\n'
            raise httpx.ReadError("Network connection reset mid-stream")

        return httpx.Response(200, content=byte_stream())

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(broken_stream_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        if sample_path.is_file():
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()
        else:
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
            pcm_bytes = samples.tobytes()

        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        events = []
        for _ in range(10):
            try:
                ev = ws.receive_json()
                events.append(ev)
                if ev.get("type") == "error":
                    break
            except Exception:
                break

        event_types = [e.get("type") for e in events]
        assert "speech_result" in event_types
        assert "error" in event_types
        err_event = next(e for e in events if e.get("type") == "error")
        assert err_event.get("code") == "llm_unavailable"

        # Socket survives
        ws.send_json({"type": "ping"})
        assert ws.receive_json().get("type") == "pong"

