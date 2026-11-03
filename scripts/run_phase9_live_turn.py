"""
Phase 9 Acceptance Verification Script.
Executes an end-to-end live run against a live running VoiceSense server:
1. Verifies /api/health (including DB status component).
2. Registers a new user (POST /api/auth/register).
3. Logs in to obtain JWT access token (POST /api/auth/login).
4. Verifies authenticated identity (GET /api/auth/me).
5. Opens WebSocket turn (/ws/speech) with in-frame auth_token, streaming real Hindi speech.
6. Waits for speech_result and llm_done events.
7. Queries history list (GET /api/history/sessions).
8. Queries full session detail (GET /api/history/sessions/{id}).
9. Deletes session (DELETE /api/history/sessions/{id}) and purges all data (DELETE /api/history).
10. Verifies history is completely purged.

Untrimmed execution logs are saved to docs/deployment/runs/run_phase9_live_turn.txt.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

import httpx
import numpy as np
import soundfile as sf
import websockets

from ai.preprocessing.audio import load_and_preprocess_audio

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/speech"
OUTPUT_LOG = Path("docs/deployment/runs/run_phase9_live_turn.txt")


class OutputLogger:
    """Writes logs to stdout and output file simultaneously."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.filepath, "w", encoding="utf-8")

    def log(self, msg: str = ""):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] {msg}" if msg else ""
        try:
            print(formatted)
        except Exception:
            try:
                print(formatted.encode("ascii", errors="backslashreplace").decode("ascii"))
            except Exception:
                pass
        self.file.write(formatted + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


async def run_live_turn():
    logger = OutputLogger(OUTPUT_LOG)
    logger.log("=" * 80)
    logger.log("VOICESENSE AI — PHASE 9 ACCEPTANCE VERIFICATION RUN")
    logger.log("=" * 80)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as http_client:
        # Step 1: Health Check
        logger.log("\n[STEP 1] Checking server health...")
        resp = await http_client.get("/api/health")
        logger.log(f"GET /api/health -> Status: {resp.status_code}")
        health_data = resp.json()
        logger.log(f"Health Response:\n{json.dumps(health_data, indent=2)}")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        assert "db" in health_data["components"], "Database health component missing"
        logger.log(f"Database health status: {health_data['components']['db']}")

        # Step 2: Register User
        username = f"hindi_turn_user_{int(time.time())}"
        password = "SecurePassword123!"
        logger.log(f"\n[STEP 2] Registering user: {username}...")
        resp = await http_client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        logger.log(f"POST /api/auth/register -> Status: {resp.status_code}")
        reg_data = resp.json()
        logger.log(f"Registration Response:\n{json.dumps(reg_data, indent=2)}")
        assert resp.status_code in (200, 201), f"Registration failed: {resp.text}"
        user_id = reg_data["id"]

        # Step 3: Login to obtain JWT
        logger.log(f"\n[STEP 3] Logging in as {username}...")
        resp = await http_client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        logger.log(f"POST /api/auth/login -> Status: {resp.status_code}")
        login_data = resp.json()
        logger.log(f"Login Response:\n{json.dumps(login_data, indent=2)}")
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        access_token = login_data["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Step 4: Verify Current User (GET /api/auth/me)
        logger.log("\n[STEP 4] Verifying identity via GET /api/auth/me...")
        resp = await http_client.get("/api/auth/me", headers=auth_headers)
        logger.log(f"GET /api/auth/me -> Status: {resp.status_code}")
        me_data = resp.json()
        logger.log(f"Identity Response:\n{json.dumps(me_data, indent=2)}")
        assert resp.status_code == 200
        assert me_data["id"] == user_id

        # Step 5: WebSocket Turn with Real Hindi Speech
        logger.log(f"\n[STEP 5] Connecting to WebSocket: {WS_URL}...")
        hindi_clip_path = "tests/samples/sample_hindi_speech.wav"
        assert os.path.exists(hindi_clip_path), f"Sample clip missing: {hindi_clip_path}"

        audio_float = load_and_preprocess_audio(hindi_clip_path, target_sr=16000)
        pcm_bytes = (audio_float * 32767.0).astype(np.int16).tobytes()
        logger.log(
            f"Preprocessed Hindi audio: {len(audio_float)} samples ({len(audio_float)/16000:.2f}s), {len(pcm_bytes)} PCM16 bytes"
        )

        session_id = f"sess_p9_{int(time.time())}"
        ws_events = []

        async with websockets.connect(WS_URL) as ws:
            logger.log("Connected to WebSocket. Sending start frame...")
            start_frame = {
                "type": "start",
                "session_id": session_id,
                "sample_rate": 16000,
                "encoding": "pcm_s16le",
                "language_hint": "hi",
                "auth_token": access_token,
            }
            await ws.send(json.dumps(start_frame))
            logger.log(f"Sent start frame: {start_frame}")

            ready_raw = await ws.recv()
            ready_evt = json.loads(ready_raw)
            logger.log(f"\n[SERVER EVENT: READY]\n{json.dumps(ready_evt, indent=2)}")
            assert ready_evt.get("type") == "ready"

            # Stream audio frames
            chunk_size = 1024
            logger.log(f"Streaming {len(pcm_bytes)} bytes in {len(pcm_bytes)//chunk_size + 1} chunks...")
            for i in range(0, len(pcm_bytes), chunk_size):
                chunk = pcm_bytes[i : i + chunk_size]
                await ws.send(chunk)
                await asyncio.sleep(0.01)

            logger.log("Finished streaming audio frames. Sending stop frame...")
            await ws.send(json.dumps({"type": "stop"}))

            # Receive turns
            logger.log("Collecting server events...")
            try:
                while True:
                    evt_raw = await asyncio.wait_for(ws.recv(), timeout=25.0)
                    if isinstance(evt_raw, bytes):
                        # Binary frame (TTS audio chunk)
                        logger.log(f"[SERVER EVENT: BINARY_AUDIO_CHUNK] length={len(evt_raw)} bytes")
                        continue

                    evt = json.loads(evt_raw)
                    evt_type = evt.get("type")
                    logger.log(f"\n[SERVER EVENT: {evt_type.upper()}]\n{json.dumps(evt, indent=2)}")
                    ws_events.append(evt)

                    if evt_type in ("llm_done", "error", "tts_done"):
                        # If llm_done received, wait briefly for any trailing events
                        if evt_type == "llm_done":
                            await asyncio.sleep(0.5)
                        break
            except asyncio.TimeoutError:
                logger.log("Event collection timed out after 25.0s.")

        # Step 6: Verify Persistence via REST History API
        logger.log("\n[STEP 6] Waiting 1.0s for async persistence worker...")
        await asyncio.sleep(1.0)

        logger.log("\n[STEP 7] Querying user history via GET /api/history/sessions...")
        resp = await http_client.get("/api/history/sessions", headers=auth_headers)
        logger.log(f"GET /api/history/sessions -> Status: {resp.status_code}")
        sessions_list = resp.json()
        logger.log(f"Sessions List Response:\n{json.dumps(sessions_list, indent=2)}")
        assert resp.status_code == 200
        assert len(sessions_list) >= 1, "Expected at least 1 session for user"

        target_session = next((s for s in sessions_list if s["id"] == session_id), sessions_list[0])
        retrieved_id = target_session["id"]

        logger.log(f"\n[STEP 8] Querying detailed session history via GET /api/history/sessions/{retrieved_id}...")
        resp = await http_client.get(f"/api/history/sessions/{retrieved_id}", headers=auth_headers)
        logger.log(f"GET /api/history/sessions/{retrieved_id} -> Status: {resp.status_code}")
        session_detail = resp.json()
        logger.log(f"Session Detail Response:\n{json.dumps(session_detail, indent=2)}")
        assert resp.status_code == 200
        assert session_detail["id"] == retrieved_id
        assert len(session_detail["predictions"]) > 0, "Expected prediction records"

        pred = session_detail["predictions"][0]
        logger.log(f"Model Version: {pred.get('model_version')}")
        if pred.get("transcript"):
            logger.log(f"Stored Transcript: {pred['transcript']['text']} (lang: {pred['transcript']['language']})")
        if pred.get("emotion_result"):
            logger.log(f"Stored Emotion: {pred['emotion_result']['primary_emotion']}")

        # Step 9: Delete Session
        logger.log(f"\n[STEP 9] Deleting session {retrieved_id} via DELETE /api/history/sessions/{retrieved_id}...")
        resp = await http_client.delete(f"/api/history/sessions/{retrieved_id}", headers=auth_headers)
        logger.log(f"DELETE /api/history/sessions/{retrieved_id} -> Status: {resp.status_code}")
        logger.log(f"Delete Response:\n{json.dumps(resp.json(), indent=2)}")
        assert resp.status_code == 200

        # Step 10: Delete My Data (Purge all user data)
        logger.log("\n[STEP 10] Purging all user data via DELETE /api/history...")
        resp = await http_client.delete("/api/history", headers=auth_headers)
        logger.log(f"DELETE /api/history -> Status: {resp.status_code}")
        logger.log(f"Purge Response:\n{json.dumps(resp.json(), indent=2)}")
        assert resp.status_code == 200

        # Step 11: Verify History is completely empty
        logger.log("\n[STEP 11] Verifying history is empty via GET /api/history/sessions...")
        resp = await http_client.get("/api/history/sessions", headers=auth_headers)
        logger.log(f"GET /api/history/sessions -> Status: {resp.status_code}")
        final_sessions = resp.json()
        logger.log(f"Final Sessions Response:\n{json.dumps(final_sessions, indent=2)}")
        assert resp.status_code == 200
        assert len(final_sessions) == 0, f"Expected 0 sessions after purge, got {len(final_sessions)}"

    logger.log("\n" + "=" * 80)
    logger.log("PHASE 9 ACCEPTANCE RUN COMPLETED SUCCESSFULLY!")
    logger.log(f"Untrimmed logs saved to: {OUTPUT_LOG.resolve()}")
    logger.log("=" * 80)
    logger.close()


if __name__ == "__main__":
    asyncio.run(run_live_turn())
