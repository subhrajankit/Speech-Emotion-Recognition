"""
Service-level tests for Tier-2 LID integration in SpeechService.

Verifies configuration gating (LID_ENABLED), detector injection into
LanguageRouter, hint precedence, fallback preservation, and that routing
(including LID inference) never blocks the asyncio event loop.
All model inference is mocked — no torch/speechbrain required.
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from ai.routing.language_identifier import VoxLingua107LanguageIdentifier
from ai.routing.language_router import LanguageRouter, RoutingDecision
from backend.app.core.config import settings
from backend.app.services.speech_service import SpeechService, speech_service
from tests.test_doubles import FakeSenseVoiceEngine, FakeIndicConformerEngine


@pytest.fixture(autouse=True)
def _multilingual_asr_mode(monkeypatch):
    """LID/service routing tests exercise multilingual mode explicitly."""
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", False)


def _fresh_service() -> SpeechService:
    """Builds a SpeechService with fake engines and no real model loads."""
    service = SpeechService()
    fake_sv = FakeSenseVoiceEngine()
    fake_ic = FakeIndicConformerEngine()
    service._sensevoice = fake_sv
    service._indicconformer = fake_ic
    service._engine = fake_sv
    service._router = LanguageRouter(
        default_engine="sensevoice",
        default_language="en",
        lid_confidence_threshold=settings.LID_CONFIDENCE_THRESHOLD,
    )
    service._init_error = None
    service._indic_init_error = None
    service._is_initialized = True
    return service


def _fake_model_dir(tmp_path: Path) -> Path:
    for name in VoxLingua107LanguageIdentifier.REQUIRED_FILES:
        (tmp_path / name).write_bytes(b"")
    return tmp_path


# ----------------------------------------------------------------------
# Configuration gating
# ----------------------------------------------------------------------

def test_lid_disabled_by_default_leaves_detector_unwired():
    """Default settings: LID_ENABLED=false → router.lid_detector is None."""
    assert settings.LID_ENABLED is False
    service = _fresh_service()
    assert service.router.lid_detector is None


def test_initialize_with_lid_disabled_injects_no_detector(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LID_ENABLED", False)
    service = SpeechService()
    service.initialize()
    assert service.router is not None
    assert service.router.lid_detector is None


def test_initialize_with_lid_enabled_injects_detector(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LID_ENABLED", True)
    monkeypatch.setattr(settings, "LID_MODEL_DIR", str(_fake_model_dir(tmp_path)))
    service = SpeechService()
    service.initialize()
    assert service.router is not None
    assert isinstance(service.router.lid_detector, VoxLingua107LanguageIdentifier)
    # LAZY_LOAD_MODELS=true (default) → detector must not be loaded eagerly.
    assert service.router.lid_detector.is_loaded is False


def test_initialize_with_lid_enabled_but_missing_artifacts_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LID_ENABLED", True)
    monkeypatch.setattr(settings, "LID_MODEL_DIR", str(tmp_path))  # empty dir
    service = SpeechService()
    service.initialize()
    assert service.router is not None
    assert service.router.lid_detector is None  # safe fallback, hint/default only


# ----------------------------------------------------------------------
# Routing behavior through SpeechService
# ----------------------------------------------------------------------

def test_explicit_hint_takes_precedence_over_lid_detector():
    service = _fresh_service()
    detector = Mock(spec=VoxLingua107LanguageIdentifier)
    detector.identify.return_value = ("en", 0.99)
    service._router.lid_detector = detector

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
        language_hint="hi",
    )
    assert engine_name == "indicconformer"
    assert decision.source == "hint"
    detector.identify.assert_not_called()


def test_lid_detection_routes_to_indicconformer():
    service = _fresh_service()
    detector = Mock(spec=VoxLingua107LanguageIdentifier)
    detector.identify.return_value = ("hi", 0.9)
    service._router.lid_detector = detector

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
    )
    assert engine_name == "indicconformer"
    assert decision.source == "detected"
    assert decision.language == "hi"


def test_lid_low_confidence_falls_back_to_sensevoice():
    service = _fresh_service()
    detector = Mock(spec=VoxLingua107LanguageIdentifier)
    detector.identify.return_value = ("hi", 0.3)
    service._router.lid_detector = detector

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
    )
    assert engine_name == "sensevoice"
    assert decision.source == "default"


def test_lid_detector_error_falls_back_to_default():
    service = _fresh_service()
    detector = Mock(spec=VoxLingua107LanguageIdentifier)
    detector.identify.side_effect = RuntimeError("boom")
    service._router.lid_detector = detector

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
    )
    assert engine_name == "sensevoice"
    assert decision.source == "default"


# ----------------------------------------------------------------------
# Async safety: routing must not block the event loop
# ----------------------------------------------------------------------

class _SlowRouter:
    """Router double whose route() simulates a slow synchronous LID pass."""

    def __init__(self, delay_s: float = 0.3):
        self.delay_s = delay_s

    def route(self, audio=None, sample_rate=16000, language_hint=None):
        time.sleep(self.delay_s)
        return RoutingDecision(
            language="en",
            confidence=None,
            engine="sensevoice",
            source="default",
            debug={"policy": "test_slow_router"},
        )


@pytest.mark.asyncio
async def test_transcribe_array_routing_does_not_block_event_loop():
    service = _fresh_service()
    service._router = _SlowRouter(delay_s=0.3)

    ticks = 0
    stop = False

    async def ticker():
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0.01)

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await service.transcribe_array(
            audio=np.ones(16000, dtype=np.float32),
        )
        assert result.transcript
    finally:
        stop = True
        await ticker_task

    # A 0.3s blocking route() on the loop would allow ~1-2 ticks; off-loop
    # execution yields ~30 ticks at 10ms intervals.
    assert ticks > 10, f"event loop appears blocked during routing (ticks={ticks})"
