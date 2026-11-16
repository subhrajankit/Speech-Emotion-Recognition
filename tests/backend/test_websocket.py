"""
Tests for WebSocket /ws/speech streaming endpoint.
Covers protocol v1 handshake, audio streaming, speech_result emission,
keepalives, buffer limits, and authentication gating.
"""

import json
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


def test_websocket_hindi_language_hint_returns_emotion_none(client, monkeypatch):
    """
    Verifies WebSocket session configured with language_hint='hi'
    routes to IndicConformer and returns emotion=None (null).
    """
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", False)
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
    """Verifies that when AUTH_REQUIRED=true, start frames without valid auth_token are rejected with 1008."""
    settings.AUTH_REQUIRED = True
    try:
        with client.websocket_connect("/ws/speech") as ws:
            ws.send_json({
                "type": "start",
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
                "language_hint": "en",
            })
            err = ws.receive_json()
            assert err.get("type") == "error"
            assert err.get("code") == "AUTH_REQUIRED"
            with pytest.raises(WebSocketDisconnect) as excinfo:
                ws.receive_json()
            assert excinfo.value.code == 1008
    finally:
        settings.AUTH_REQUIRED = False


def test_websocket_auth_required_accepted_with_token(client):
    """Verifies that valid JWT auth_token in start frame permits session when AUTH_REQUIRED=true."""
    settings.AUTH_REQUIRED = True
    try:
        from backend.app.core.database import get_db_session
        from backend.app.core.security import hash_password
        from backend.app.models.user import User

        with get_db_session() as db:
            if db.query(User).filter(User.id == "test_user_123").first() is None:
                db.add(User(
                    id="test_user_123",
                    username="testuser",
                    hashed_password=hash_password("test_password_123"),
                    is_active=True,
                ))
                db.commit()

        token = create_access_token(user_id="test_user_123", username="testuser")
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


def test_websocket_handles_llm_bad_response_500_peg_native_without_disconnecting(client, monkeypatch):
    """
    Phase 8i Item 2a: When llama-server returns HTTP 500 peg-native parsing error,
    verify that the turn ends with {"type":"error","code":"llm_bad_response"}
    and the WebSocket connection remains OPEN and functional.
    """
    import httpx
    import json
    from backend.app.services.llm_service import llm_service

    error_body = json.dumps({
        "error": {
            "code": 500,
            "message": "The model produced output that does not match the expected peg-native format",
            "type": "server_error"
        }
    })

    async def peg_native_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=error_body, headers={"content-type": "application/json"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(peg_native_handler))
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

        assert "error" in event_types, f"Expected error event, got {event_types}"
        err_idx = event_types.index("error")
        err_event = events[err_idx]
        assert err_event.get("code") == "llm_bad_response"

        # Verify socket is STILL OPEN and responsive
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
        while ready_ev.get("type") in ("llm_delta", "status"):
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


def test_websocket_tts_streaming_order(client, monkeypatch):
    """
    Acceptance Criteria:
    Verifies full event sequence:
    speech_result -> llm_delta... -> llm_done -> tts_chunk (JSON) -> tts_chunk (binary) -> tts_done.
    Uses FakeEngineForTests for test-only isolated audio generation.
    """
    import httpx
    from backend.app.services.llm_service import llm_service
    from backend.app.services.tts_service import tts_service
    from tests.backend.test_tts_service import FakeEngineForTests

    sse_content = (
        'data: {"choices":[{"delta":{"content":"First sentence. "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"Second sentence."}}]}\n\n'
        'data: [DONE]\n\n'
    )

    async def sse_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_content)

    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    monkeypatch.setattr(llm_service, "_custom_client", httpx.AsyncClient(transport=httpx.MockTransport(sse_handler)))
    monkeypatch.setattr(tts_service, "_engine_override", FakeEngineForTests())

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        if sample_path.is_file():
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()
        else:
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            pcm_bytes = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16).tobytes()

        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        received_events = []
        binary_frames = []

        # Read frames until tts_done is encountered
        for _ in range(25):
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                received_events.append(data)
                if data.get("type") == "tts_done":
                    break
            elif "bytes" in msg and msg["bytes"]:
                binary_frames.append(msg["bytes"])

        types = [e.get("type") for e in received_events]
        assert "speech_result" in types
        assert "llm_done" in types
        assert "tts_chunk" in types
        assert "tts_done" in types

        # Check strict ordering
        speech_idx = types.index("speech_result")
        llm_idx = types.index("llm_done")
        tts_first_idx = types.index("tts_chunk")
        tts_done_idx = types.index("tts_done")

        assert speech_idx < llm_idx < tts_first_idx < tts_done_idx

        # Binary WAV frames must accompany tts_chunk
        assert len(binary_frames) == 2
        for b in binary_frames:
            assert b[:4] == b"RIFF"


