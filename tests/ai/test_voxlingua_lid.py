"""
Unit tests for VoxLingua107LanguageIdentifier.

All heavyweight model inference is mocked: torch / speechbrain / hyperpyyaml
are NOT required in CI. Tests cover artifact validation, lazy one-time
loading, label mapping, confidence passthrough, safe degradation, and
router integration.
"""

from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from ai.routing.language_identifier import VoxLingua107LanguageIdentifier
from ai.routing.language_router import LanguageRouter


def _make_model_dir(tmp_path: Path) -> Path:
    """Creates the four required artifact filenames (empty contents)."""
    for name in VoxLingua107LanguageIdentifier.REQUIRED_FILES:
        (tmp_path / name).write_bytes(b"")
    return tmp_path


def _speech_audio(seconds: float = 1.0, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False, dtype=np.float32)
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


# ----------------------------------------------------------------------
# Artifact validation
# ----------------------------------------------------------------------

def test_missing_artifacts_detected(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    assert det.has_required_files() is False


def test_all_artifacts_present(tmp_path):
    _make_model_dir(tmp_path)
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    assert det.has_required_files() is True


def test_load_missing_artifacts_raises_runtime_error(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="missing"):
        det.load()
    assert det.is_loaded is False


# ----------------------------------------------------------------------
# Safe degradation: invalid / silent / unloadable audio
# ----------------------------------------------------------------------

def test_identify_empty_audio_returns_unknown_without_loading(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    assert det.identify(np.array([], dtype=np.float32)) == ("unknown", 0.0)
    assert det.identify(None) == ("unknown", 0.0)
    assert det.is_loaded is False


def test_identify_silence_returns_unknown(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    assert det.identify(np.zeros(16000, dtype=np.float32)) == ("unknown", 0.0)
    assert det.is_loaded is False


def test_identify_nonfinite_audio_returns_unknown(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    bad = np.array([0.1, np.nan, 0.2], dtype=np.float32)
    assert det.identify(bad) == ("unknown", 0.0)
    assert det.is_loaded is False


def test_identify_unloadable_model_returns_unknown_and_caches_failure(tmp_path):
    _make_model_dir(tmp_path)  # files exist but contents are garbage
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    audio = _speech_audio(0.5)

    assert det.identify(audio) == ("unknown", 0.0)
    assert det.is_loaded is False
    assert det._load_error is not None

    # Second call must not retry the failed load.
    det.load = Mock(side_effect=AssertionError("load must not be retried"))
    assert det.identify(audio) == ("unknown", 0.0)
    det.load.assert_not_called()


# ----------------------------------------------------------------------
# Audio preparation
# ----------------------------------------------------------------------

def test_prepare_audio_resamples_to_16k(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    audio8k = _speech_audio(0.5, sr=8000)
    out = det._prepare_audio(audio8k, sample_rate=8000)
    assert out is not None
    assert len(out) == pytest.approx(8000, rel=0.01)


def test_prepare_audio_passthrough_16k(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    audio = _speech_audio(0.5, sr=16000)
    out = det._prepare_audio(audio, sample_rate=16000)
    assert out is not None
    assert len(out) == len(audio)
    assert out.dtype == np.float32


# ----------------------------------------------------------------------
# Label mapping
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,expected",
    [
        ("hi: Hindi", "hi"),
        ("en: English", "en"),
        ("zh: Chinese", "zh"),
        ("mr: Marathi", "mr"),
        ("ta: Tamil", "ta"),
        ("tl: Tagalog", "tl"),
        ("iw: Hebrew", "he"),   # obsolete code normalized per model card
        ("jw: Javanese", "jv"),  # obsolete code normalized per model card
    ],
)
def test_map_label_to_code_valid(label, expected):
    assert VoxLingua107LanguageIdentifier.map_label_to_code(label) == expected


@pytest.mark.parametrize(
    "label",
    ["", None, "   ", "not a label", "123: bogus", "hi", ": Hindi", "<|hi|>"],
)
def test_map_label_to_code_unknown(label):
    assert VoxLingua107LanguageIdentifier.map_label_to_code(label) == "unknown"


# ----------------------------------------------------------------------
# Inference path (mocked _infer — no torch required)
# ----------------------------------------------------------------------

def _loaded_detector(tmp_path, infer_return):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    det.is_loaded = True
    det._infer = Mock(return_value=infer_return)
    return det


def test_identify_returns_mapped_code_and_model_confidence(tmp_path):
    det = _loaded_detector(tmp_path, ("hi: Hindi", 0.87))
    code, conf = det.identify(_speech_audio(0.5))
    assert code == "hi"
    assert conf == pytest.approx(0.87)
    det._infer.assert_called_once()


def test_identify_maps_obsolete_codes(tmp_path):
    det = _loaded_detector(tmp_path, ("iw: Hebrew", 0.9))
    assert det.identify(_speech_audio(0.5)) == ("he", pytest.approx(0.9))


def test_identify_unparseable_label_returns_unknown_code(tmp_path):
    det = _loaded_detector(tmp_path, ("garbage-output", 0.95))
    code, conf = det.identify(_speech_audio(0.5))
    assert code == "unknown"
    assert conf == pytest.approx(0.95)  # confidence is model-provided, passed through


def test_identify_inference_error_returns_unknown(tmp_path):
    det = _loaded_detector(tmp_path, None)
    det._infer = Mock(side_effect=RuntimeError("CUDA exploded"))
    assert det.identify(_speech_audio(0.5)) == ("unknown", 0.0)


def test_load_called_once_across_identities(tmp_path):
    det = VoxLingua107LanguageIdentifier(model_dir=str(tmp_path))
    det.load = Mock(side_effect=lambda: setattr(det, "is_loaded", True))
    det._infer = Mock(return_value=("en: English", 0.8))

    det.identify(_speech_audio(0.3))
    det.identify(_speech_audio(0.3))
    det.identify(_speech_audio(0.3))
    assert det.load.call_count == 1


# ----------------------------------------------------------------------
# Router integration (Tier-2)
# ----------------------------------------------------------------------

def test_router_uses_lid_detection_above_threshold(tmp_path):
    det = _loaded_detector(tmp_path, ("hi: Hindi", 0.9))
    router = LanguageRouter(lid_detector=det, lid_confidence_threshold=0.6)
    decision = router.route(audio=_speech_audio(0.5))
    assert decision.engine == "indicconformer"
    assert decision.source == "detected"
    assert decision.language == "hi"
    assert decision.confidence == pytest.approx(0.9)


def test_router_lid_below_threshold_falls_back(tmp_path):
    det = _loaded_detector(tmp_path, ("hi: Hindi", 0.4))
    router = LanguageRouter(lid_detector=det, lid_confidence_threshold=0.6)
    decision = router.route(audio=_speech_audio(0.5))
    assert decision.engine == "sensevoice"
    assert decision.source == "default"


def test_router_explicit_hint_beats_lid(tmp_path):
    det = _loaded_detector(tmp_path, ("en: English", 0.99))
    router = LanguageRouter(lid_detector=det)
    decision = router.route(audio=_speech_audio(0.5), language_hint="hi")
    assert decision.engine == "indicconformer"
    assert decision.source == "hint"
    det._infer.assert_not_called()


def test_router_lid_unknown_language_uses_default_engine(tmp_path):
    det = _loaded_detector(tmp_path, ("fr: French", 0.95))
    router = LanguageRouter(lid_detector=det, lid_confidence_threshold=0.6)
    decision = router.route(audio=_speech_audio(0.5))
    assert decision.engine == "sensevoice"
    assert decision.source == "detected"
    assert decision.language == "fr"
