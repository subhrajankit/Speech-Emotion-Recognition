import asyncio
import json
import time
import websockets
import soundfile as sf
import numpy as np

WAV_PATH = "tests/samples/english_speech_16k.wav"
WS_URL = "ws://127.0.0.1:8000/ws/speech"

async def run_voice_turn():
    data, sr = sf.read(WAV_PATH, dtype="int16")
    dur = len(data) / sr
    print(f"Loaded {WAV_PATH}: {len(data)} samples, {sr}Hz, duration: {dur:.2f}s", flush=True)

    pcm_bytes = data.tobytes()
    chunk_size = int(sr * 0.02 * 2)  # 20ms = 320 samples = 640 bytes

    events_received = []

    print(f"Connecting to {WS_URL}...", flush=True)
    async with websockets.connect(WS_URL) as ws:
        # 1. Start handshake
        await ws.send(json.dumps({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en"
        }))

        # 2. Receive listener task
        done_event = asyncio.Event()

        async def listener():
            try:
                while True:
                    msg = await ws.recv()
                    t = time.perf_counter()
                    if isinstance(msg, bytes):
                        print(f"[{t:.3f}] (BINARY) Received audio bytes: {len(msg)} bytes", flush=True)
                        events_received.append({"type": "binary_audio", "bytes": len(msg), "time": t})
                    else:
                        payload = json.loads(msg)
                        m_type = payload.get("type")
                        print(f"[{t:.3f}] Received event: {payload}", flush=True)
                        events_received.append({"event": payload, "time": t})
                        if m_type in ("tts_done", "error"):
                            done_event.set()
                            break
            except Exception as e:
                print(f"Listener error / disconnect: {e}", flush=True)
                done_event.set()

        listen_task = asyncio.create_task(listener())

        # 3. Stream audio chunks in real-time pace
        print("Streaming audio frames...", flush=True)
        for i in range(0, len(pcm_bytes), chunk_size):
            chunk = pcm_bytes[i:i + chunk_size]
            await ws.send(chunk)
            await asyncio.sleep(0.02)  # simulate real-time

        # 4. Stop turn
        print("Sending stop frame...", flush=True)
        await ws.send(json.dumps({"type": "stop"}))

        # 5. Wait for turn completion (up to 45 seconds)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            print("Timed out waiting for turn completion", flush=True)

        listen_task.cancel()

    print("\n=== SUMMARY OF RECEIVED EVENTS ===")
    for ev in events_received:
        if "event" in ev:
            print(f"- {ev['event'].get('type')}: {ev['event']}")
        else:
            print(f"- BINARY AUDIO: {ev['bytes']} bytes")

if __name__ == "__main__":
    asyncio.run(run_voice_turn())