def test_websocket_tts_failure_isolation(client, monkeypatch):
    """
    Acceptance Criteria: Failure-injection test.
    TTS fails or runs out of memory, yet speech_result and llm_done are still delivered.
    Client receives {"type": "error", "code": "tts_unavailable"}.
    Socket remains open and responsive to subsequent pings.
    """
    import httpx
    from backend.app.services.llm_service import llm_service
    from backend.app.services.tts_service import tts_service, TTSError
    from tests.backend.test_tts_service import FakeEngineForTests

    sse_content = (
        'data: {"choices":[{"delta":{"content":"Hello world."}}]}\n\n'
        'data: [DONE]\n\n'
    )

    async def sse_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_content)

    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    monkeypatch.setattr(llm_service, "_custom_client", httpx.AsyncClient(transport=httpx.MockTransport(sse_handler)))
    monkeypatch.setattr(tts_service, "_engine_override", FakeEngineForTests(
        fail_with=TTSError("Simulated CUDA Out of Memory in TTS")
    ))

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        sample_path = Path("tests/samples/sample_chinese_speech.wav")
        if sample_path.is_file():
            data, _ = sf.read(str(sample_path), dtype="int16")
            pcm_bytes = data[:32000].tobytes()
        else:
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            pcm_bytes = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16).tobytes()

        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})


        received_events = []
        for _ in range(15):
            try:
                ev = ws.receive_json()
                received_events.append(ev)
                if ev.get("type") == "error" and ev.get("code") == "tts_unavailable":
                    break
            except Exception:
                break

        types = [e.get("type") for e in received_events]
        assert "speech_result" in types, "speech_result MUST still be delivered"
        assert "llm_done" in types, "llm_done MUST still be delivered"
        assert "error" in types

        err_event = next(e for e in received_events if e.get("type") == "error")
        assert err_event.get("code") == "tts_unavailable"

        # Socket remains open and healthy
        ws.send_json({"type": "ping"})
        assert ws.receive_json().get("type") == "pong"


def test_websocket_emits_error_when_engine_raises(client, monkeypatch):
    """
    Confirms that when the speech engine raises an exception during transcription,
    the server sends an explicit {"type": "error", "code": "INFERENCE_ERROR"}
    event over the WebSocket before any disconnect or close occurs.
    """
    from backend.app.services.speech_service import speech_service

    async def mock_failing_transcribe(*args, **kwargs):
        raise RuntimeError("Simulated speech engine failure: DLL load failed")

    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", mock_failing_transcribe)

    with client.websocket_connect("/ws/speech") as ws:
        # 1. Start session
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })
        ready_evt = ws.receive_json()
        assert ready_evt.get("type") == "ready"

        # 2. Stream audio and stop to flush
        t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
        pcm_bytes = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16).tobytes()
        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        # 3. Receive events; must receive error event with code INFERENCE_ERROR
        received_events = []
        for _ in range(10):
            try:
                ev = ws.receive_json()
                received_events.append(ev)
                if ev.get("type") == "error":
                    break
            except Exception:
                break

        types = [e.get("type") for e in received_events]
        assert "error" in types, f"Server must emit error event before close; got events: {types}"
        err = next(e for e in received_events if e.get("type") == "error")
        assert err.get("code") == "INFERENCE_ERROR"
        assert "Simulated speech engine failure" in err.get("message", "")


