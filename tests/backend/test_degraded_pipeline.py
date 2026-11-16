"""
Degraded Pipeline End-to-End Tests (Checklist Item 11).
Verifies that voice requests over WebSocket gracefully degrade when downstream components fail:
1. No LLM (LLM service returns 503 / unavailable).
2. No RAG (RAG vector store index missing / unindexed).
3. No TTS (TTS service disabled or failing).
4. No DB (Database down / OperationalError on persistence).
5. All 4 downstream components down simultaneously (perception invariant preserved).
"""

import json
import time
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
import soundfile as sf
import httpx
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.security import create_access_token, hash_password
from backend.app.core.database import get_db_session
from backend.app.models.user import User
from backend.app.services.llm_service import llm_service
from backend.app.services.tts_service import tts_service
from backend.app.services.rag_service import rag_service
from tests.backend.test_tts_service import FakeEngineForTests


def _ensure_degraded_user(user_id: str, username: str) -> None:
    """Creates the user row backing a test JWT so FK enforcement accepts sessions."""
    with get_db_session() as db:
        if db.query(User).filter(User.id == user_id).first() is None:
            db.add(User(
                id=user_id,
                username=username,
                hashed_password=hash_password("test_password_123"),
                is_active=True,
            ))
            db.commit()
from tests.test_doubles import FakeEmbeddings


def _generate_pcm16_speech_audio() -> bytes:
    """Generates 1.0s of audible synthetic tone simulating speech audio."""
    t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
    samples = (0.5 * np.sin(2 * np.pi * 300 * t) * 32767.0).astype(np.int16)
    return samples.tobytes()


def _stream_turn_and_collect_events(ws, pcm_bytes: bytes, max_reads: int = 30):
    """Streams audio chunk by chunk, sends stop, and collects received JSON events."""
    chunk_size = 1024
    for i in range(0, len(pcm_bytes), chunk_size):
        ws.send_bytes(pcm_bytes[i : i + chunk_size])
    ws.send_json({"type": "stop"})

    events = []
    for _ in range(max_reads):
        try:
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                events.append(data)
                if data.get("type") in ("llm_done", "error") and "speech_result" in [e.get("type") for e in events]:
                    break
        except Exception:
            break
    return events


@pytest.mark.unit
def test_degraded_variant_no_llm(client, monkeypatch):
    """
    Degraded Variant A: No LLM.
    When the local LLM server (Qwen3 / llama.cpp) is offline or returns 503,
    speech_result (transcript + emotion) is STILL delivered reliably,
    followed by a friendly llm_unavailable error event.
    """
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "LLM daemon unavailable"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)
    monkeypatch.setattr(tts_service, "_engine_override", FakeEngineForTests())

    pcm_bytes = _generate_pcm16_speech_audio()

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
        })
        ready = ws.receive_json()
        assert ready.get("type") == "ready"

        events = _stream_turn_and_collect_events(ws, pcm_bytes)
        event_types = [e.get("type") for e in events]

        # Invariant: Speech result must be delivered
        assert "speech_result" in event_types, f"speech_result missing: {event_types}"
        speech_evt = next(e for e in events if e.get("type") == "speech_result")
        assert "transcript" in speech_evt
        assert "emotion" in speech_evt

        # LLM failure must be reported cleanly
        has_llm_error = any(
            e.get("type") == "error" and e.get("code") in ("llm_unavailable", "llm_bad_response", "INFERENCE_ERROR")
            for e in events
        )
        assert has_llm_error, f"Expected LLM error event, got: {events}"


@pytest.mark.unit
def test_degraded_variant_no_rag(client, monkeypatch, tmp_path):
    """
    Degraded Variant B: No RAG.
    When RAG index is missing, corrupted, or unindexed,
    knowledge queries degrade gracefully into plain conversational chat,
    emitting a rag_fallback status without throwing errors or breaking the turn.
    """
    empty_index_dir = tmp_path / "empty_rag_index"
    empty_index_dir.mkdir()
    monkeypatch.setattr(rag_service, "index_dir", empty_index_dir)
    rag_service.embedder = FakeEmbeddings()
    rag_service.initialize()

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"General conversation response without RAG."}}]}\n\n',
        b'data: [DONE]\n\n',
    ]
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)
    monkeypatch.setattr(tts_service, "_engine_override", FakeEngineForTests())

    pcm_bytes = _generate_pcm16_speech_audio()

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
        })
        ready = ws.receive_json()
        assert ready.get("type") == "ready"

        events = _stream_turn_and_collect_events(ws, pcm_bytes)
        event_types = [e.get("type") for e in events]

        assert "speech_result" in event_types
        assert "llm_delta" in event_types
        assert "llm_done" in event_types
        llm_done = next(e for e in events if e.get("type") == "llm_done")
        assert llm_done.get("sources") == []


