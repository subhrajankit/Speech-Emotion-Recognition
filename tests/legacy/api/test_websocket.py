import numpy as np
import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.config import settings

def test_websocket_ping_pong():
    settings.MOCK_MODELS = True
    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as websocket:
            websocket.send_json({"type": "ping"})
            data = websocket.receive_json()
            assert data["type"] == "pong"

def test_websocket_empty_utterance():
    settings.MOCK_MODELS = True
    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as websocket:
            websocket.send_json({"action": "end_of_utterance"})
            data = websocket.receive_json()
            assert data["type"] == "warning"
            assert "empty" in data["message"].lower()

def test_websocket_voice_roundtrip():
    settings.MOCK_MODELS = True
    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as websocket:
            # Send 1 second of mock PCM16 audio bytes
            mock_pcm = np.random.randint(-1000, 1000, 16000, dtype=np.int16).tobytes()
            websocket.send_bytes(mock_pcm)

            # Signal end of utterance
            websocket.send_json({"action": "end_of_utterance"})

            received_messages = []
            wav_chunks = []
            while True:
                raw = websocket.receive()
                if "text" in raw and raw["text"]:
                    import json
                    msg = json.loads(raw["text"])
                    received_messages.append(msg)
                    if msg.get("type") == "playback_ready":
                        break
                elif "bytes" in raw and raw["bytes"]:
                    wav_chunks.append(raw["bytes"])

            types = [m.get("type") for m in received_messages]
            assert "status" in types
            assert "llm_start" in types
            assert "sentence_start" in types
            assert "sentence_end" in types
            assert "turn_complete" in types
            assert "result" in types
            assert len(wav_chunks) >= 1
            assert len(wav_chunks[0]) > 44