def test_websocket_first_turn_lazy_load_status_events(client, monkeypatch):
    """
    Item 6b: First-turn lazy load status notifications.
    When an engine is lazy-loaded on the first turn:
    1. Emits {"type": "status", "state": "loading_model", "engine": "..."}
    2. Model loads
    3. Emits {"type": "status", "state": "model_ready", "engine": "..."}
    4. Speech result emitted.
    On subsequent turns, no status events are emitted because model is already resident.
    """
    from tests.test_doubles import SlowLoadingFakeEngine
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service
    import httpx

    mock_llm_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text='data: [DONE]\n\n'))
    )
    monkeypatch.setattr(llm_service, "_custom_client", mock_llm_client)

    slow_engine = SlowLoadingFakeEngine(load_delay=0.01)
    monkeypatch.setattr(speech_service, "_sensevoice", slow_engine)
    monkeypatch.setattr(speech_service, "_engine", slow_engine)

    with client.websocket_connect("/ws/speech") as ws:
        # --- Turn 1: First turn with lazy loading ---
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })
        assert ws.receive_json().get("type") == "ready"

        # Stream audio and stop
        t = np.linspace(0, 0.5, 8000, endpoint=False, dtype=np.float32)
        pcm_bytes = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16).tobytes()
        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        events_turn1 = []
        for _ in range(20):
            try:
                ev = ws.receive_json()
                events_turn1.append(ev)
                if ev.get("type") in ("llm_done", "error"):
                    break
            except Exception:
                break

        types1 = [e.get("type") for e in events_turn1]
        assert "status" in types1, f"Expected status events, got {types1}"
        assert "speech_result" in types1

        # Check status event contents and order
        status_events = [e for e in events_turn1 if e.get("type") == "status" and "state" in e]
        assert len(status_events) == 2
        assert status_events[0] == {"type": "status", "state": "loading_model", "engine": "sensevoice"}
        assert status_events[1] == {"type": "status", "state": "model_ready", "engine": "sensevoice"}

        loading_idx = events_turn1.index(status_events[0])
        ready_idx = events_turn1.index(status_events[1])
        speech_idx = events_turn1.index(next(e for e in events_turn1 if e.get("type") == "speech_result"))
        assert loading_idx < ready_idx < speech_idx

        # --- Turn 2: Subsequent turn (engine resident) ---
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })
        assert ws.receive_json().get("type") == "ready"

        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        events_turn2 = []
        for _ in range(20):
            try:
                ev = ws.receive_json()
                events_turn2.append(ev)
                if ev.get("type") in ("llm_done", "error"):
                    break
            except Exception:
                break

        types2 = [e.get("type") for e in events_turn2]
        engine_status2 = [e for e in events_turn2 if e.get("type") == "status" and "state" in e]
        assert len(engine_status2) == 0, f"Turn 2 must NOT emit model status events when model is loaded; got {engine_status2}"
        assert "speech_result" in types2


def test_preload_default_engine_config(monkeypatch):
    """
    Confirms PRELOAD_DEFAULT_ENGINE config preloads the default engine at startup.
    """
    from tests.test_doubles import SlowLoadingFakeEngine
    from backend.app.services.speech_service import SpeechService
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "PRELOAD_DEFAULT_ENGINE", True)
    svc = SpeechService()
    fake = SlowLoadingFakeEngine(load_delay=0.0)
    svc._sensevoice = fake
    svc._engine = fake

    assert not fake.is_loaded
    svc.initialize()
    assert fake.is_loaded
    assert fake.load_count == 1


