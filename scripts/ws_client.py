"""
Standalone WebSocket streaming test client for VoiceSense AI.
Streams a WAV audio file in small chunks over /ws/speech and prints all server events in order.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
import numpy as np
import soundfile as sf
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ws_client")


async def receive_events(ws, stop_event: asyncio.Event, wait_for_tts: bool = False):
    """Continuously listens for and prints server events."""
    try:
        async for message in ws:
            if isinstance(message, str):
                try:
                    event = json.loads(message)
                    event_type = event.get("type", "unknown")
                    print(f"\n[SERVER EVENT: {event_type.upper()}]")
                    print(json.dumps(event, indent=2))
                    if event_type == "error":
                        stop_event.set()
                except json.JSONDecodeError:
                    print(f"\n[SERVER TEXT] {message}")
            else:
                print(f"\n[SERVER BINARY AUDIO] Received {len(message)} bytes WAV frame")
    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket connection closed by server.")
    except Exception as e:
        logger.error(f"Error receiving message: {e}")
    finally:
        stop_event.set()



async def stream_wav(
    url: str,
    wav_path: str,
    chunk_samples: int = 512,
    chunk_delay: float = 0.032,
    language_hint: str = None,
    token: str = None,
    timeout: float = 15.0,
    wait_for_tts: bool = False,
):
    """
    Connects to WebSocket, sends start message, streams audio chunks, and prints responses.
    """
    path = Path(wav_path)
    if not path.exists():
        logger.error(f"File not found: {wav_path}")
        sys.exit(1)

    # Load audio and convert to 16kHz mono PCM16
    audio_data, sr = sf.read(str(path), dtype="float32")
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=-1)

    if sr != 16000:
        # Simple linear resample to 16000
        num_target = int(len(audio_data) * 16000 / sr)
        audio_data = np.interp(
            np.linspace(0, len(audio_data), num_target, endpoint=False),
            np.arange(len(audio_data)),
            audio_data
        ).astype(np.float32)
        sr = 16000

    # Convert float32 in [-1.0, 1.0] to int16 PCM bytes
    pcm_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767.0).astype(np.int16)
    pcm_bytes = pcm_int16.tobytes()

    target_url = url
    if token:
        target_url = f"{url}?token={token}"

    logger.info(f"Connecting to {target_url}...")
    async with websockets.connect(target_url) as ws:
        stop_event = asyncio.Event()
        recv_task = asyncio.create_task(receive_events(ws, stop_event, wait_for_tts=wait_for_tts))

        # 1. Send start frame
        start_msg = {
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": language_hint
        }
        logger.info(f"Sending start frame: {start_msg}")
        await ws.send(json.dumps(start_msg))

        # Small delay to allow ready response
        await asyncio.sleep(0.05)

        # 2. Stream audio in small chunks
        bytes_per_chunk = chunk_samples * 2  # 2 bytes per int16 sample
        total_chunks = len(pcm_bytes) // bytes_per_chunk
        logger.info(f"Streaming {len(pcm_bytes)} bytes ({total_chunks} chunks of {bytes_per_chunk} bytes)...")

        for i in range(0, len(pcm_bytes), bytes_per_chunk):
            chunk = pcm_bytes[i : i + bytes_per_chunk]
            await ws.send(chunk)
            if chunk_delay > 0:
                await asyncio.sleep(chunk_delay)

        logger.info("Finished streaming audio frames. Sending stop frame...")
        # 3. Send stop frame
        stop_msg = {"type": "stop"}
        await ws.send(json.dumps(stop_msg))

        # 4. Wait for responses to settle after stop
        logger.info(f"Waiting up to {timeout}s for server processing and final turn to complete...")
        # Wait a few seconds to let VAD flush, ASR, and LLM complete
        wait_start = time.time()
        while time.time() - wait_start < timeout:
            if stop_event.is_set():
                break
            await asyncio.sleep(0.5)

        # Brief delay to allow socket buffer completion
        await asyncio.sleep(1.0)

        # Cleanup
        recv_task.cancel()
        await asyncio.gather(recv_task, return_exceptions=True)
        logger.info("Session complete.")


def main():
    parser = argparse.ArgumentParser(description="VoiceSense AI WebSocket Test Client")
    default_wav = "tests/speech_sample.wav"
    try:
        sf.info("tests/speech_sample.wav")
    except Exception:
        default_wav = "tests/samples/sample_chinese_speech.wav"

    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/speech", help="WebSocket server URL")
    parser.add_argument("--wav", default=default_wav, help="Path to WAV audio file")
    parser.add_argument("--chunk-samples", type=int, default=512, help="Samples per chunk (default: 512 / 32ms)")
    parser.add_argument("--chunk-delay", type=float, default=0.032, help="Delay between chunks in seconds (default: 0.032)")
    parser.add_argument("--language-hint", default=None, help="Optional ISO language code")
    parser.add_argument("--token", default=None, help="Optional JWT token")
    parser.add_argument("--timeout", type=float, default=30.0, help="Response timeout in seconds")
    parser.add_argument("--wait-for-tts", action="store_true", help="Wait for tts_done event instead of llm_done")

    args = parser.parse_args()

    asyncio.run(stream_wav(
        url=args.url,
        wav_path=args.wav,
        chunk_samples=args.chunk_samples,
        chunk_delay=args.chunk_delay,
        language_hint=args.language_hint,
        token=args.token,
        timeout=args.timeout,
        wait_for_tts=args.wait_for_tts,
    ))


if __name__ == "__main__":
    main()
