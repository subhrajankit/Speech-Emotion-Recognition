"""
Unit and integration tests for SenseVoiceSpeechEngine.
Tests VAD-gated silence handling, interface compliance, and skips model tests when weights are absent.
"""

import numpy as np
import pytest

from ai.inference.engine import SpeechEngine
from ai.inference.sensevoice import SenseVoiceSpeechEngine
from ai.inference.types import SpeechResult


def test_engine_interface_compliance():
    """Confirms SenseVoiceSpeechEngine satisfies the SpeechEngine ABC."""
    engine = SenseVoiceSpeechEngine(auto_load=False)
    assert isinstance(engine, SpeechEngine)
    assert "SenseVoiceSmall" in engine.model_version


def test_engine_handles_silence_without_error():
    """
    When given 1 second of silent audio, the VAD gate intercepts it
    and returns a valid no-speech SpeechResult without needing model weights.
    """
    engine = SenseVoiceSpeechEngine(auto_load=False)
    silence = np.zeros(16000, dtype=np.float32)

    result = engine.transcribe(silence, sample_rate=16000)
    assert isinstance(result, SpeechResult)
    assert result.transcript == ""
    assert result.language == "unknown"
    assert result.emotion is None
    assert result.confidence is None
    assert result.debug.get("vad_has_speech") is False


def test_engine_handles_empty_audio():
    """Empty audio returns schema-valid result with 0 transcript."""
    engine = SenseVoiceSpeechEngine(auto_load=False)
    empty = np.array([], dtype=np.float32)

    result = engine.transcribe(empty, sample_rate=16000)
    assert isinstance(result, SpeechResult)
    assert result.transcript == ""
    assert result.language == "unknown"


def test_engine_handles_sub_second_audio():
    """Audio clip shorter than VAD minimum returns no-speech."""
    engine = SenseVoiceSpeechEngine(auto_load=False)
    # 100ms clip at 16kHz (1600 samples)
    short_audio = np.ones(1600, dtype=np.float32) * 0.1

    result = engine.transcribe(short_audio, sample_rate=16000)
    assert isinstance(result, SpeechResult)
    assert result.transcript == ""
    assert result.debug.get("vad_has_speech") is False


def test_actionable_error_on_missing_funasr_or_weights():
    """
    When auto_load is True and funasr/torch or weights are missing,
    a clear, actionable RuntimeError is raised naming the expected path or dependency.
    """
    engine = SenseVoiceSpeechEngine(auto_load=False, model_dir="nonexistent/models/SenseVoiceSmall")
    try:
        engine._load_model()
    except RuntimeError as err:
        msg = str(err)
        assert any(term in msg for term in ["PyTorch", "FunASR", "nonexistent/models/SenseVoiceSmall"]), (
            f"Error message must be actionable. Got: {msg}"
        )


@pytest.mark.model
def test_real_model_inference():
    """
    Model-dependent test: marked @pytest.mark.model.
    SKIPS cleanly if funasr, torch, or weights are not installed.
    Never mocks the model to fake a pass.
    """
    try:
        import torch
        from funasr import AutoModel
    except ImportError as e:
        pytest.skip(f"Deep learning dependency not installed ({e}). Skipping real model test.")

    import os
    model_dir = os.getenv("SENSEVOICE_MODEL_DIR", "iic/SenseVoiceSmall")
    if not os.path.exists(model_dir):
        pytest.skip(f"SenseVoice weights absent at '{model_dir}'. Skipping real model test.")

    # Only reached if dependencies and weights actually exist
    engine = SenseVoiceSpeechEngine(model_dir=model_dir, device="cpu", auto_load=True)
    from ai.preprocessing.audio import load_and_preprocess_audio
    audio = load_and_preprocess_audio("tests/samples/sample_chinese_speech.wav")
    res = engine.transcribe(audio)

    assert isinstance(res, SpeechResult)
    assert len(res.transcript) > 0
    assert res.language != "unknown"