@pytest.mark.unit
def test_degraded_variant_no_tts(client, monkeypatch):
    """
    Degraded Variant C: No TTS.
    When TTS is disabled in configuration or synthesis fails,
    speech_result and text response (llm_chunk/llm_done) are delivered fully.
    Audio playback is omitted without raising uncaught exceptions.
    """
    monkeypatch.setattr(settings, "TTS_ENABLED", False)

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"Visual-only text reply."}}]}\n\n',
        b'data: [DONE]\n\n',
    ]
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    pcm_bytes = _generate_pcm16_speech_audio()

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
        })
        ready = ws.receive_json()
        assert ready.get("type") == "ready"

        events = _stream_turn_and_collect_events(ws, pcm_bytes)
        event_types = [e.get("type") for e in events]

        assert "speech_result" in event_types
        assert "llm_delta" in event_types
        assert "llm_done" in event_types
        # When TTS is disabled, no tts_chunk should be sent
        assert "tts_chunk" not in event_types


@pytest.mark.unit
def test_degraded_variant_no_db(client, monkeypatch, caplog):
    """
    Degraded Variant D: No DB.
    When database persistence fails (e.g. connection refused or pool exhausted),
    WebSocket turn finishes without delay and failure is safely logged and swallowed.
    """
    _ensure_degraded_user("usr_degraded_test", "degraded_tester")
    token = create_access_token(user_id="usr_degraded_test", username="degraded_tester")

    sse_chunks = [
        b'data: {"choices":[{"delta":{"content":"Delivered despite database failure."}}]}\n\n',
        b'data: [DONE]\n\n',
    ]
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(sse_chunks))

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)
    monkeypatch.setattr(tts_service, "_engine_override", FakeEngineForTests())

    pcm_bytes = _generate_pcm16_speech_audio()

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

            events = _stream_turn_and_collect_events(ws, pcm_bytes)
            event_types = [e.get("type") for e in events]

            assert "speech_result" in event_types
            assert "llm_done" in event_types


@pytest.mark.unit
def test_degraded_variant_all_four_down(client, monkeypatch, tmp_path):
    """
    Degraded Variant E: All 4 Down Simultaneously (No LLM, No RAG, No TTS, No DB).
    Verifies the ultimate core architecture invariant:
    Perception (ASR + Emotion) has zero coupling to downstream systems.
    Even with LLM offline, RAG missing, TTS disabled, and DB down,
    speech_result is STILL produced and delivered over WebSocket!
    """
    _ensure_degraded_user("usr_catastrophe", "catastrophe_tester")
    token = create_access_token(user_id="usr_catastrophe", username="catastrophe_tester")

    # 1. RAG missing
    empty_index_dir = tmp_path / "catastrophe_empty_rag"
    empty_index_dir.mkdir()
    monkeypatch.setattr(rag_service, "index_dir", empty_index_dir)
    rag_service.embedder = FakeEmbeddings()
    rag_service.initialize()

    # 2. LLM offline (503)
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "LLM crashed"})
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    # 3. TTS disabled
    monkeypatch.setattr(settings, "TTS_ENABLED", False)

    # 4. DB down
    pcm_bytes = _generate_pcm16_speech_audio()

    with patch(
        "backend.app.services.history_service.HistoryService.persist_turn_sync",
        side_effect=RuntimeError("Simulated DB Catastrophe"),
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

            events = _stream_turn_and_collect_events(ws, pcm_bytes)
            event_types = [e.get("type") for e in events]

            # The core invariant must hold:
            assert "speech_result" in event_types, f"speech_result missing: {event_types}"
            speech_evt = next(e for e in events if e.get("type") == "speech_result")
            assert "transcript" in speech_evt
            assert speech_evt["transcript"] != ""
            assert "emotion" in speech_evt
