"""
Regression tests for ASR_ENGLISH_ONLY MVP mode.

Verifies deterministic SenseVoice routing, strict language-hint validation
across REST/WebSocket/service boundaries, and complete IndicConformer/LID
isolation — all with fakes/mocks only (no model downloads or inference).
"""

import sys
from unittest.mock import Mock

import numpy as np
import pytest

from ai.routing.language_router import LanguageRouter
from backend.app.core.config import Settings, settings
from backend.app.services.speech_service import (
    InvalidLanguageHintError,
    SpeechService,
    normalize_language_hint,
)
from tests.test_doubles import FakeIndicConformerEngine, FakeSenseVoiceEngine

speech_service_module = sys.modules["backend.app.services.speech_service"]


@pytest.fixture(autouse=True)
def _english_only_mode(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)


def _fresh_service() -> SpeechService:
    service = SpeechService()
    fake_sv = FakeSenseVoiceEngine()
    service._sensevoice = fake_sv
    service._engine = fake_sv
    service._router = LanguageRouter(default_engine="sensevoice", default_language="en")
    service._is_initialized = True
    service._init_error = None
    service._indic_init_error = None
    return service


# ----------------------------------------------------------------------
# Configuration + hint normalization
# ----------------------------------------------------------------------

def test_english_only_defaults_to_true():
    assert Settings.model_fields["ASR_ENGLISH_ONLY"].default is True
    assert settings.ASR_ENGLISH_ONLY is True


@pytest.mark.parametrize(
    "raw_hint,expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("auto", None),
        ("AUTO", None),
        (" auto ", None),
        ("en", "en"),
        ("EN", "en"),
        (" en ", "en"),
    ],
)
def test_english_only_accepts_neutral_and_english_hints(monkeypatch, raw_hint, expected):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    assert normalize_language_hint(raw_hint) == expected


@pytest.mark.parametrize("bad_hint", ["hi", "bn", "mr", "fr", "zh", "en-US", "hinglish", 123])
def test_english_only_rejects_all_other_hints(monkeypatch, bad_hint):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    with pytest.raises(InvalidLanguageHintError):
        normalize_language_hint(bad_hint)


def test_hint_normalization_preserves_multilingual_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", False)
    assert normalize_language_hint("hi") == "hi"
    assert normalize_language_hint(" fr ") == " fr "


# ----------------------------------------------------------------------
# Deterministic service routing
# ----------------------------------------------------------------------

@pytest.mark.parametrize("hint", [None, "", "   ", "auto", "AUTO", "en", " EN "])
def test_english_only_routes_accepted_hints_to_sensevoice(monkeypatch, hint):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    service = _fresh_service()
    service._router = Mock()
    service._router.route.side_effect = AssertionError("router must not be used")
    service._indicconformer = Mock()

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
        language_hint=hint,
    )

    assert engine_name == "sensevoice"
    assert engine is service._sensevoice
    assert decision.engine == "sensevoice"
    assert decision.language == "en"
    service._router.route.assert_not_called()
    service._indicconformer.transcribe.assert_not_called()


@pytest.mark.parametrize("bad_hint", ["hi", "bn", "fr"])
def test_english_only_service_rejects_indic_and_other_hints(monkeypatch, bad_hint):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    service = _fresh_service()
    with pytest.raises(InvalidLanguageHintError):
        service.get_engine_for_utterance(
            audio=np.ones(16000, dtype=np.float32),
            language_hint=bad_hint,
        )


def test_english_only_never_invokes_lid_even_if_detector_injected(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    service = _fresh_service()
    detector = Mock()
    detector.identify.return_value = ("hi", 0.99)
    service._router.lid_detector = detector

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
    )

    assert engine_name == "sensevoice"
    assert decision.engine == "sensevoice"
    assert decision.source == "default"
    detector.identify.assert_not_called()