def test_websocket_slow_loading_engine_answers_pings_and_delivers_status_events(client, monkeypatch):
    """
    Phase 10b Item 1: Prove with a slow-loading double that blocks its worker thread
    that WebSocket keepalive pings are answered immediately and status events arrive in order
    without connection drop.
    """
    from tests.test_doubles import SlowLoadingFakeEngine
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service
    import httpx

    mock_llm_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text='data: [DONE]\n\n'))
    )
    monkeypatch.setattr(llm_service, "_custom_client", mock_llm_client)

    # SlowLoadingFakeEngine with 0.5s blocking delay in load()
    slow_engine = SlowLoadingFakeEngine(load_delay=0.5)
    monkeypatch.setattr(speech_service, "_sensevoice", slow_engine)
    monkeypatch.setattr(speech_service, "_engine", slow_engine)

    with client.websocket_connect("/ws/speech") as ws:
        # 1. Start session
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        })
        ready_evt = ws.receive_json()
        assert ready_evt.get("type") == "ready"

        # 2. Stream audio and send stop
        t = np.linspace(0, 0.5, 8000, endpoint=False, dtype=np.float32)
        pcm_bytes = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16).tobytes()
        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i : i + 1024])
        ws.send_json({"type": "stop"})

        # 3. Send keepalive pings while worker thread is blocked in load()
        ws.send_json({"type": "ping"})
        ws.send_json({"type": "ping"})

        # 4. Drain all events
        events = []
        for _ in range(25):
            try:
                ev = ws.receive_json()
                events.append(ev)
                if ev.get("type") in ("llm_done", "error"):
                    break
            except Exception:
                break

        # 5. Verify pongs were returned and status events arrived
        pong_events = [e for e in events if e.get("type") == "pong"]
        status_events = [e for e in events if e.get("type") == "status" and "state" in e]
        speech_results = [e for e in events if e.get("type") == "speech_result"]

        assert len(pong_events) == 2, f"Expected 2 pongs, got {pong_events}"
        assert len(status_events) == 2, f"Expected 2 engine status events, got {status_events}"
        assert status_events[0] == {"type": "status", "state": "loading_model", "engine": "sensevoice"}
        assert status_events[1] == {"type": "status", "state": "model_ready", "engine": "sensevoice"}
        assert len(speech_results) == 1, "Expected speech_result"







def test_websocket_rejects_jwt_with_nonexistent_user(client):
    """
    A correctly signed JWT whose 'sub' references no users row must be
    rejected with AUTH_FAILED and must not create sessions/history rows.
    """
    import uuid
    from backend.app.core.database import get_db_session
    from backend.app.models.session import Session as DBSession
    from backend.app.models.prediction import Prediction

    ghost_id = f"usr_ghost_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_ghost_{uuid.uuid4().hex[:8]}"
    token = create_access_token(user_id=ghost_id, username="ghost")

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "session_id": sess_id,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
            "auth_token": token,
        })
        error = ws.receive_json()
        assert error.get("type") == "error"
        assert error.get("code") == "AUTH_FAILED"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    with get_db_session() as db:
        assert db.query(DBSession).filter(DBSession.id == sess_id).count() == 0
        assert db.query(DBSession).filter(DBSession.user_id == ghost_id).count() == 0
        assert db.query(Prediction).filter(Prediction.session_id == sess_id).count() == 0


def test_websocket_accepts_jwt_for_existing_user(client):
    """A valid JWT for an existing user passes the subject check and reaches ready."""
    import uuid
    from backend.app.core.database import get_db_session
    from backend.app.core.security import hash_password
    from backend.app.models.user import User

    user_id = f"usr_ws_{uuid.uuid4().hex[:8]}"
    with get_db_session() as db:
        db.add(User(
            id=user_id,
            username=f"ws_{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("test_password_123"),
            is_active=True,
        ))
        db.commit()

    token = create_access_token(user_id=user_id, username="ws_user")
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "session_id": f"sess_ws_{uuid.uuid4().hex[:8]}",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
            "auth_token": token,
        })
        assert ws.receive_json().get("type") == "ready"


