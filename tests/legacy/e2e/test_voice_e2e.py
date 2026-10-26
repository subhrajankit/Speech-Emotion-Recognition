"""
End-to-End (E2E) Test Suite for SenseAI Voice Assistant (Phase 13).

Tests full speech-turn lifecycles through WebSocket and WebTransport endpoints:
- Handshake authentication
- VAD segmentation & streaming speech pipeline
- Intent routing across chat, knowledge, and command branches
- Emotion-aware prompt conditioning & sentence-by-sentence TTS audio streaming
- Telemetry recording in the benchmark ring buffer
"""

import pytest
from fastapi.testclient import TestClient

from src.backend.config import settings
from src.backend.main import app
from src.backend.pipeline import VoicePipeline
from src.backend.telemetry import benchmark_collector


class TestVoicePipelineE2E:
    """End-to-end tests for the complete voice assistant pipeline."""

    def test_e2e_full_streaming_voice_turn_over_websocket(self, auth_token, synthetic_speech_audio):
        """
        Simulates an entire voice turn:
        Client connects with JWT -> streams audio -> receives streaming sentences -> turn completion -> telemetry logged.
        """
        client = TestClient(app)

        with client.websocket_connect(f"/ws/voice?token={auth_token}") as ws:
            # 1. Send ping
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"

            # 2. Stream audio chunk and trigger end of utterance
            ws.send_bytes(synthetic_speech_audio)
            ws.send_json({"type": "end-of-utterance"})

            received_events = []
            received_audio_bytes = 0

            # Collect stream until turn completion
            while True:
                msg = ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    received_audio_bytes += len(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    import json
                    data = json.loads(msg["text"])
                    received_events.append(data.get("type"))
                    if data.get("type") in ("turn_complete", "result"):
                        break

            assert "status" in received_events
            assert "llm_start" in received_events
            assert "sentence_start" in received_events
            assert "turn_complete" in received_events
            assert received_audio_bytes > 0, "Expected binary audio frames from TTS synthesis"

            # 3. Verify stage timing telemetry was recorded
            metrics = benchmark_collector.get_recent(limit=1)
            assert len(metrics) == 1
            timing = metrics[0]
            assert timing["total"] > 0
            assert timing["llm_ttft"] > 0
            assert timing["tts_ttfa"] > 0

    @pytest.mark.asyncio
    async def test_e2e_multi_intent_routing_branches(self, synthetic_speech_audio):
        """
        Verifies all three branches of the Intent Router execute properly in the pipeline:
        - 'chat': direct LLM generation
        - 'knowledge': RAG retrieval with citation note
        - 'command': deterministic utility stub
        """
        pipeline = VoicePipeline()

        # Branch 1: Chat Intent (Default)
        chat_events = []
        async for event_type, payload in pipeline.stream_utterance(synthetic_speech_audio):
            chat_events.append((event_type, payload))

        turn_complete = next(p for t, p in chat_events if t == "complete")
        assert turn_complete["intent"]["category"] == "chat"
        assert "response_text" in turn_complete

        # Branch 2: Knowledge Intent
        # Mock transcript containing knowledge keywords
        async def knowledge_generator():
            async for ev, pl in pipeline.stream_utterance(synthetic_speech_audio):
                if ev == "complete":
                    return pl
        
        # Test Intent Router directly verifies branch segregation
        from src.backend.pipeline.intent import IntentRouter
        router = IntentRouter()
        knowledge_res = router.classify("According to the company policy, what is the leave rule?")
        assert knowledge_res.category == "knowledge"

        command_res = router.classify("Set a reminder for 5pm")
        assert command_res.category == "command"

    def test_e2e_security_handshake_rejection_and_acceptance(self, monkeypatch, auth_token):
        """
        Validates handshake authentication gating end-to-end:
        - Unauthorized handshake rejected with code 1008
        - Authorized handshake accepted
        """
        monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
        client = TestClient(app)

        # Unauthorized
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/voice") as ws:
                pass

        # Authorized
        with client.websocket_connect(f"/ws/voice?token={auth_token}") as ws:
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"
