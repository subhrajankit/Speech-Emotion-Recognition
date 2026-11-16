"""
History API & User Isolation Tests for VoiceSense AI.
Verifies session listing, inspection, deletion, cross-user isolation, and delete-my-data.
"""

import time
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import get_db_session
from backend.app.models.user import User
from backend.app.models.session import Session as DBSession
from backend.app.models.prediction import Prediction
from backend.app.models.transcript import Transcript
from backend.app.models.emotion import EmotionResult
from backend.app.models.message import Message
from backend.app.core.rate_limiter import auth_rate_limiter
from backend.app.services.history_service import history_service


def _register_and_login(client: TestClient, username_prefix: str) -> tuple[str, str]:
    """Helper creating a user and returning (user_id, access_token)."""
    auth_rate_limiter.reset()
    ts = int(time.time() * 1000)
    username = f"{username_prefix}_{ts}"
    password = "SecurePassword123!"

    reg = client.post("/api/auth/register", json={"username": username, "password": password})
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]

    return user_id, token


def test_history_user_isolation_and_delete_my_data(client: TestClient):
    """
    Acceptance Criterion:
    History isolation (user A cannot read or delete user B's session); delete-my-data.
    """
    # 1. Create User A and User B
    user_a_id, token_a = _register_and_login(client, "user_a")
    user_b_id, token_b = _register_and_login(client, "user_b")

    # 2. Seed a session and turns for User A directly
    session_a_id = f"sess_a_{uuid.uuid4().hex[:8]}"
    with get_db_session() as db:
        session_a = DBSession(id=session_a_id, user_id=user_a_id, primary_language="en")
        pred_a = Prediction(id=str(uuid.uuid4()), session_id=session_a_id, processing_time_ms=500.0)
        trans_a = Transcript(id=str(uuid.uuid4()), prediction_id=pred_a.id, session_id=session_a_id, text="User A Secret", language="en")
        emo_a = EmotionResult(id=str(uuid.uuid4()), prediction_id=pred_a.id, session_id=session_a_id, primary_emotion="happy", confidence=0.9, valence=0.8, arousal=0.6)
        msg_a = Message(id=str(uuid.uuid4()), session_id=session_a_id, prediction_id=pred_a.id, role="assistant", text="Reply to A")
        db.add_all([session_a, pred_a, trans_a, emo_a, msg_a])
        db.commit()

    # 3. Seed a session for User B
    session_b_id = f"sess_b_{uuid.uuid4().hex[:8]}"
    with get_db_session() as db:
        session_b = DBSession(id=session_b_id, user_id=user_b_id, primary_language="hi")
        db.add(session_b)
        db.commit()

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 4. Listing sessions: User A sees only Session A; User B sees only Session B
    list_a = client.get("/api/history/sessions", headers=headers_a)
    assert list_a.status_code == 200
    ids_a = [s["id"] for s in list_a.json()]
    assert session_a_id in ids_a
    assert session_b_id not in ids_a

    list_b = client.get("/api/history/sessions", headers=headers_b)
    assert list_b.status_code == 200
    ids_b = [s["id"] for s in list_b.json()]
    assert session_b_id in ids_b
    assert session_a_id not in ids_b

    # 5. Isolation: User B tries to GET User A's session -> 404
    cross_read = client.get(f"/api/history/sessions/{session_a_id}", headers=headers_b)
    assert cross_read.status_code == 404

    # 6. Isolation: User B tries to DELETE User A's session -> 404
    cross_delete = client.delete(f"/api/history/sessions/{session_a_id}", headers=headers_b)
    assert cross_delete.status_code == 404

    # 7. User A reads Session A detail -> 200
    detail_a = client.get(f"/api/history/sessions/{session_a_id}", headers=headers_a)
    assert detail_a.status_code == 200
    data_a = detail_a.json()
    assert len(data_a["predictions"]) == 1
    assert data_a["predictions"][0]["transcript"]["text"] == "User A Secret"
    assert len(data_a["messages"]) == 1

    # 8. User A deletes their single session -> 200
    del_single = client.delete(f"/api/history/sessions/{session_a_id}", headers=headers_a)
    assert del_single.status_code == 200
    # Confirm it's gone
    assert client.get(f"/api/history/sessions/{session_a_id}", headers=headers_a).status_code == 404

    # 9. Delete-my-data: Create new session for User B, then User B calls DELETE /api/history
    purge_resp = client.delete("/api/history", headers=headers_b)
    assert purge_resp.status_code == 200
    purge_data = purge_resp.json()
    assert purge_data["deleted"] is True
    assert purge_data["purged_sessions_count"] >= 1

    # Confirm User B's history is empty
    empty_b = client.get("/api/history/sessions", headers=headers_b)
    assert empty_b.status_code == 200
    assert len(empty_b.json()) == 0


def _speech_payload(text: str = "turn text") -> dict:
    return {
        "transcript": text,
        "language": "en",
        "emotion": "happy",
        "confidence": None,
        "processing_time_ms": 12.0,
        "model_version": "SenseVoiceSmall (funasr)",
        "debug": {},
    }