def test_websocket_cannot_append_history_to_foreign_session(client):
    """
    Cross-user session isolation: user A supplying user B's session_id in the
    WS start frame may receive a normal speech_result, but history_service's
    ownership guard must refuse persistence — B's session and its records
    remain byte-for-byte unchanged.
    """
    import uuid
    from datetime import datetime, timezone
    from backend.app.core.database import get_db_session
    from backend.app.core.security import hash_password
    from backend.app.models.user import User
    from backend.app.models.session import Session as DBSession
    from backend.app.models.prediction import Prediction
    from backend.app.models.transcript import Transcript
    from backend.app.models.emotion import EmotionResult
    from backend.app.models.message import Message

    suffix = uuid.uuid4().hex[:8]
    user_a_id = f"usr_iso_a_{suffix}"
    user_b_id = f"usr_iso_b_{suffix}"
    sess_b_id = f"sess_iso_b_{suffix}"

    with get_db_session() as db:
        for uid, uname in ((user_a_id, "iso_a"), (user_b_id, "iso_b")):
            db.add(User(
                id=uid, username=f"{uname}_{suffix}",
                hashed_password=hash_password("test_password_123"),
                is_active=True,
            ))
        pred_b = Prediction(
            id=str(uuid.uuid4()), session_id=sess_b_id,
            processing_time_ms=123.0, created_at=datetime.now(timezone.utc),
        )
        db.add(DBSession(
            id=sess_b_id, user_id=user_b_id, primary_language="en",
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        ))
        db.add(pred_b)
        db.flush()
        db.add(Transcript(
            id=str(uuid.uuid4()), prediction_id=pred_b.id, session_id=sess_b_id,
            text="B private turn", language="en",
        ))
        db.add(EmotionResult(
            id=str(uuid.uuid4()), prediction_id=pred_b.id, session_id=sess_b_id,
            primary_emotion="neutral",
        ))
        db.add(Message(
            id=str(uuid.uuid4()), session_id=sess_b_id, prediction_id=pred_b.id,
            role="assistant", text="B reply",
        ))
        db.commit()
        pred_b_id = pred_b.id

    def _counts() -> dict:
        with get_db_session() as db:
            return {
                "sessions": db.query(DBSession).filter(DBSession.id == sess_b_id).count(),
                "predictions": db.query(Prediction).filter(Prediction.session_id == sess_b_id).count(),
                "transcripts": db.query(Transcript).filter(Transcript.session_id == sess_b_id).count(),
                "emotion_results": db.query(EmotionResult).filter(EmotionResult.session_id == sess_b_id).count(),
                "messages": db.query(Message).filter(Message.session_id == sess_b_id).count(),
            }

    baseline = _counts()
    assert baseline == {"sessions": 1, "predictions": 1, "transcripts": 1,
                        "emotion_results": 1, "messages": 1}

    token_a = create_access_token(user_id=user_a_id, username="iso_a")
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "session_id": sess_b_id,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
            "auth_token": token_a,
        })
        assert ws.receive_json().get("type") == "ready"

        t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
        samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
        pcm_bytes = samples.tobytes()
        for i in range(0, len(pcm_bytes), 1024):
            ws.send_bytes(pcm_bytes[i:i + 1024])
        ws.send_json({"type": "stop"})

        got_speech_result = False
        for _ in range(10):
            ev = ws.receive_json()
            if ev.get("type") == "speech_result":
                got_speech_result = True
                break
        assert got_speech_result, "Expected normal speech_result despite foreign session_id"

    assert _counts() == baseline, "User B's session history was mutated by user A's turn"

    with get_db_session() as db:
        sess = db.query(DBSession).filter(DBSession.id == sess_b_id).one()
        assert sess.user_id == user_b_id
        assert db.query(Prediction).filter(
            Prediction.session_id == sess_b_id, Prediction.id != pred_b_id
        ).count() == 0


def _silent_pcm16_bytes(duration_s: float = 1.0) -> bytes:
    """Digital-silence PCM16 mono 16kHz payload."""
    return b"\x00\x00" * int(16000 * duration_s)


