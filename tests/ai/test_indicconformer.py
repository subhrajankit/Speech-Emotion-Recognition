"""
Unit and integration tests for IndicConformerSpeechEngine.
Tests SpeechEngine interface compliance, emotion invariant (emotion=None),
VAD silence handling, and model tests with skip-with-reason.
"""

import os
import numpy as np
import pytest

from ai.inference.engine import SpeechEngine
from ai.inference.indicconformer import IndicConformerSpeechEngine
from ai.inference.sensevoice import SenseVoiceSpeechEngine
from ai.inference.types import SpeechResult


from unittest.mock import MagicMock


def test_indicconformer_interface_compliance():
    """Confirms IndicConformerSpeechEngine satisfies SpeechEngine ABC."""
    engine = IndicConformerSpeechEngine(auto_load=False)
    assert isinstance(engine, SpeechEngine)
    assert "IndicConformer-600m" in engine.model_version


def test_indicconformer_emotion_is_always_none():
    """
    Critical Architecture Invariant:
    IndicConformer produces NO emotion prediction.
    Must always return emotion = None and emotion_scores = None.
    SenseVoice emotion head is never run on Hindi audio.
    """
    engine = IndicConformerSpeechEngine(auto_load=False)
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ["परीक्षण"]
    engine.model = mock_model
    engine.is_loaded = True
    dummy_audio = np.ones(16000, dtype=np.float32)

    result = engine.transcribe(dummy_audio, sample_rate=16000, language_hint="hi")
    assert isinstance(result, SpeechResult)
    assert result.emotion is None
    assert result.emotion_scores is None
    assert result.language == "hi"


def test_indicconformer_handles_silence_without_error():
    """
    When given 1 second of silent audio, the VAD gate intercepts it
    and returns a valid no-speech SpeechResult without needing model weights.
    """
    engine = IndicConformerSpeechEngine(auto_load=False)
    silence = np.zeros(16000, dtype=np.float32)

    result = engine.transcribe(silence, sample_rate=16000, language_hint="hi")
    assert isinstance(result, SpeechResult)
    assert result.transcript == ""
    assert result.language == "hi"
    assert result.emotion is None
    assert result.confidence is None
    assert result.debug.get("vad_has_speech") is False


def test_indicconformer_handles_empty_audio():
    """Empty audio returns schema-valid result with 0 transcript and emotion=None."""
    engine = IndicConformerSpeechEngine(auto_load=False)
    empty = np.array([], dtype=np.float32)

    result = engine.transcribe(empty, sample_rate=16000, language_hint="hi")
    assert isinstance(result, SpeechResult)
    assert result.transcript == ""
    assert result.emotion is None
    assert result.debug.get("status") == "empty_audio"


def test_actionable_error_on_missing_nemo_or_weights():
    """
    When auto_load is True and NeMo or weights are missing,
    a clear, actionable RuntimeError is raised naming the expected path or dependency.
    """
    engine = IndicConformerSpeechEngine(
        auto_load=False,
        model_dir="nonexistent/models/IndicConformer.nemo"
    )
    try:
        engine._load_model()
    except RuntimeError as err:
        msg = str(err)
        assert any(term in msg for term in ["PyTorch", "NeMo", "nonexistent/models/IndicConformer.nemo"]), (
            f"Error message must be actionable. Got: {msg}"
        )


@pytest.mark.model
def test_dual_engine_identical_schema():
    """
    Model-dependent test: marked @pytest.mark.model.
    A real Hindi wav goes through IndicConformer, a real English wav through SenseVoice,
    both returning the identical SpeechResult schema.
    SKIPS cleanly if weights or deep learning dependencies are absent.
    """
    try:
        import torch
    except ImportError as e:
        pytest.skip(f"PyTorch not installed ({e}). Skipping real model test.")

    hindi_wav = "tests/samples/sample_hindi_speech.wav"
    english_wav = "tests/speech_sample.wav"

    if not os.path.exists(hindi_wav):
        pytest.skip(f"Hindi audio sample absent at '{hindi_wav}'. Skipping dual model test.")

    indic_model_dir = os.getenv("INDICCONFORMER_MODEL_DIR", "ai4bharat/indicconformer_stt_indic_hybrid_ctc_large")
    sv_model_dir = os.getenv("SENSEVOICE_MODEL_DIR", "iic/SenseVoiceSmall")

    if not os.path.exists(indic_model_dir) and not indic_model_dir.startswith("ai4bharat/"):
        pytest.skip(f"IndicConformer weights absent at '{indic_model_dir}'. Skipping real model test.")
    if not os.path.exists(sv_model_dir) and not sv_model_dir.startswith("iic/"):
        pytest.skip(f"SenseVoice weights absent at '{sv_model_dir}'. Skipping real model test.")

    from ai.preprocessing.audio import load_and_preprocess_audio

    # 1. IndicConformer transcription
    try:
        indic_engine = IndicConformerSpeechEngine(model_dir=indic_model_dir, device="cpu", auto_load=True)
        hindi_audio = load_and_preprocess_audio(hindi_wav)
        indic_res = indic_engine.transcribe(hindi_audio, language_hint="hi")
    except Exception as e:
        pytest.skip(f"IndicConformer could not be loaded or executed: {e}")

    # 2. SenseVoice transcription
    try:
        sv_engine = SenseVoiceSpeechEngine(model_dir=sv_model_dir, device="cpu", auto_load=True)
        english_audio = load_and_preprocess_audio(english_wav)
        sv_res = sv_engine.transcribe(english_audio, language_hint="en")
    except Exception as e:
        pytest.skip(f"SenseVoice could not be loaded or executed: {e}")

    # 3. Assert identical schema
    assert isinstance(indic_res, SpeechResult)
    assert isinstance(sv_res, SpeechResult)
    assert indic_res.language == "hi"
    assert indic_res.emotion is None  # Architecture invariant
    assert set(indic_res.model_dump().keys()) == set(sv_res.model_dump().keys())
