"""
Chunk 6.1 quarantine tests for the placeholder SER engine.

Wav2Vec2EmotionEngine is a scaffold: pseudo-random features and untrained
weights. Non-mock construction must fail explicitly; mock mode must be
unmistakably labeled and must not emit fabricated valence/arousal metrics.
"""

import numpy as np
import pytest

from ai.inference.emotion import Wav2Vec2EmotionEngine, EmotionEngine, EmotionResult


def test_non_mock_engine_refuses_to_construct():
    """Default (non-mock) construction must raise NotImplementedError."""
    with pytest.raises(NotImplementedError, match="placeholder scaffold"):
        Wav2Vec2EmotionEngine()


def test_non_mock_engine_refuses_even_with_checkpoint_path(tmp_path):
    """A checkpoint path must not bypass the quarantine — weights are untrained."""
    fake_ckpt = tmp_path / "fake.npz"
    np.savez(fake_ckpt, w1=np.zeros((4, 4)))
    with pytest.raises(NotImplementedError):
        Wav2Vec2EmotionEngine(checkpoint_path=str(fake_ckpt))


def test_mock_engine_is_explicitly_labeled():
    """Mock mode must identify its output as mock in model_version and health."""
    engine = Wav2Vec2EmotionEngine(mock=True)
    assert isinstance(engine, EmotionEngine)

    health = engine.check_health()
    assert health["mock"] is True
    assert "mock" in health["model_version"]

    audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)).astype(np.float32)
    res = engine.classify(audio)
    assert isinstance(res, EmotionResult)
    assert "mock" in res.model_version


def test_mock_engine_emits_no_fabricated_metrics():
    """EmotionResult must not contain valence/arousal or other invented fields."""
    engine = Wav2Vec2EmotionEngine(mock=True)
    audio = np.zeros(16000, dtype=np.float32)
    res = engine.classify(audio)

    payload = res.to_dict()
    assert set(payload.keys()) == {
        "primary", "confidence", "scores", "processing_time_ms", "model_version",
    }
    for forbidden in ("valence", "arousal", "emotion_scores", "lexical_polarity"):
        assert forbidden not in payload


def test_mock_engine_still_supports_test_inputs():
    """Existing mock-mode tests rely on ndarray/bytes/empty inputs working."""
    engine = Wav2Vec2EmotionEngine(mock=True)

    res_arr = engine.classify(np.ones(8000, dtype=np.float32) * 0.1)
    assert res_arr.primary in engine.config.emotions
    assert sum(res_arr.scores.values()) == pytest.approx(1.0, abs=1e-3)

    res_bytes = engine.classify(b"\x00\x00" * 4000)
    assert isinstance(res_bytes, EmotionResult)

    res_empty = engine.classify(np.array([], dtype=np.float32))
    assert res_empty.primary == "neutral"
