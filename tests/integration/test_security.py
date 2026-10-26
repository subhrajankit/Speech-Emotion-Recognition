import os
import json
import sqlite3
import pytest
from starlette.testclient import TestClient

from src.backend.main import app
from src.backend.config import settings
from src.backend.security.auth import create_access_token
from src.backend.security.audit import AuditLogger
from src.backend.audio.liveness import VoiceLivenessDetector
from src.backend.pipeline.intent import IntentRouter, IntentCategory
from src.backend.database.storage import EmotionStorage


@pytest.fixture(autouse=True)
def enable_mock_models():
    orig = settings.MOCK_MODELS
    settings.MOCK_MODELS = True
    yield
    settings.MOCK_MODELS = orig


def test_unauthenticated_websocket_handshake_rejected():
    settings.REQUIRE_AUTH = True
    try:
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/voice") as ws:
                pass
    finally:
        settings.REQUIRE_AUTH = False


def test_authenticated_websocket_handshake_accepted():
    settings.REQUIRE_AUTH = True
    try:
        client = TestClient(app)
        token = create_access_token(session_id="secure_session_1", client_id="test_client")
        with client.websocket_connect(f"/ws/voice?token={token}") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data.get("type") == "pong"
    finally:
        settings.REQUIRE_AUTH = False


def test_command_whitelist_sandboxing():
    router = IntentRouter()
    assert router.is_command_whitelisted("command:timer") is True
    assert router.is_command_whitelisted("command:calculator") is True
    assert router.is_command_whitelisted("command:rm_rf") is False
    assert router.is_command_whitelisted("command:unauthorized_shell") is False


def test_voice_liveness_detection(synthetic_speech_audio):
    detector = VoiceLivenessDetector()
    result = detector.analyze(synthetic_speech_audio)
    assert hasattr(result, "is_suspicious")
    assert hasattr(result, "flatness")
    assert hasattr(result, "rms_variance")
    assert isinstance(result.details, dict)


def test_audit_logger_hash_chain_and_tamper_detection(tmp_path):
    log_file = str(tmp_path / "test_audit.log")
    logger = AuditLogger(log_path=log_file)

    e1 = logger.log_event("AUTH_SUCCESS", actor="user1", details={"ip": "127.0.0.1"})
    e2 = logger.log_event("COMMAND_EXECUTED", actor="user1", details={"cmd": "timer"})
    e3 = logger.log_event("COMMAND_REJECTED", actor="attacker", details={"cmd": "exec"})

    valid, count = logger.verify_chain()
    assert valid is True
    assert count == 3

    # Tamper with the log file
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Modify event in second record
    record2 = json.loads(lines[1])
    record2["event_type"] = "TAMPERED_EVENT"
    lines[1] = json.dumps(record2) + "\n"

    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verification must detect tampering
    valid_after_tamper, msg = logger.verify_chain()
    assert valid_after_tamper is False
    assert "Hash mismatch" in msg


def test_database_field_level_encryption_at_rest(tmp_path):
    db_file = str(tmp_path / "encrypted_test.db")
    # Strong 32-byte url-safe base64 test Fernet key
    test_key = "Wwd7xrp9M6xNeeZ83gaigH1-DwKbDRUFlgI0SGl5L_o="
    storage = EmotionStorage(db_path=db_file, encryption_key=test_key)

    conv_id = "patient_session_99"
    sensitive_transcript = "Patient reports mild chest tightness and elevated anxiety."
    primary_emotion = "anxious"

    row_id = storage.save_emotion_event(
        conversation_id=conv_id,
        primary_emotion=primary_emotion,
        confidence=0.92,
        valence=-0.4,
        arousal=0.7,
        raw_transcript=sensitive_transcript
    )
    assert row_id > 0

    # 1. Direct SQLite query: Verify raw data on disk is encrypted
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT primary_emotion, raw_transcript FROM emotion_history WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    conn.close()

    db_emotion, db_transcript = row
    assert db_transcript.startswith("enc::")
    assert db_emotion.startswith("enc::")
    assert sensitive_transcript not in db_transcript
    assert primary_emotion not in db_emotion

    # 2. Storage layer query: Verify transparent decryption
    history = storage.get_history(conversation_id=conv_id, limit=5)
    assert len(history) == 1
    assert history[0]["raw_transcript"] == sensitive_transcript
    assert history[0]["primary_emotion"] == primary_emotion
