"""
Unit tests for audio preprocessing: decode, mono, 16kHz resampling, and normalization.
"""

import numpy as np
import pytest
from pathlib import Path

from ai.preprocessing.audio import (
    to_mono,
    resample_audio,
    normalize_audio,
    load_and_preprocess_audio,
    decode_audio,
)


def test_to_mono_1d():
    """1D mono array should pass through unmodified."""
    x = np.array([0.1, -0.2, 0.5], dtype=np.float32)
    mono = to_mono(x)
    assert np.array_equal(x, mono)


def test_to_mono_stereo_samples_last():
    """2D stereo (samples, 2) should downmix to average."""
    stereo = np.array([[0.2, 0.4], [-0.6, -0.2], [1.0, 0.0]], dtype=np.float32)
    expected = np.array([0.3, -0.4, 0.5], dtype=np.float32)
    mono = to_mono(stereo)
    assert np.allclose(mono, expected, atol=1e-5)


def test_to_mono_channels_first():
    """2D stereo (2, samples) should downmix to average."""
    stereo = np.array([[0.2, -0.6, 1.0], [0.4, -0.2, 0.0]], dtype=np.float32)
    expected = np.array([0.3, -0.4, 0.5], dtype=np.float32)
    mono = to_mono(stereo)
    assert np.allclose(mono, expected, atol=1e-5)


def test_resample_same_rate():
    """Resampling with identical rates returns original data."""
    x = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    res = resample_audio(x, 16000, 16000)
    assert np.array_equal(x, res)


def test_resample_up_and_down():
    """Resampling changes length proportionally."""
    # 1 second of 8000 Hz -> 8000 samples
    x = np.sin(np.linspace(0, 2 * np.pi * 440, 8000)).astype(np.float32)
    # Upsample to 16000 Hz
    res16k = resample_audio(x, 8000, 16000)
    assert len(res16k) == 16000

    # Downsample from 48000 Hz to 16000 Hz
    x48k = np.zeros(48000, dtype=np.float32)
    res_down = resample_audio(x48k, 48000, 16000)
    assert len(res_down) == 16000


def test_normalize_audio_peak():
    """Normalizes non-silent audio to specified peak."""
    x = np.array([-0.5, 0.2, 0.4], dtype=np.float32)
    norm = normalize_audio(x, peak=0.95)
    assert np.max(np.abs(norm)) == pytest.approx(0.95, rel=1e-3)
    assert np.all(norm >= -1.0) and np.all(norm <= 1.0)


def test_normalize_audio_silence():
    """All-zero audio stays all-zero and does not produce NaN/Inf."""
    x = np.zeros(100, dtype=np.float32)
    norm = normalize_audio(x, peak=0.95)
    assert np.all(norm == 0.0)
    assert not np.any(np.isnan(norm))
    assert not np.any(np.isinf(norm))


def test_normalize_audio_int16():
    """Integer PCM16 arrays are scaled properly to [-1.0, 1.0]."""
    x = np.array([-32768, 0, 16384], dtype=np.int16)
    norm = normalize_audio(x, peak=0.95)
    assert norm.dtype == np.float32
    assert np.max(np.abs(norm)) == pytest.approx(0.95, rel=1e-3)


def test_load_and_preprocess_real_file():
    """Loads and preprocesses real recording to exactly 16 kHz float32."""
    sample_path = Path("tests/samples/sample_chinese_speech.wav")
    assert sample_path.exists(), "Sample file must exist"

    processed = load_and_preprocess_audio(sample_path, target_sr=16000)
    assert isinstance(processed, np.ndarray)
    assert processed.dtype == np.float32
    assert processed.ndim == 1
    assert len(processed) == 16000 * 6  # 6 seconds at 16kHz
    assert np.max(np.abs(processed)) <= 1.0


def test_decode_invalid_path_raises():
    """Raises FileNotFoundError for nonexistent file."""
    with pytest.raises(FileNotFoundError):
        decode_audio("nonexistent_path_to_audio.wav")
