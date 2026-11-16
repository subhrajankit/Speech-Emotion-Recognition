"""
Unit and integration tests for Emotion2VecSpeechEngine.
Tests interface compliance, lazy loading, label mapping, threshold gating,
silence handling, and real inference when weights exist.
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock

from ai.inference.emotion import EmotionEngine, EmotionResult
from ai.inference.emotion2vec import (
    Emotion2VecSpeechEngine,
    _normalize_funasr_label,
    SUPPORTED_4CLASS_MAP,
)


def test_label_normalization():
    """Verify Chinese/English FunASR labels normalize to clean English keys."""
    assert _normalize_funasr_label("生气/angry") == "angry"
    assert _normalize_funasr_label("开心/happy") == "happy"
    assert _normalize_funasr_label("中立/neutral") == "neutral"
    assert _normalize_funasr_label("难过/sad") == "sad"
    assert _normalize_funasr_label("厌恶/disgusted") == "disgusted"
    assert _normalize_funasr_label("<unk>") == "<unk>"


def test_interface_compliance():
    """Verify Emotion2VecSpeechEngine implements EmotionEngine ABC."""
    engine = Emotion2VecSpeechEngine(auto_load=False)
    assert isinstance(engine, EmotionEngine)
    assert engine.model_version == "emotion2vec_plus_base"
    assert engine.is_loaded is False
    assert engine.model is None


def test_lazy_loading_behavior():
    """Verify weights are not loaded at construction when auto_load=False."""
    engine = Emotion2VecSpeechEngine(auto_load=False)
    assert engine.is_loaded is False
    assert engine.model is None
    health = engine.check_health()
    assert health["is_loaded"] is False
    assert health["status"] == "ready"


def test_silence_handling():
    """Verify digital silence returns unknown with zero confidence without calling model."""
    engine = Emotion2VecSpeechEngine(auto_load=False)
    engine.is_loaded = True
    engine.model = MagicMock()

    silence = np.zeros(16000, dtype=np.float32)
    res = engine.classify(silence, sample_rate=16000)

    assert isinstance(res, EmotionResult)
    assert res.primary == "unknown"
    assert res.confidence == 0.0
    # Model generate must NOT be called for silence
    assert engine.model.generate.call_count == 0


def test_empty_audio_handling():
    """Verify empty numpy array returns unknown with zero confidence."""
    engine = Emotion2VecSpeechEngine(auto_load=False)
    engine.is_loaded = True
    engine.model = MagicMock()

    empty = np.array([], dtype=np.float32)
    res = engine.classify(empty, sample_rate=16000)

    assert isinstance(res, EmotionResult)
    assert res.primary == "unknown"
    assert res.confidence == 0.0
    assert engine.model.generate.call_count == 0


def test_supported_emotion_mapping_and_threshold():
    """Verify high-confidence supported emotion maps directly."""
    engine = Emotion2VecSpeechEngine(confidence_threshold=0.60, auto_load=False)
    engine.is_loaded = True

    # Mock model output: Angry with 0.85 score
    mock_model = MagicMock()
    mock_model.generate.return_value = [
        {
            "labels": ["生气/angry", "开心/happy", "中立/neutral", "难过/sad"],
            "scores": [0.85, 0.05, 0.05, 0.05],
        }
    ]
    engine.model = mock_model

    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    res = engine.classify(dummy_audio)

    assert isinstance(res, EmotionResult)
    assert res.primary == "angry"
    assert res.confidence == 0.85
    assert res.scores["angry"] == 0.85


def test_sub_threshold_rejection():
    """Verify predictions below confidence threshold map to unknown."""
    engine = Emotion2VecSpeechEngine(confidence_threshold=0.60, auto_load=False)
    engine.is_loaded = True

    # Top score is only 0.45 (< 0.60 threshold)
    mock_model = MagicMock()
    mock_model.generate.return_value = [
        {
            "labels": ["生气/angry", "开心/happy", "中立/neutral", "难过/sad"],
            "scores": [0.45, 0.35, 0.10, 0.10],
        }
    ]
    engine.model = mock_model

    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    res = engine.classify(dummy_audio)

    assert isinstance(res, EmotionResult)
    assert res.primary == "unknown"
    assert res.confidence == 0.45  # Real confidence preserved
    assert res.scores["angry"] == 0.45


def test_unsupported_class_mapping():
    """Verify unsupported classes (e.g. disgusted, fearful) map to unknown."""
    engine = Emotion2VecSpeechEngine(confidence_threshold=0.60, auto_load=False)
    engine.is_loaded = True

    mock_model = MagicMock()
    mock_model.generate.return_value = [
        {
            "labels": ["厌恶/disgusted", "生气/angry", "中立/neutral", "难过/sad"],
            "scores": [0.92, 0.04, 0.02, 0.02],
        }
    ]
    engine.model = mock_model

    dummy_audio = np.ones(16000, dtype=np.float32) * 0.1
    res = engine.classify(dummy_audio)

    assert isinstance(res, EmotionResult)
    assert res.primary == "unknown"
    assert res.confidence == 0.92  # Preserves raw confidence
    assert res.scores["disgusted"] == 0.92


@pytest.mark.model
def test_real_emotion2vec_inference_on_sample():
    """Integration test with real model weights if present."""
    model_path = Path("models/emotion/emotion2vec-plus-base")
    if not model_path.exists():
        pytest.skip(f"Model path {model_path} does not exist.")

    test_wav = model_path / "test.wav"
    if not test_wav.exists():
        pytest.skip(f"Test wav {test_wav} does not exist.")

    engine = Emotion2VecSpeechEngine(
        model_dir=model_path,
        device="cpu",
        threads=2,
        confidence_threshold=0.60,
        auto_load=True,
    )
    assert engine.is_loaded is True

    res = engine.classify(str(test_wav))
    assert isinstance(res, EmotionResult)
    assert res.primary in ("angry", "happy", "neutral", "sad", "unknown")
    assert res.confidence >= 0.0
    assert len(res.scores) > 0
    assert res.processing_time_ms > 0
