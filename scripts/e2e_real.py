#!/usr/bin/env python3
"""
Manual Real-Model End-to-End Verification Script (Phase 10 Requirement 5).
NOT a unit test. Never run in CI.

Runs against live server started from HEAD:
1. Spawns backend server on 127.0.0.1:8000 using local python environment.
2. Polls /api/health until server is fully initialized.
3. Streams authentic Hindi clip (sample_hindi_speech.wav) with language_hint="hi" over /ws/speech.
4. Streams authentic English clip (english_speech_16k.wav) with language_hint="en" over /ws/speech.
5. Verifies and logs real transcription, emotion outputs, and pipeline events.
6. Saves complete untrimmed logs to docs/deployment/runs/run_phase10_e2e_real.txt.
7. Shuts down backend server cleanly.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
import numpy as np
import websockets

from ai.preprocessing.audio import load_and_preprocess_audio

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/speech"
OUTPUT_LOG = Path("docs/deployment/runs/run_phase10_e2e_real.txt")


class OutputLogger:
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


async def wait_for_server_healthy(logger: OutputLogger, timeout_s: float = 60.0):
    start = time.time()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
        while time.time() - start < timeout_s:
            try:
                resp = await client.get("/api/health")
                if resp.status_code == 200:
                    data = resp.json()
                    logger.log(f"Server reported healthy: status={data.get('status')}")
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


async def run_turn(logger: OutputLogger, audio_path: str, lang_hint: str, label: str):
    logger.log(f"\n--- Starting {label} Turn ({audio_path}, hint={lang_hint}) ---")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file missing: {audio_path}")

    audio_float = load_and_preprocess_audio(audio_path, target_sr=16000)
    pcm_bytes = (audio_float * 32767.0).astype(np.int16).tobytes()
    logger.log(f"Audio preprocessed: {len(audio_float)} samples ({len(audio_float)/16000:.2f}s), {len(pcm_bytes)} bytes")

    events = []
    binary_chunks_count = 0
    binary_bytes_total = 0

    async with websockets.connect(WS_URL, ping_interval=120, ping_timeout=120) as ws:
        # 1. Send start
        start_frame = {
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": lang_hint,
        }
        await ws.send(json.dumps(start_frame))
        logger.log(f"Sent start frame: {start_frame}")

        # 2. Receive ready
        ready_raw = await ws.recv()
        ready_evt = json.loads(ready_raw)
        logger.log(f"Received event: {ready_evt.get('type')}")
        events.append(ready_evt)

        # 3. Stream audio
        chunk_size = 1024
        for i in range(0, len(pcm_bytes), chunk_size):
            await ws.send(pcm_bytes[i : i + chunk_size])
            await asyncio.sleep(0.01)

        # 4. Send stop
        await ws.send(json.dumps({"type": "stop"}))
        logger.log("Sent stop frame. Awaiting responses...")

        # 5. Receive stream events
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=120.0)
                if isinstance(msg, bytes):
                    binary_chunks_count += 1
                    binary_bytes_total += len(msg)
                    continue

                evt = json.loads(msg)
                evt_type = evt.get("type")
                events.append(evt)
                logger.log(f"Received event [{evt_type}]: {json.dumps(evt, ensure_ascii=False)}")

                if evt_type in ("llm_done", "error"):
                    # Wait briefly for any remaining tts binary chunks
                    await asyncio.sleep(0.5)
                    break
        except asyncio.TimeoutError:
            logger.log("Event reception timed out.")

    logger.log(f"Total events received: {len(events)}, TTS binary chunks: {binary_chunks_count} ({binary_bytes_total} bytes)")
    return events


async def main():
    logger = OutputLogger(OUTPUT_LOG)
    logger.log("=" * 80)
    logger.log("VOICESENSE AI — MANUAL REAL-MODEL E2E RUN (scripts/e2e_real.py)")
    logger.log("=" * 80)

    # 1. Start backend process
    logger.log("[1/5] Starting backend server subprocess from HEAD...")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--ws-ping-interval",
        "120",
        "--ws-ping-timeout",
        "120",
    ]
    env = os.environ.copy()
    env["AUTH_REQUIRED"] = "false"
    env["OPENBLAS_NUM_THREADS"] = "1"

    server_log_path = Path("docs/deployment/runs/server_e2e_real.log")
    server_log = open(server_log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    logger.log(f"Backend process spawned. PID: {proc.pid} (logging to {server_log_path})")

    try:
        # 2. Wait for server healthy
        logger.log("[2/5] Waiting for server to become healthy at http://127.0.0.1:8000/api/health...")
        healthy = await wait_for_server_healthy(logger, timeout_s=60.0)
        if not healthy:
            logger.log("ERROR: Server failed to reach healthy state within timeout.")
            return 1

        # Check health response details
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            h_resp = await client.get("/api/health")
            logger.log(f"Health Response:\n{json.dumps(h_resp.json(), indent=2)}")

        # 3. Hindi Turn
        logger.log("\n[3/5] Executing Turn 1: Real Hindi Speech with language_hint='hi'")
        hindi_events = await run_turn(
            logger=logger,
            audio_path="tests/samples/sample_hindi_speech.wav",
            lang_hint="hi",
            label="Hindi",
        )
        hindi_speech = next((e for e in hindi_events if e.get("type") == "speech_result"), None)
        assert hindi_speech is not None, "Hindi turn did not produce speech_result"
        logger.log(f"Hindi Transcript: {hindi_speech.get('transcript')}")
        logger.log(f"Hindi Language: {hindi_speech.get('language')}")
        logger.log(f"Hindi Emotion (Invariant: None): {hindi_speech.get('emotion')}")

        # 4. English Turn
        logger.log("\n[4/5] Executing Turn 2: Real English Speech with language_hint='en'")
        english_events = await run_turn(
            logger=logger,
            audio_path="tests/samples/english_speech_16k.wav",
            lang_hint="en",
            label="English",
        )
        english_speech = next((e for e in english_events if e.get("type") == "speech_result"), None)
        assert english_speech is not None, "English turn did not produce speech_result"
        logger.log(f"English Transcript: {english_speech.get('transcript')}")
        logger.log(f"English Language: {english_speech.get('language')}")
        logger.log(f"English Emotion: {english_speech.get('emotion')}")

        logger.log("\n[5/5] Real-model verification completed successfully!")
        logger.log(f"Untrimmed run log saved to: {OUTPUT_LOG.resolve()}")
        return 0

    finally:
        logger.log("\nShutting down backend process (PID: %s)..." % proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=10.0)
            logger.log("Backend process exited cleanly.")
        except subprocess.TimeoutExpired:
            logger.log("Backend did not exit within 10s. Killing process...")
            proc.kill()
            proc.wait()
            logger.log("Backend process killed.")
        try:
            server_log.close()
        except Exception:
            pass
        logger.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