def _session_row_counts(session_id: str) -> tuple[int, int, int, int]:
    with get_db_session() as db:
        return (
            db.query(Prediction).filter(Prediction.session_id == session_id).count(),
            db.query(Transcript).filter(Transcript.session_id == session_id).count(),
            db.query(EmotionResult).filter(EmotionResult.session_id == session_id).count(),
            db.query(Message).filter(Message.session_id == session_id).count(),
        )


def test_persistence_rejects_cross_user_session_write(client: TestClient):
    """
    C3-5 regression: a turn persisted with another user's session_id must be
    rejected — the victim's session receives no new rows and ownership is
    never transferred.
    """
    user_a_id, _token_a = _register_and_login(client, "sess_owner")
    user_b_id, _token_b = _register_and_login(client, "sess_intruder")

    session_a_id = f"sess_a_{uuid.uuid4().hex[:8]}"
    with get_db_session() as db:
        db.add(DBSession(id=session_a_id, user_id=user_a_id, primary_language="en"))
        db.commit()

    before = _session_row_counts(session_a_id)

    # User B attempts to persist a turn into User A's session
    pred_id = history_service.persist_turn_sync(
        session_id=session_a_id,
        user_id=user_b_id,
        speech_result_data=_speech_payload("forged by B"),
        llm_response_text="injected reply",
    )
    assert pred_id is None
    assert _session_row_counts(session_a_id) == before

    # Ownership unchanged: session still belongs to A only
    with get_db_session() as db:
        owner = db.query(DBSession.user_id).filter(DBSession.id == session_a_id).scalar()
        assert owner == user_a_id

    # Same-user reuse still works: A persists into their own session
    pred_id_a = history_service.persist_turn_sync(
        session_id=session_a_id,
        user_id=user_a_id,
        speech_result_data=_speech_payload("legit turn by A"),
        llm_response_text="reply to A",
    )
    assert pred_id_a is not None

    after = _session_row_counts(session_a_id)
    assert after[0] == before[0] + 1  # +1 prediction
    assert after[1] == before[1] + 1  # +1 transcript
    assert after[2] == before[2] + 1  # +1 emotion result
    assert after[3] == before[3] + 2  # +1 user msg +1 assistant msg

    # The persisted content belongs to A's turn
    with get_db_session() as db:
        texts = [
            t.text
            for t in db.query(Transcript).filter(Transcript.session_id == session_a_id).all()
        ]
        assert "legit turn by A" in texts
        assert "forged by B" not in texts


def test_persistence_skips_emotion_result_when_emotion_none(client: TestClient):
    """
    C3-3 regression: SpeechResult.emotion=None (e.g. IndicConformer turns)
    must NOT create a fabricated 'neutral' EmotionResult row.
    """
    user_id, _token = _register_and_login(client, "noemotion")
    session_id = f"sess_ne_{uuid.uuid4().hex[:8]}"

    payload = _speech_payload("hindi turn")
    payload["emotion"] = None
    payload["model_version"] = "IndicConformer-600m (multilingual)"

    pred_id = history_service.persist_turn_sync(
        session_id=session_id,
        user_id=user_id,
        speech_result_data=payload,
    )
    assert pred_id is not None

    with get_db_session() as db:
        emotions = db.query(EmotionResult).filter(EmotionResult.session_id == session_id).all()
        assert emotions == []
        # Turn itself still persisted
        assert db.query(Prediction).filter(Prediction.session_id == session_id).count() == 1
        assert db.query(Transcript).filter(Transcript.session_id == session_id).count() == 1


def test_persistence_stores_null_metrics_for_real_emotion(client: TestClient):
    """
    C3-1/C3-2 regression: a genuine emotion label persists, but confidence,
    valence, and arousal are NULL — never fabricated constants or
    lookup-table approximations.
    """
    user_id, _token = _register_and_login(client, "realemo")
    session_id = f"sess_re_{uuid.uuid4().hex[:8]}"

    pred_id = history_service.persist_turn_sync(
        session_id=session_id,
        user_id=user_id,
        speech_result_data=_speech_payload("happy turn"),
    )
    assert pred_id is not None

    with get_db_session() as db:
        emo = db.query(EmotionResult).filter(EmotionResult.prediction_id == pred_id).one()
        assert emo.primary_emotion == "happy"
        assert emo.confidence is None
        assert emo.valence is None
        assert emo.arousal is None


