"""
Unit tests for Emotion2Vec integration in SpeechService.
Verifies:
1. Feature flag OFF (EMOTION2VEC_ENABLED=False) baseline preservation with zero regression.
2. Feature flag ON with dedicated_primary routing strategy.
3. Feature flag ON with hybrid_fallback routing strategy.
4. Threshold-gated and unsupported label mapping to None (Unknown in UI).
5. Fault isolation: emotion2vec inference crash preserves ASR transcript.
6. Health status reporting for SER component.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock

from ai.inference.types import SpeechResult
from ai.inference.emotion import EmotionResult
from backend.app.core.config import settings
from backend.app.services.speech_service import SpeechService
from tests.test_doubles import FakeSenseVoiceEngine


class FakeEmotion2VecEngineDouble:
    """Test double simulating Emotion2VecSpeechEngine."""

    def __init__(
        self,
        primary: str = "angry",
        confidence: float = 0.88,
        scores: dict = None,
        raw_label: str = "angry",
        should_raise: bool = False,
    ):
        self.primary = primary
        self.confidence = confidence
        self.scores = scores or {"angry": 0.88, "neutral": 0.12}
        self.raw_label = raw_label
        self.should_raise = should_raise
        self.is_loaded = True
        self.model_version = "emotion2vec_plus_base"
        self.call_count = 0

    def load(self):
        self.is_loaded = True

    def classify(self, audio, sample_rate=16000) -> EmotionResult:
        self.call_count += 1
        if self.should_raise:
            raise RuntimeError("Simulated Emotion2Vec inference crash")
        return EmotionResult(
            primary=self.primary,
            confidence=self.confidence,
            scores=self.scores,
            processing_time_ms=42.5,
            model_version=self.model_version,
            raw_label=self.raw_label,
        )


@pytest.fixture
def dummy_audio():
    # 1 second of 16kHz sine wave audio
    t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
    return 0.1 * np.sin(2 * np.pi * 440 * t)


@pytest.fixture
def service():
    srv = SpeechService()
    # Inject fake SenseVoice engine directly
    srv._sensevoice = FakeSenseVoiceEngine(
        simulated_transcript="Test speech transcript",
        simulated_language="en",
        simulated_emotion="neutral",
    )
    srv._engine = srv._sensevoice
    srv._is_initialized = True
    return srv


@pytest.mark.asyncio
async def test_feature_flag_off_preserves_baseline(service, dummy_audio, monkeypatch):
    """When EMOTION2VEC_ENABLED=False, SenseVoice output is untouched."""
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", False)

    result = await service.transcribe_array(dummy_audio, sample_rate=16000)

    assert result.transcript == "Test speech transcript"
    assert result.emotion == "neutral"
    assert result.debug.get("emotion_source_model") == "sensevoice"
    assert result.debug.get("is_fallback") is False


@pytest.mark.asyncio
async def test_feature_flag_on_dedicated_primary(service, dummy_audio, monkeypatch):
    """When EMOTION2VEC_ENABLED=True & dedicated_primary, Emotion2Vec overrides emotion."""
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", True)
    monkeypatch.setattr(settings, "EMOTION_ROUTING_STRATEGY", "dedicated_primary")

    fake_ser = FakeEmotion2VecEngineDouble(
        primary="angry",
        confidence=0.88,
        scores={"angry": 0.88, "neutral": 0.12},
        raw_label="angry",
    )
    service._emotion2vec = fake_ser

    result = await service.transcribe_array(dummy_audio, sample_rate=16000)

    assert result.transcript == "Test speech transcript"
    assert result.emotion == "angry"
    assert result.confidence == 0.88
    assert result.emotion_scores == {"angry": 0.88, "neutral": 0.12}
    assert result.debug.get("emotion_source_model") == "emotion2vec_plus_base"
    assert result.debug.get("emotion_raw_label") == "angry"
    assert result.debug.get("emotion_processing_time_ms") == 42.5
    assert result.debug.get("is_fallback") is False
    assert fake_ser.call_count == 1


@pytest.mark.asyncio
async def test_feature_flag_on_maps_unknown_to_none(service, dummy_audio, monkeypatch):
    """When Emotion2Vec returns 'unknown', SpeechResult.emotion is mapped to None."""
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", True)
    monkeypatch.setattr(settings, "EMOTION_ROUTING_STRATEGY", "dedicated_primary")

    fake_ser = FakeEmotion2VecEngineDouble(
        primary="unknown",
        confidence=0.45,
        scores={"other": 0.45, "neutral": 0.30},
        raw_label="other",
    )
    service._emotion2vec = fake_ser

    result = await service.transcribe_array(dummy_audio, sample_rate=16000)

    assert result.emotion is None
    assert result.confidence == 0.45
    assert result.debug.get("emotion_source_model") == "emotion2vec_plus_base"
    assert result.debug.get("emotion_raw_label") == "other"


@pytest.mark.asyncio
async def test_hybrid_fallback_skips_when_sensevoice_valid(service, dummy_audio, monkeypatch):
    """In hybrid_fallback mode, Emotion2Vec is NOT called if SenseVoice has an emotion."""
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", True)
    monkeypatch.setattr(settings, "EMOTION_ROUTING_STRATEGY", "hybrid_fallback")

    # SenseVoice returns "happy"
    service._sensevoice._simulated_emotion = "happy"
    fake_ser = FakeEmotion2VecEngineDouble(primary="angry")
    service._emotion2vec = fake_ser

    result = await service.transcribe_array(dummy_audio, sample_rate=16000)

    assert result.emotion == "happy"
    assert fake_ser.call_count == 0


@pytest.mark.asyncio
async def test_hybrid_fallback_triggers_when_sensevoice_is_none(service, dummy_audio, monkeypatch):
    """In hybrid_fallback mode, Emotion2Vec triggers when SenseVoice returns None."""
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", True)
    monkeypatch.setattr(settings, "EMOTION_ROUTING_STRATEGY", "hybrid_fallback")

    # SenseVoice returns None (simulating <|EMO_UNKNOWN|>)
    service._sensevoice._simulated_emotion = None
    fake_ser = FakeEmotion2VecEngineDouble(primary="sad", confidence=0.78, raw_label="sad")
    service._emotion2vec = fake_ser

    result = await service.transcribe_array(dummy_audio, sample_rate=16000)

    assert result.emotion == "sad"
    assert result.confidence == 0.78
    assert result.debug.get("is_fallback") is True
    assert fake_ser.call_count == 1


@pytest.mark.asyncio
async def test_fault_isolation_on_emotion2vec_failure(service, dummy_audio, monkeypatch):
    """If Emotion2Vec crashes, SpeechResult transcript is preserved and error is recorded."""
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", True)
    monkeypatch.setattr(settings, "EMOTION_ROUTING_STRATEGY", "dedicated_primary")

    fake_ser = FakeEmotion2VecEngineDouble(should_raise=True)
    service._emotion2vec = fake_ser

    result = await service.transcribe_array(dummy_audio, sample_rate=16000)

    # Transcript remains valid
    assert result.transcript == "Test speech transcript"
    assert result.debug.get("emotion_error") == "Simulated Emotion2Vec inference crash"
    assert result.debug.get("emotion_source_model") == "sensevoice_fallback"
    assert result.debug.get("is_fallback") is True


def test_health_status_reporting(service, monkeypatch):
    """get_health_status() reports correct emotion telemetry."""
    # When disabled
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", False)
    status_off = service.get_health_status()
    assert status_off["components"]["emotion"] == "ok"
    assert status_off["details"]["emotion2vec_enabled"] is False

    # When enabled and healthy
    monkeypatch.setattr(settings, "EMOTION2VEC_ENABLED", True)
    service._emotion2vec = FakeEmotion2VecEngineDouble()
    status_on = service.get_health_status()
    assert status_on["components"]["emotion"] == "ok"
    assert status_on["details"]["emotion2vec_enabled"] is True
    assert status_on["details"]["emotion2vec_loaded"] is True