def _sine_pcm16_bytes(duration_s: float = 1.0) -> bytes:
    t = np.linspace(0, duration_s, int(16000 * duration_s), endpoint=False, dtype=np.float32)
    samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
    return samples.tobytes()


def _send_start(ws, language_hint="en"):
    ws.send_json({
        "type": "start",
        "sample_rate": 16000,
        "encoding": "pcm_s16le",
        "language_hint": language_hint,
    })
    assert ws.receive_json().get("type") == "ready"


def _send_pcm(ws, pcm_bytes: bytes, chunk_size: int = 1024):
    for i in range(0, len(pcm_bytes), chunk_size):
        ws.send_bytes(pcm_bytes[i:i + chunk_size])


def _drain_events(ws, max_events: int = 12, stop_types=("speech_result", "llm_done", "error")):
    events = []
    for _ in range(max_events):
        try:
            ev = ws.receive_json()
        except Exception:
            break
        events.append(ev)
        if ev.get("type") in stop_types:
            break
    return events


def test_websocket_silent_stop_emits_no_speech_status(client, monkeypatch):
    """
    Chunk 9.3C: a stop-flush containing only silence must NOT emit
    speech_result, must NOT start an LLM turn, and must emit a non-error
    status event with state 'no_speech'. The session stays usable.
    """
    import httpx
    from ai.inference.types import SpeechResult
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service

    async def mock_no_speech_transcribe(*args, **kwargs):
        return SpeechResult(
            transcript="",
            language="unknown",
            emotion=None,
            confidence=None,
            processing_time_ms=5,
            model_version="fake-no-speech",
            debug={"status": "no_speech_detected", "vad_has_speech": False},
        )

    llm_calls = []

    async def counting_llm_handler(request: httpx.Request) -> httpx.Response:
        llm_calls.append(request)
        return httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n')

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(counting_llm_handler))
    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", mock_no_speech_transcribe)
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    with client.websocket_connect("/ws/speech") as ws:
        _send_start(ws)
        _send_pcm(ws, _silent_pcm16_bytes(1.0))
        ws.send_json({"type": "stop"})

        events = _drain_events(ws, stop_types=("status", "speech_result", "error", "llm_done"))
        types = [e.get("type") for e in events]

        assert "speech_result" not in types, f"no-speech must not emit speech_result: {events}"
        assert "llm_done" not in types and "llm_delta" not in types
        assert "error" not in types, f"ordinary silence must not be an error: {events}"

        no_speech = next(
            (e for e in events if e.get("type") == "status" and e.get("state") == "no_speech"),
            None,
        )
        assert no_speech is not None, f"expected status no_speech event, got {events}"
        assert no_speech.get("message")

        # LLM was never invoked for the silent turn.
        assert llm_calls == [], "LLM must not run for confirmed no-speech"

        # Recording session remains usable: ping/pong and a fresh start cycle.
        ws.send_json({"type": "ping"})
        assert ws.receive_json().get("type") == "pong"

        _send_start(ws)
        _send_pcm(ws, _sine_pcm16_bytes(0.5))
        ws.send_json({"type": "stop"})
        # Second cycle still produces no_speech (mock always returns empty) —
        # the important part is the socket accepted the new start frame.
        events2 = _drain_events(ws, stop_types=("status", "speech_result", "error"))
        assert any(e.get("type") == "status" and e.get("state") == "no_speech" for e in events2)


