import time
import numpy as np
from src.backend.config import settings
from src.backend.models.manager import model_manager
from src.backend.pipeline.orchestrator import VoicePipeline

settings.MOCK_MODELS = True
model_manager.initialize()
pipeline = VoicePipeline()

print("Measuring actual dev machine stage latencies...")
timings = []

mock_audio = np.random.randint(-1000, 1000, 16000, dtype=np.int16).tobytes()

import asyncio

async def run_benchmark():
    for i in range(10):
        t0 = time.perf_counter()
        events = []
        async for ev, payload in pipeline.stream_utterance(mock_audio, conversation_id=f"bench_{i}"):
            events.append((ev, payload))
        complete_ev = [p for e, p in events if e == "complete"][0]
        timings.append(complete_ev["stage_timing"])

    print("\n--- Measured Stage Timings (10 runs, mock mode) ---")
    stages = ["vad", "asr", "emotion", "router", "rag", "llm_ttft", "llm_total", "tts_ttfa", "total"]
    for s in stages:
        vals = [t[s] for t in timings]
        print(f"  {s:<12}: min={min(vals):.2f}ms, avg={sum(vals)/len(vals):.2f}ms, max={max(vals):.2f}ms")

asyncio.run(run_benchmark())