def test_history_api_serializes_turn_without_emotion_result(client: TestClient):
    """
    History API must safely serialize predictions that have no EmotionResult
    row, and legacy rows with populated metrics must remain readable.
    """
    user_id, token = _register_and_login(client, "sercheck")
    headers = {"Authorization": f"Bearer {token}"}

    # Turn 1: real emotion -> row with NULL metrics
    session_id = f"sess_ser_{uuid.uuid4().hex[:8]}"
    pred_with = history_service.persist_turn_sync(
        session_id=session_id, user_id=user_id, speech_result_data=_speech_payload("with emo")
    )
    # Turn 2: no emotion -> no EmotionResult row (same session reuse)
    payload_noemo = _speech_payload("no emo")
    payload_noemo["emotion"] = None
    pred_without = history_service.persist_turn_sync(
        session_id=session_id, user_id=user_id, speech_result_data=payload_noemo
    )
    assert pred_with and pred_without

    # Legacy-style row with populated metrics must still serialize
    with get_db_session() as db:
        legacy_pred = Prediction(
            id=str(uuid.uuid4()), session_id=session_id, processing_time_ms=1.0,
        )
        db.add(legacy_pred)
        db.flush()
        db.add(EmotionResult(
            id=str(uuid.uuid4()), prediction_id=legacy_pred.id, session_id=session_id,
            primary_emotion="sad", confidence=0.9, valence=-0.7, arousal=-0.4,
        ))
        db.commit()

    detail = client.get(f"/api/history/sessions/{session_id}", headers=headers)
    assert detail.status_code == 200
    preds = {p["id"]: p for p in detail.json()["predictions"]}

    assert preds[pred_with]["emotion_result"]["primary_emotion"] == "happy"
    assert preds[pred_with]["emotion_result"]["confidence"] is None
    assert preds[pred_with]["emotion_result"]["valence"] is None
    assert preds[pred_with]["emotion_result"]["arousal"] is None

    assert preds[pred_without]["emotion_result"] is None

    legacy = [p for p in detail.json()["predictions"] if p["id"] not in (pred_with, pred_without)]
    assert len(legacy) == 1
    assert legacy[0]["emotion_result"]["confidence"] == 0.9
    assert legacy[0]["emotion_result"]["valence"] == -0.7


def test_persistence_stores_null_script_and_mixed_language(client: TestClient):
    """
    C3-6 regression: SpeechResult has no script/mixed_language fields, so the
    pipeline cannot determine them — they must persist as NULL, never the
    fabricated defaults "latin"/False.
    """
    user_id, _token = _register_and_login(client, "scriptnull")
    session_id = f"sess_sn_{uuid.uuid4().hex[:8]}"

    pred_id = history_service.persist_turn_sync(
        session_id=session_id,
        user_id=user_id,
        speech_result_data=_speech_payload("multilingual turn"),
    )
    assert pred_id is not None

    with get_db_session() as db:
        tr = db.query(Transcript).filter(Transcript.prediction_id == pred_id).one()
        assert tr.script is None
        assert tr.mixed_language is None
        # Real fields untouched
        assert tr.text == "multilingual turn"
        assert tr.language == "en"
        assert tr.created_at is not None


def test_persistence_stores_genuine_script_metadata_when_present(client: TestClient):
    """
    If a payload ever carries genuine script/mixed_language values they must
    persist verbatim.
    """
    user_id, _token = _register_and_login(client, "scriptreal")
    session_id = f"sess_sr_{uuid.uuid4().hex[:8]}"

    payload = _speech_payload("code switched turn")
    payload["script"] = "devanagari"
    payload["mixed_language"] = True

    pred_id = history_service.persist_turn_sync(
        session_id=session_id,
        user_id=user_id,
        speech_result_data=payload,
    )
    assert pred_id is not None

    with get_db_session() as db:
        tr = db.query(Transcript).filter(Transcript.prediction_id == pred_id).one()
        assert tr.script == "devanagari"
        assert tr.mixed_language is True


def test_history_api_serializes_null_transcript_metadata(client: TestClient):
    """
    History API must serialize NULL script/mixed_language safely and keep
    legacy rows (with populated values) readable.
    """
    user_id, token = _register_and_login(client, "scriptapi")
    headers = {"Authorization": f"Bearer {token}"}
    session_id = f"sess_sa_{uuid.uuid4().hex[:8]}"

    pred_new = history_service.persist_turn_sync(
        session_id=session_id, user_id=user_id, speech_result_data=_speech_payload("new turn")
    )
    # Legacy row with populated metadata
    with get_db_session() as db:
        legacy_pred = Prediction(id=str(uuid.uuid4()), session_id=session_id, processing_time_ms=1.0)
        db.add(legacy_pred)
        db.flush()
        db.add(Transcript(
            id=str(uuid.uuid4()), prediction_id=legacy_pred.id, session_id=session_id,
            text="legacy turn", language="zh", script="han", mixed_language=False,
        ))
        db.commit()
        legacy_pred_id = legacy_pred.id

    detail = client.get(f"/api/history/sessions/{session_id}", headers=headers)
    assert detail.status_code == 200
    preds = {p["id"]: p for p in detail.json()["predictions"]}

    new_tr = preds[pred_new]["transcript"]
    assert new_tr["script"] is None
    assert new_tr["mixed_language"] is None
    assert new_tr["text"] == "new turn"

    legacy_tr = preds[legacy_pred_id]["transcript"]
    assert legacy_tr["script"] == "han"
    assert legacy_tr["mixed_language"] is False
