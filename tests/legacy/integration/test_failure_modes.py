"""
Integration Tests for Phase 14: Error Handling & Resilience.

Validates:
1. llama.cpp downtime simulation: retry-with-backoff, fast-fail on circuit breaker trip.
2. Circuit breaker state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
3. TTS neural generation failure: retry and graceful fallback to synthesized audio.
4. IndicConformer failure to load: graceful degradation to SenseVoice English/global.
5. RAG missing/corrupt index: graceful fallback from KNOWLEDGE intent to CHAT.
6. GPU concurrency limiter: queues concurrent voice turns under constrained semaphore.
7. WebSocket voice turn resilience: returns clean response rather than hanging or 500ing.
"""

import asyncio
import json
import sys
import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend.config import settings
from src.backend.models.manager import model_manager
from src.backend.models.llm import LlamaCppClient
from src.backend.llm.circuit_breaker import CircuitBreaker, CircuitState
from src.backend.tts.indic_parler import IndicParlerTTS
from src.backend.asr.router import LanguageRouter, AudioContext
from src.backend.pipeline.intent import IntentRouter, IntentCategory
from src.backend.pipeline.concurrency import GPUConcurrencyLimiter


@pytest.mark.asyncio
async def test_llm_downtime_retry_and_circuit_breaker():
    """
    Simulates llama.cpp server downtime (unreachable port).
    Asserts retry-with-backoff occurs, then circuit breaker trips to OPEN
    after N consecutive failures and subsequently fast-fails.
    """
    cb = CircuitBreaker(name="test_llama", failure_threshold=3, cooldown_seconds=0.5)
    client = LlamaCppClient(
        base_url="http://127.0.0.1:59999/v1",
        model_name="qwen3-1.7b",
        timeout=0.1,
        mock=False,
        max_retries=2,
        backoff_factor=0.01,
        circuit_breaker=cb
    )
    cb.reset()

    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0

    # Request 1: fails after retries -> failure_count = 1
    tokens_1 = []
    async for tok in client.stream_response("Hello"):
        tokens_1.append(tok)
    resp_1 = "".join(tokens_1)
    assert "temporarily unavailable" in resp_1
    assert cb.failure_count == 1
    assert cb.state == CircuitState.CLOSED

    # Request 2: fails after retries -> failure_count = 2
    tokens_2 = []
    async for tok in client.stream_response("Hello again"):
        tokens_2.append(tok)
    resp_2 = "".join(tokens_2)
    assert "temporarily unavailable" in resp_2
    assert cb.failure_count == 2
    assert cb.state == CircuitState.CLOSED

    # Request 3: fails after retries -> failure_count = 3 -> trips to OPEN
    tokens_3 = []
    async for tok in client.stream_response("Hello 3"):
        tokens_3.append(tok)
    resp_3 = "".join(tokens_3)
    assert "temporarily unavailable" in resp_3
    assert cb.failure_count == 3
    assert cb.state == CircuitState.OPEN

    # Request 4: Circuit is OPEN -> must fast-fail immediately without network delay
    t_fast_start = time.perf_counter()
    tokens_4 = []
    async for tok in client.stream_response("Hello 4 while OPEN"):
        tokens_4.append(tok)
    fast_duration = time.perf_counter() - t_fast_start

    resp_4 = "".join(tokens_4)
    assert "temporarily unavailable" in resp_4
    assert fast_duration < 0.05, f"Expected fast-fail (<50ms), got {fast_duration*1000:.2f}ms"


def test_circuit_breaker_transitions():
    """
    Tests explicit CLOSED -> OPEN -> HALF_OPEN -> CLOSED state lifecycle.
    """
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, cooldown_seconds=0.1)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 1. First failure
    cb.record_failure(RuntimeError("Failure 1"))
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 2. Second failure trips circuit
    cb.record_failure(RuntimeError("Failure 2"))
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False
    assert cb.get_remaining_cooldown() > 0.0

    # 3. Wait for cooldown to expire
    time.sleep(0.12)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # 4. Probe succeeds -> transitions to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_tts_retry_and_fallback_audio():
    """
    Tests that TTS neural failure retries and gracefully falls back to harmonic
    synthesizer rather than raising unhandled exceptions.
    """
    tts = IndicParlerTTS(mock=False, max_retries=1, backoff_ms=5)

    mock_torch = MagicMock()
    mock_model = MagicMock()
    mock_model.generate.side_effect = RuntimeError("CUDA OOM simulated")
    tts.model = mock_model
    tts.tokenizer = MagicMock()
    tts.tokenizer.return_value = MagicMock(input_ids=MagicMock(to=MagicMock(return_value="dummy")))

    with patch.dict(sys.modules, {"torch": mock_torch}):
        wav_bytes = tts.synthesize_wav("Hello testing resilience fallback")
        assert isinstance(wav_bytes, bytes)
        assert len(wav_bytes) > 44
        assert wav_bytes[:4] == b"RIFF"  # Valid WAV header from harmonic tone fallback
        assert mock_model.generate.call_count == 2  # 1 initial attempt + 1 retry


