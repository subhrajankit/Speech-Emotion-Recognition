import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("senseai.telemetry")

@dataclass
class StageTiming:
    """
    Per-stage latency and milestone timings for an utterance request:
    - audio_received: ISO timestamp when audio frame buffer arrived
    - vad: Silero Voice Activity Detection processing time (ms)
    - asr: Language routing and speech recognition time (ms)
    - emotion: SER acoustic + lexical emotion classification time (ms)
    - router: Intent router classification gate time (ms)
    - rag: Knowledge retrieval time (ms) (0.0 if chat or bypassed)
    - llm_ttft: Time to first token from LLM (ms)
    - llm_total: Total time for LLM completion stream (ms)
    - tts_ttfa: Time to first audio chunk from TTS (ms)
    - total: Total request lifecycle duration (ms)
    """
    audio_received: str
    vad: float
    asr: float
    emotion: float
    router: float
    rag: float
    llm_ttft: float
    llm_total: float
    tts_ttfa: float
    total: float
    conversation_id: str = ""
    transcript: str = ""
    intent: str = "chat"
    language: str = "en"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps({
            "event": "stage_timing",
            **self.to_dict()
        })


class BenchmarkCollector:
    """
    Thread-safe in-memory ring buffer capturing per-stage timing metrics
    for the last N requests. Emits structured JSON log lines for observability scrapers.
    """
    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self._buffer: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record(self, timing: StageTiming) -> Dict[str, Any]:
        """
        Stores timing in ring buffer and outputs a structured JSON log entry.
        """
        timing_dict = timing.to_dict()
        with self._lock:
            self._buffer.append(timing_dict)

        # Log as structured JSON per request
        logger.info(timing.to_json())
        return timing_dict

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieves the last `limit` recorded stage timings (newest first).
        """
        with self._lock:
            items = list(self._buffer)
        items.reverse()
        return items[:limit]

    def get_summary(self) -> Dict[str, Any]:
        """
        Computes aggregate latency statistics (min, avg, max, p95) across all recorded requests.
        """
        with self._lock:
            items = list(self._buffer)

        if not items:
            return {
                "count": 0,
                "capacity": self.capacity,
                "stages": {},
                "summary": "No requests recorded yet."
            }

        count = len(items)
        stages = ["vad", "asr", "emotion", "router", "rag", "llm_ttft", "llm_total", "tts_ttfa", "total"]
        stats: Dict[str, Dict[str, float]] = {}

        for stage in stages:
            values = [float(item.get(stage, 0.0)) for item in items]
            values.sort()
            p95_idx = int(round(0.95 * (len(values) - 1)))
            stats[stage] = {
                "min_ms": round(values[0], 2),
                "avg_ms": round(sum(values) / count, 2),
                "max_ms": round(values[-1], 2),
                "p95_ms": round(values[p95_idx], 2)
            }

        return {
            "count": count,
            "capacity": self.capacity,
            "stages": stats,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def clear(self):
        """
        Clears stored metrics history.
        """
        with self._lock:
            self._buffer.clear()

# Global singleton benchmark collector
benchmark_collector = BenchmarkCollector(capacity=100)
