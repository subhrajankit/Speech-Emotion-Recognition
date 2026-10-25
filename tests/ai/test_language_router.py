"""
Unit tests for LanguageRouter pure decision logic.
Verifies the 3-tier routing policy using hand-written LID outputs.
Tests decision logic without downloading or initializing heavy neural models.
"""

from typing import Tuple
import numpy as np
import pytest

from ai.routing.language_router import (
    LanguageRouter,
    RoutingDecision,
    LanguageIdentifier,
    INDIC_LANGUAGES,
    SENSEVOICE_LANGUAGES,
)


class MockLIDDetector(LanguageIdentifier):
    """Hand-written LID detector emitting predetermined language and confidence."""

    def __init__(self, predicted_lang: str, confidence: float):
        self.predicted_lang = predicted_lang
        self.confidence = confidence

    def identify(self, audio: np.ndarray, sample_rate: int = 16000) -> Tuple[str, float]:
        return self.predicted_lang, self.confidence


def test_explicit_hint_wins_indic():
    """Explicit Hindi/Indic language hint routes to IndicConformer with source='hint'."""
    router = LanguageRouter()
    decision = router.route(language_hint="hi")

    assert isinstance(decision, RoutingDecision)
    assert decision.language == "hi"
    assert decision.engine == "indicconformer"
    assert decision.source == "hint"
    assert decision.confidence == 1.0


def test_explicit_hint_wins_all_indic_languages():
    """All 22 scheduled Indian languages correctly route to IndicConformer."""
    router = LanguageRouter()
    for lang in INDIC_LANGUAGES:
        decision = router.route(language_hint=lang)
        assert decision.engine == "indicconformer", f"Language {lang} should route to indicconformer"
        assert decision.source == "hint"
        assert decision.language == lang


def test_explicit_hint_wins_sensevoice():
    """Explicit English/global language hint routes to SenseVoice with source='hint'."""
    router = LanguageRouter()
    for lang in SENSEVOICE_LANGUAGES:
        decision = router.route(language_hint=lang)
        assert decision.engine == "sensevoice", f"Language {lang} should route to sensevoice"
        assert decision.source == "hint"
        assert decision.language == lang


def test_explicit_hint_overrides_lid_detector():
    """Explicit client hint takes precedence over contradictory LID detection."""
    # LID says English with high confidence, but client requests Hindi hint
    detector = MockLIDDetector(predicted_lang="en", confidence=0.99)
    router = LanguageRouter(lid_detector=detector)

    dummy_audio = np.ones(16000, dtype=np.float32)
    decision = router.route(audio=dummy_audio, language_hint="hi")

    assert decision.language == "hi"
    assert decision.engine == "indicconformer"
    assert decision.source == "hint"


def test_unrecognized_hint_falls_back_to_default_engine():
    """Unknown language hint falls back to default engine (sensevoice) safely."""
    router = LanguageRouter(default_engine="sensevoice")
    decision = router.route(language_hint="xyz")

    assert decision.language == "xyz"
    assert decision.engine == "sensevoice"
    assert decision.source == "hint"
    assert decision.confidence is None
    assert decision.debug.get("policy") == "unrecognized_hint_fallback"


def test_lid_detection_above_threshold_indic():
    """When no hint is given, high-confidence Indic LID routes to IndicConformer."""
    detector = MockLIDDetector(predicted_lang="hi", confidence=0.85)
    router = LanguageRouter(lid_confidence_threshold=0.6, lid_detector=detector)

    dummy_audio = np.ones(16000, dtype=np.float32)
    decision = router.route(audio=dummy_audio, language_hint=None)

    assert decision.language == "hi"
    assert decision.engine == "indicconformer"
    assert decision.source == "detected"
    assert decision.confidence == 0.85


def test_lid_detection_above_threshold_sensevoice():
    """When no hint is given, high-confidence global language routes to SenseVoice."""
    detector = MockLIDDetector(predicted_lang="zh", confidence=0.92)
    router = LanguageRouter(lid_confidence_threshold=0.6, lid_detector=detector)

    dummy_audio = np.ones(16000, dtype=np.float32)
    decision = router.route(audio=dummy_audio, language_hint=None)

    assert decision.language == "zh"
    assert decision.engine == "sensevoice"
    assert decision.source == "detected"
    assert decision.confidence == 0.92


def test_lid_detection_below_threshold_falls_back():
    """When LID confidence is below threshold, routes to default engine."""
    detector = MockLIDDetector(predicted_lang="hi", confidence=0.45)
    router = LanguageRouter(
        default_engine="sensevoice",
        default_language="en",
        lid_confidence_threshold=0.6,
        lid_detector=detector
    )

    dummy_audio = np.ones(16000, dtype=np.float32)
    decision = router.route(audio=dummy_audio, language_hint=None)

    assert decision.language == "en"
    assert decision.engine == "sensevoice"
    assert decision.source == "default"
    assert decision.confidence is None


def test_no_hint_no_lid_routes_to_default():
    """When no hint and no LID detector are present, routes to default engine."""
    router = LanguageRouter(default_engine="sensevoice", default_language="en")
    decision = router.route(audio=None, language_hint=None)

    assert decision.language == "en"
    assert decision.engine == "sensevoice"
    assert decision.source == "default"
    assert decision.confidence is None


@pytest.mark.asyncio
async def test_indicconformer_failure_triggers_fallback_to_sensevoice():
    """
    Requirement 7: If IndicConformer fails during transcription,
    falls back to the default engine (SenseVoice) and reports the fallback in result.debug.
    """
    from unittest.mock import MagicMock
    from backend.app.services.speech_service import SpeechService
    from ai.inference.types import SpeechResult

    service = SpeechService()
    service._sensevoice = MagicMock()
    service._sensevoice.transcribe.return_value = SpeechResult(
        transcript="Hello from fallback SenseVoice",
        language="en",
        emotion="neutral",
        confidence=None,
        processing_time_ms=10,
        model_version="SenseVoiceSmall (mock)",
        debug={"status": "mock_inference"}
    )
    service._indicconformer = MagicMock()
    service._indicconformer.transcribe.side_effect = RuntimeError("Inference failed: CUDA OOM")
    service._router = LanguageRouter()
    service._engine = service._sensevoice
    service._is_initialized = True

    dummy_audio = np.ones(16000, dtype=np.float32)
    result = await service.transcribe_array(audio=dummy_audio, language_hint="hi")

    assert result.transcript == "Hello from fallback SenseVoice"
    assert result.debug is not None
    assert "fallback" in result.debug
    assert result.debug["fallback"]["from_engine"] == "indicconformer"
    assert result.debug["fallback"]["to_engine"] == "sensevoice"
    assert "Inference failed: CUDA OOM" in result.debug["fallback"]["error"]
    assert result.debug["routing"]["engine"] == "indicconformer"
    assert result.debug["routing"]["source"] == "hint"
