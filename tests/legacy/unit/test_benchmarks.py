import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.config import settings
from src.backend.telemetry import StageTiming, BenchmarkCollector, benchmark_collector
from src.backend.pipeline.orchestrator import VoicePipeline

@pytest.fixture(autouse=True)
def setup_mock_environment():
    settings.MOCK_MODELS = True
    benchmark_collector.clear()

def test_stage_timing_dataclass_and_json():
    timing = StageTiming(
        audio_received="2026-09-14T12:00:00Z",
        vad=1.5,
        asr=120.0,
        emotion=15.0,
        router=0.8,
        rag=0.0,
        llm_ttft=110.0,
        llm_total=350.0,
        tts_ttfa=180.0,
        total=540.0,
        conversation_id="conv_test_123",
        transcript="Hello assistant",
        intent="chat",
        language="en"
    )

    data = timing.to_dict()
    assert data["vad"] == 1.5
    assert data["asr"] == 120.0
    assert data["intent"] == "chat"
    assert data["total"] == 540.0

    raw_json = timing.to_json()
    parsed = json.loads(raw_json)
    assert parsed["event"] == "stage_timing"
    assert parsed["llm_ttft"] == 110.0
    assert parsed["conversation_id"] == "conv_test_123"

def test_benchmark_collector_ring_buffer_and_stats():
    collector = BenchmarkCollector(capacity=3)

    for i in range(5):
        t = StageTiming(
            audio_received=f"2026-09-14T12:0{i}:00Z",
            vad=1.0,
            asr=100.0 + i * 10,
            emotion=10.0,
            router=1.0,
            rag=0.0,
            llm_ttft=50.0,
            llm_total=200.0,
            tts_ttfa=80.0,
            total=300.0 + i * 10,
            conversation_id=f"conv_{i}"
        )
        collector.record(t)

    # Capacity is 3, so only the last 3 items should remain
    recent = collector.get_recent(limit=10)
    assert len(recent) == 3
    # Ordered newest first
    assert recent[0]["conversation_id"] == "conv_4"
    assert recent[1]["conversation_id"] == "conv_3"
    assert recent[2]["conversation_id"] == "conv_2"

    summary = collector.get_summary()
    assert summary["count"] == 3
    assert "asr" in summary["stages"]
    # asr values in buffer: 120, 130, 140
    assert summary["stages"]["asr"]["min_ms"] == 120.0
    assert summary["stages"]["asr"]["avg_ms"] == 130.0
    assert summary["stages"]["asr"]["max_ms"] == 140.0

def test_benchmark_api_endpoints():
    client = TestClient(app)

    # Seed one timing record
    timing = StageTiming(
        audio_received="2026-09-14T12:00:00Z",
        vad=2.0,
        asr=95.0,
        emotion=8.0,
        router=0.5,
        rag=12.0,
        llm_ttft=85.0,
        llm_total=220.0,
        tts_ttfa=130.0,
        total=350.0,
        conversation_id="conv_api_seed",
        transcript="Test query",
        intent="knowledge"
    )
    benchmark_collector.record(timing)

    # Test GET /api/benchmark/metrics
    metrics_res = client.get("/api/benchmark/metrics?limit=10")
    assert metrics_res.status_code == 200
    metrics_data = metrics_res.json()
    assert len(metrics_data) >= 1
    assert metrics_data[0]["conversation_id"] == "conv_api_seed"
    assert metrics_data[0]["rag"] == 12.0

    # Test GET /api/benchmark/summary
    summary_res = client.get("/api/benchmark/summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert summary_data["count"] >= 1
    assert summary_data["stages"]["total"]["max_ms"] >= 350.0

    # Test POST /api/benchmark/reset
    reset_res = client.post("/api/benchmark/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "cleared"

    # Verify cleared
    summary_after = client.get("/api/benchmark/summary").json()
    assert summary_after["count"] == 0

@pytest.mark.asyncio
async def test_pipeline_records_stage_timing_on_completion():
    pipeline = VoicePipeline()
    mock_pcm = np.random.randint(-500, 500, 16000, dtype=np.int16).tobytes()

    benchmark_collector.clear()
    events = []
    async for event_type, payload in pipeline.stream_utterance(mock_pcm, conversation_id="conv_pipeline_telemetry"):
        events.append((event_type, payload))

    event_types = [e[0] for e in events]
    assert "complete" in event_types

    # Find the complete event
    complete_payload = [e[1] for e in events if e[0] == "complete"][0]
    assert "stage_timing" in complete_payload
    stage_timing = complete_payload["stage_timing"]
    assert stage_timing["conversation_id"] == "conv_pipeline_telemetry"
    assert "audio_received" in stage_timing
    assert "asr" in stage_timing
    assert "llm_ttft" in stage_timing
    assert "total" in stage_timing

    # Verify recorded in collector
    recorded = benchmark_collector.get_recent(limit=5)
    assert len(recorded) >= 1
    assert recorded[0]["conversation_id"] == "conv_pipeline_telemetry"
