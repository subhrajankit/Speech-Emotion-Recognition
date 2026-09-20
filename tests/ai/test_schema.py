"""
Unit tests for unified SpeechResult schema validation and serialization.
"""

import pytest
from pydantic import ValidationError

from ai.inference.types import SpeechResult


def test_speech_result_valid():
    res = SpeechResult(
        transcript="Hello, how can I help?",
        language="en",
        emotion="happy",
        processing_time_ms=120,
        model_version="SenseVoiceSmall (v1.0)"
    )

    assert res.transcript == "Hello, how can I help?"
    assert res.language == "en"
    assert res.emotion == "happy"
    assert res.confidence is None  # Uncalibrated confidence policy
    assert res.processing_time_ms == 120
    assert res.model_version == "SenseVoiceSmall (v1.0)"
    assert res.audio_events == []
    assert res.segments == []


def test_speech_result_confidence_range():
    # Valid confidence
    res = SpeechResult(
        transcript="Test",
        language="en",
        confidence=0.85,
        processing_time_ms=50,
        model_version="test"
    )
    assert res.confidence == 0.85

    # Invalid confidence > 1.0
    with pytest.raises(ValidationError):
        SpeechResult(
            transcript="Test",
            language="en",
            confidence=1.5,
            processing_time_ms=50,
            model_version="test"
        )


def test_speech_result_schema_has_no_sensevoice_specific_keys():
    """Confirms root schema contains no model-specific fields."""
    res = SpeechResult(
        transcript="Hello",
        language="en",
        processing_time_ms=10,
        model_version="generic"
    )
    fields = set(res.model_dump().keys())
    forbidden = {"sensevoice", "rich_text", "itn", "ban_emo_unk", "funasr"}
    for f in fields:
        assert f.lower() not in forbidden, f"Found forbidden model-specific field: {f}"


def test_speech_result_json_serialization():
    res = SpeechResult(
        transcript="Good evening",
        language="en",
        emotion="neutral",
        processing_time_ms=95,
        model_version="test_v1",
        audio_events=["Speech", "BGM"]
    )
    json_str = res.model_dump_json()
    assert '"transcript":"Good evening"' in json_str
    assert '"language":"en"' in json_str
    assert '"emotion":"neutral"' in json_str
    assert '"confidence":null' in json_str
    assert '"audio_events":["Speech","BGM"]' in json_str
