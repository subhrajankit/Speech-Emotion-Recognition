import os
import pytest
import numpy as np
from fastapi.testclient import TestClient

os.environ["MOCK_MODELS"] = "true"

from src.backend.main import app
from src.backend.models.manager import model_manager
from src.backend.pipeline.orchestrator import VoicePipeline

def _generate_synthetic_pcm(duration_sec=0.5, sample_rate=16000, freq=440.0) -> bytes:
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)
    return samples.tobytes()

@pytest.mark.asyncio
async def test_streaming_pipeline_yields_sentences_and_metrics():
    model_manager.initialize()
    pipeline = VoicePipeline()
    pcm = _generate_synthetic_pcm(duration_sec=0.4)

    events = []
    sentence_events = []
    complete_event = None

    async for event_type, payload in pipeline.stream_utterance(pcm, conversation_id="test_stream_conv"):
        events.append((event_type, payload))
        if event_type == "sentence":
            sentence_events.append(payload)
        elif event_type == "complete":
            complete_event = payload

    assert len(events) >= 3
    assert len(sentence_events) >= 1
    assert complete_event is not None

    # Check metrics in complete event
    latencies = complete_event["latencies"]
    assert "ttft_ms" in latencies
    assert "ttfa_ms" in latencies
    assert "total_ms" in latencies
    assert latencies["total_ms"] >= 0

    # Verify first sentence audio chunk is valid WAV
    first_sentence = sentence_events[0]
    assert "audio_bytes" in first_sentence
    assert len(first_sentence["audio_bytes"]) > 44
    assert first_sentence["audio_bytes"][:4] == b"RIFF"
    assert "ttfa_ms" in first_sentence["latencies"]

def test_websocket_streaming_protocol_roundtrip():
    model_manager.initialize()
    pcm_speech = _generate_synthetic_pcm(duration_sec=0.4)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            # Send raw audio bytes
            ws.send_bytes(pcm_speech)
            # Force utterance end
            ws.send_text('{"action": "end-of-utterance"}')

            received_types = []
            binary_chunks = []
            turn_complete_data = None

            # Read until turn completes
            while True:
                msg = ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    binary_chunks.append(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    import json
                    data = json.loads(msg["text"])
                    msg_type = data.get("type")
                    received_types.append(msg_type)
                    if msg_type == "turn_complete":
                        turn_complete_data = data
                    if msg_type == "playback_ready":
                        break

            assert "status" in received_types
            assert "llm_start" in received_types
            assert "sentence_start" in received_types
            assert "sentence_end" in received_types
            assert "turn_complete" in received_types
            assert "result" in received_types

            assert len(binary_chunks) >= 1
            for chunk in binary_chunks:
                assert chunk[:4] == b"RIFF"

            assert turn_complete_data is not None
            assert "ttft_ms" in turn_complete_data["latencies"]
            assert "ttfa_ms" in turn_complete_data["latencies"]