def test_websocket_no_speech_does_not_consume_rate_limit_slot(client, monkeypatch):
    """
    Chunk 9.3C: the pre-inference rate-limit reservation is refunded when
    inference confirms no speech, so a subsequent genuine utterance within
    the same minute is not rejected.
    """
    import httpx
    from ai.inference.types import SpeechResult
    from backend.app.core.rate_limiter import session_rate_limiter
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service

    call_count = {"n": 0}

    async def mock_transcribe(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return SpeechResult(
                transcript="",
                language="unknown",
                emotion=None,
                confidence=None,
                processing_time_ms=5,
                model_version="fake-no-speech",
                debug={"status": "no_speech_detected"},
            )
        return SpeechResult(
            transcript="Hello there, this is real speech.",
            language="en",
            emotion="neutral",
            confidence=None,
            processing_time_ms=5,
            model_version="fake-speech",
        )

    async def ok_llm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n',
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(ok_llm_handler))
    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", mock_transcribe)
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)
    monkeypatch.setattr(session_rate_limiter, "max_utterances", 1)

    with client.websocket_connect("/ws/speech") as ws:
        # Cycle 1: silent stop -> no_speech (slot must be refunded).
        _send_start(ws)
        _send_pcm(ws, _silent_pcm16_bytes(1.0))
        ws.send_json({"type": "stop"})
        events1 = _drain_events(ws, stop_types=("status", "speech_result", "error"))
        assert any(e.get("type") == "status" and e.get("state") == "no_speech" for e in events1)
        assert not any(e.get("code") == "RATE_LIMIT_EXCEEDED" for e in events1)

        # Cycle 2: genuine utterance on the SAME session_id bucket. With only
        # 1 utterance/min allowed, this succeeds only if cycle 1 was refunded.
        _send_start(ws)
        _send_pcm(ws, _sine_pcm16_bytes(0.5))
        ws.send_json({"type": "stop"})
        events2 = _drain_events(ws, stop_types=("speech_result", "error"))
        types2 = [e.get("type") for e in events2]

        assert "RATE_LIMIT_EXCEEDED" not in [e.get("code") for e in events2], (
            f"refunded no-speech slot was still consumed: {events2}"
        )
        assert "speech_result" in types2, f"expected normal speech_result, got {events2}"
        sr = next(e for e in events2 if e.get("type") == "speech_result")
        assert sr.get("transcript") == "Hello there, this is real speech."


def test_websocket_idle_stop_never_submits_prebuffer_to_asr(client, monkeypatch):
    """
    Regression (phantom stop-flush): when the VAD segmenter is idle, stop must
    NOT submit the rolling non-speech pre-buffer to ASR. No speech_result, no
    LLM invocation, no rate-limit consumption — only a non-error no_speech
    status. Repeated stop is a no-op and the socket stays usable.
    """
    import httpx
    from ai.inference.types import SpeechResult
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service
    import backend.app.websocket.speech_socket as speech_socket_mod
    from tests.test_doubles import FakeStreamingSileroVAD

    # VAD sees only non-speech: the segmenter stays idle and only its
    # pre-buffer accumulates.
    monkeypatch.setattr(
        speech_socket_mod,
        "SileroVAD",
        lambda *a, **k: FakeStreamingSileroVAD(probs=0.0),
    )

    asr_calls = []

    async def counting_transcribe(*args, **kwargs):
        asr_calls.append(1)
        return SpeechResult(
            transcript="phantom transcript",
            language="en",
            emotion=None,
            confidence=None,
            processing_time_ms=1,
            model_version="fake",
        )

    llm_calls = []

    async def counting_llm_handler(request: httpx.Request) -> httpx.Response:
        llm_calls.append(request)
        return httpx.Response(200, content=b'data: [DONE]\n\n')

    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", counting_transcribe)
    monkeypatch.setattr(
        llm_service, "_custom_client",
        httpx.AsyncClient(transport=httpx.MockTransport(counting_llm_handler)),
    )

    with client.websocket_connect("/ws/speech") as ws:
        _send_start(ws)
        # 1s of digital silence: fills the idle pre-buffer but never speech.
        _send_pcm(ws, _silent_pcm16_bytes(1.0))
        ws.send_json({"type": "stop"})
        # Repeated stop must be a no-op.
        ws.send_json({"type": "stop"})

        events = _drain_events(ws, max_events=10, stop_types=("status", "speech_result", "error", "llm_done"))
        types = [e.get("type") for e in events]

        assert "speech_result" not in types, f"idle stop must not emit speech_result: {events}"
        assert "llm_done" not in types and "llm_delta" not in types
        assert "error" not in types, f"idle stop must not be an error: {events}"
        assert any(e.get("type") == "status" and e.get("state") == "no_speech" for e in events), (
            f"expected no_speech status, got {events}"
        )
        assert asr_calls == [], "idle pre-buffer must never reach ASR"
        assert llm_calls == [], "no LLM turn may start without a speech_result"

        # Socket remains usable after repeated stops.
        ws.send_json({"type": "ping"})
        assert ws.receive_json().get("type") == "pong"