@pytest.mark.asyncio
async def test_english_only_transcribe_never_touches_indicconformer(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    service = _fresh_service()
    indic = Mock()
    indic.is_loaded = True
    service._indicconformer = indic

    result = await service.transcribe_array(
        audio=np.ones(16000, dtype=np.float32),
        language_hint="auto",
    )

    assert result.debug is not None
    assert result.debug["routing"]["engine"] == "sensevoice"
    indic.load.assert_not_called()
    indic.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_english_only_transcribe_rejects_hi_before_inference(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    service = _fresh_service()
    indic = Mock()
    indic.is_loaded = True
    service._indicconformer = indic

    with pytest.raises(InvalidLanguageHintError):
        await service.transcribe_array(
            audio=np.ones(16000, dtype=np.float32),
            language_hint="hi",
        )

    indic.transcribe.assert_not_called()


# ----------------------------------------------------------------------
# Initialization isolation
# ----------------------------------------------------------------------

def test_english_only_initialize_skips_indic_and_lid_construction(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    monkeypatch.setattr(settings, "LID_ENABLED", True)
    monkeypatch.setattr(settings, "LID_MODEL_DIR", "models/voxlingua107")

    indic_ctor = Mock(side_effect=AssertionError("IndicConformer must not be constructed"))
    lid_ctor = Mock(side_effect=AssertionError("VoxLingua107 must not be constructed"))
    monkeypatch.setattr(speech_service_module, "IndicConformerSpeechEngine", indic_ctor)
    monkeypatch.setattr(speech_service_module, "VoxLingua107LanguageIdentifier", lid_ctor)

    service = SpeechService()
    service._sensevoice = FakeSenseVoiceEngine()
    service._engine = service._sensevoice
    service.initialize()

    assert service._indicconformer is None
    assert service.router is not None
    assert service.router.lid_detector is None
    indic_ctor.assert_not_called()
    lid_ctor.assert_not_called()


# ----------------------------------------------------------------------
# REST validation (shared by /api/speech/upload and /api/predict)
# ----------------------------------------------------------------------

def test_upload_rejects_hi_in_english_only(client, valid_wav_bytes):
    files = {"file": ("speech.wav", valid_wav_bytes, "audio/wav")}
    response = client.post("/api/speech/upload", files=files, data={"language_hint": "hi"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_LANGUAGE_HINT"


def test_predict_rejects_hi_in_english_only(client, valid_wav_bytes):
    files = {"file": ("speech.wav", valid_wav_bytes, "audio/wav")}
    response = client.post("/api/predict", files=files, data={"language_hint": "hi"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_LANGUAGE_HINT"


@pytest.mark.parametrize("hint", ["en", "auto", ""])
def test_upload_accepts_english_only_hints(client, valid_wav_bytes, hint):
    files = {"file": ("speech.wav", valid_wav_bytes, "audio/wav")}
    response = client.post("/api/speech/upload", files=files, data={"language_hint": hint})

    assert response.status_code == 200
    res = response.json()
    assert res["debug"]["routing"]["engine"] == "sensevoice"
    assert res["debug"]["routing"]["language"] == "en"


# ----------------------------------------------------------------------
# WebSocket validation
# ----------------------------------------------------------------------

def test_websocket_rejects_hi_then_accepts_en(client):
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "hi",
        })
        error_event = ws.receive_json()
        assert error_event["type"] == "error"
        assert error_event["code"] == "INVALID_LANGUAGE_HINT"

        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "en",
        })
        ready_event = ws.receive_json()
        assert ready_event["type"] == "ready"


def test_websocket_rejects_other_indic_hint(client):
    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({
            "type": "start",
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "language_hint": "bn",
        })
        error_event = ws.receive_json()
        assert error_event["type"] == "error"
        assert error_event["code"] == "INVALID_LANGUAGE_HINT"


# ----------------------------------------------------------------------
# Multilingual mode remains available when disabled
# ----------------------------------------------------------------------

def test_multilingual_mode_still_routes_hi_to_indicconformer(monkeypatch):
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", False)
    service = _fresh_service()
    service._indicconformer = FakeIndicConformerEngine()

    engine, engine_name, decision = service.get_engine_for_utterance(
        audio=np.ones(16000, dtype=np.float32),
        language_hint="hi",
    )

    assert engine_name == "indicconformer"
    assert decision.engine == "indicconformer"
    assert decision.source == "hint"
    assert decision.language == "hi"
