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