def test_websocket_stop_during_active_speech_flushes_segment(client, monkeypatch):
    """
    Stop while genuine speech is in progress preserves the final-segment
    flush: the buffered utterance is submitted once with
    debug.flushed_on_stop=True.
    """
    import httpx
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service

    real_transcribe = speech_service.transcribe_pcm16_bytes
    calls = []

    async def wrapped(*args, **kwargs):
        calls.append(1)
        return await real_transcribe(*args, **kwargs)

    async def ok_llm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n',
        )

    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", wrapped)
    monkeypatch.setattr(
        llm_service, "_custom_client",
        httpx.AsyncClient(transport=httpx.MockTransport(ok_llm_handler)),
    )

    with client.websocket_connect("/ws/speech") as ws:
        _send_start(ws)
        _send_pcm(ws, _sine_pcm16_bytes(0.5))
        ws.send_json({"type": "stop"})

        events = _drain_events(ws, stop_types=("speech_result", "error", "llm_done"))
        types = [e.get("type") for e in events]
        assert "speech_result" in types, f"expected flushed speech_result, got {events}"
        sr = next(e for e in events if e.get("type") == "speech_result")
        assert sr.get("debug", {}).get("flushed_on_stop") is True
        assert calls == [1], "exactly one ASR submission for the in-progress segment"


def test_websocket_stop_after_completed_segment_no_phantom_result(client, monkeypatch):
    """
    Regression: a VAD silence-timeout completion mid-recording produces one
    speech_result; the later stop (segmenter idle, only trailing silence in
    the pre-buffer) must not produce a second phantom speech_result or a
    second ASR call.
    """
    import httpx
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service
    import backend.app.websocket.speech_socket as speech_socket_mod
    from tests.test_doubles import FakeStreamingSileroVAD

    # 10 speech frames then 30 non-speech frames: the 21-frame (700ms)
    # silence threshold completes the utterance mid-stream; remaining frames
    # are idle pre-buffer only.
    monkeypatch.setattr(
        speech_socket_mod,
        "SileroVAD",
        lambda *a, **k: FakeStreamingSileroVAD(probs=[0.9] * 10 + [0.0] * 30),
    )

    real_transcribe = speech_service.transcribe_pcm16_bytes
    calls = []

    async def wrapped(*args, **kwargs):
        calls.append(1)
        return await real_transcribe(*args, **kwargs)

    async def ok_llm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n',
        )

    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", wrapped)
    monkeypatch.setattr(
        llm_service, "_custom_client",
        httpx.AsyncClient(transport=httpx.MockTransport(ok_llm_handler)),
    )

    with client.websocket_connect("/ws/speech") as ws:
        _send_start(ws)
        # Exactly 40 frame-sized chunks (1024 bytes each): 10 speech + 30 silence.
        _send_pcm(ws, _sine_pcm16_bytes(1.28))
        ws.send_json({"type": "stop"})

        events = _drain_events(ws, max_events=25, stop_types=("llm_done", "error"))
        speech_results = [e for e in events if e.get("type") == "speech_result"]

        assert len(speech_results) == 1, (
            f"expected exactly one speech_result (no phantom), got {len(speech_results)}: {events}"
        )
        sr = speech_results[0]
        assert sr.get("debug", {}).get("flushed_on_stop") is False
        assert calls == [1], f"ASR must run exactly once, got {len(calls)} calls"