def test_indic_conformer_load_failure_graceful_degradation():
    """
    Tests that if IndicConformer is unavailable/None, LanguageRouter logs
    warning and serves transcription via SenseVoice without crashing.
    """
    router = LanguageRouter(
        sensevoice_asr=model_manager.asr,
        indic_conformer=None
    )

    # Transcript routing check
    ctx = router.route_transcript("नमस्ते, आप कैसे हैं?", detected_lang="hi")
    assert ctx is not None
    assert ctx.model_used == "sensevoice"  # Degraded from indicconformer

    # Audio routing check
    dummy_audio = b"\x00" * 3200
    audio_ctx = router.route_audio(dummy_audio)
    assert audio_ctx is not None
    assert audio_ctx.language in ["en", "hi"]


def test_rag_missing_index_fallback_to_chat():
    """
    Tests that if the FAISS index is missing or unloaded, IntentRouter
    gracefully degrades 'knowledge' intent to 'chat' instead of erroring.
    """
    unloaded_retriever = MagicMock()
    unloaded_retriever.is_loaded = False

    router = IntentRouter(retriever=unloaded_retriever)

    # Query clearly matching knowledge pattern
    result = router.classify(
        "According to the company policy document, what is the leave policy?",
        retriever=unloaded_retriever
    )

    assert result.category == IntentCategory.CHAT
    assert "knowledge_fallback" in result.matched_rule


@pytest.mark.asyncio
async def test_gpu_concurrency_limiter_queuing():
    """
    Tests that GPUConcurrencyLimiter properly bounds concurrent operations
    and tracks queueing without deadlocking.
    """
    limiter = GPUConcurrencyLimiter(max_concurrent=1)
    execution_order = []

    async def task(idx: int):
        async with limiter:
            execution_order.append(f"start_{idx}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end_{idx}")

    # Launch two tasks simultaneously
    await asyncio.gather(task(1), task(2))

    # Because max_concurrent=1, tasks must execute serially: start_1 -> end_1 -> start_2 -> end_2
    assert execution_order == ["start_1", "end_1", "start_2", "end_2"] or \
           execution_order == ["start_2", "end_2", "start_1", "end_1"]
    assert limiter.total_acquired == 2


def test_websocket_pipeline_resilience_on_llm_outage(synthetic_speech_audio):
    """
    End-to-end WebSocket test simulating downstream LLM outage:
    verifies the WebSocket session completes gracefully and delivers an
    audible fallback response without hanging or returning an unhandled 500 error.
    """
    orig_mock = model_manager.llm.mock
    orig_base = model_manager.llm.base_url
    orig_retries = model_manager.llm.max_retries
    orig_backoff = model_manager.llm.backoff_factor

    try:
        model_manager.llm.mock = False
        model_manager.llm.base_url = "http://127.0.0.1:59998/v1"
        model_manager.llm.max_retries = 1
        model_manager.llm.backoff_factor = 0.01

        client = TestClient(app)
        with client.websocket_connect("/ws/voice") as ws:
            # Send audio frames
            chunk_size = 3200
            for offset in range(0, len(synthetic_speech_audio), chunk_size):
                ws.send_bytes(synthetic_speech_audio[offset:offset + chunk_size])

            # Trigger end of speech turn
            ws.send_json({"type": "end-of-utterance"})

            received_events = []
            received_audio_bytes = 0

            while True:
                msg = ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    received_audio_bytes += len(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    data = json.loads(msg["text"])
                    received_events.append(data.get("type"))
                    if data.get("type") in ("turn_complete", "result"):
                        break

            assert "status" in received_events
            assert "llm_start" in received_events
            assert "turn_complete" in received_events
            assert received_audio_bytes > 0

    finally:
        model_manager.llm.mock = orig_mock
        model_manager.llm.base_url = orig_base
        model_manager.llm.max_retries = orig_retries
        model_manager.llm.backoff_factor = orig_backoff
