"""
Chunk 6.1 tests for the SenseVoice zero-shot baseline in ai/training/evaluate.py.

Regression: engine.transcribe() expects a 16 kHz mono float32 ndarray, but the
baseline previously passed the manifest file path string. These tests mock
audio loading and SenseVoice inference — no real model or CREMA-D audio.
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import ai.training.evaluate as evaluate_mod
from ai.training.evaluate import evaluate_sensevoice_baseline
from ai.models.emotion.config import EmotionModelConfig


class _FakeSenseVoiceEngine:
    """Records transcribe() arguments; returns a canned SpeechResult-like object."""

    instances = []
    emotion = "happy"

    def __init__(self, *args, **kwargs):
        self.transcribe_calls = []
        _FakeSenseVoiceEngine.instances.append(self)

    def transcribe(self, audio, sample_rate=16000, language_hint=None):
        self.transcribe_calls.append(
            {"audio_type": type(audio).__name__, "sample_rate": sample_rate}
        )
        return SimpleNamespace(emotion=self.emotion)


@pytest.fixture
def fake_engine(monkeypatch):
    _FakeSenseVoiceEngine.instances = []
    _FakeSenseVoiceEngine.emotion = "happy"
    monkeypatch.setattr(
        "ai.inference.sensevoice.SenseVoiceSpeechEngine", _FakeSenseVoiceEngine
    )
    return _FakeSenseVoiceEngine


@pytest.fixture
def fake_loader(monkeypatch):
    """Replace audio decoding with a sentinel array; record call args."""
    calls = []
    sentinel = np.zeros(16000, dtype=np.float32)

    def _loader(audio_input, target_sr=16000, peak_norm=0.95):
        calls.append({"input": audio_input, "target_sr": target_sr})
        return sentinel

    monkeypatch.setattr(evaluate_mod, "load_and_preprocess_audio", _loader)
    return calls


def _write_manifest(tmp_path: Path, rows: list[dict]) -> Path:
    manifest = tmp_path / "manifest.csv"
    header = "sample_id,file_path,speaker_id,emotion,raw_emotion,duration_sec\n"
    lines = [
        f"{r['sample_id']},{r['file_path']},{r['speaker_id']},{r['emotion']},"
        f"{r.get('raw_emotion', '')},{r.get('duration_sec', 2.5)}"
        for r in rows
    ]
    manifest.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _records_from_manifest(manifest: Path):
    from ai.training.dataset import load_manifest_csv
    return load_manifest_csv(manifest)


def test_baseline_loads_audio_and_passes_ndarray(tmp_path, fake_engine, fake_loader):
    """transcribe() must receive a float32 ndarray, never the file path string."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    manifest = _write_manifest(tmp_path, [
        {"sample_id": "s1", "file_path": str(wav), "speaker_id": "spk1",
         "emotion": "happy", "raw_emotion": "HAP"},
        {"sample_id": "s2", "file_path": str(wav), "speaker_id": "spk1",
         "emotion": "happy", "raw_emotion": "HAP"},
    ])
    records = _records_from_manifest(manifest)

    result = evaluate_sensevoice_baseline(records, EmotionModelConfig())

    # Loader received the path; engine received an ndarray at 16 kHz
    assert fake_loader and all(c["input"] == str(wav) for c in fake_loader)
    engine = _FakeSenseVoiceEngine.instances[0]
    assert len(engine.transcribe_calls) == 2
    for call in engine.transcribe_calls:
        assert call["audio_type"] == "ndarray"
        assert call["sample_rate"] == 16000

    # Both happy predictions mapped correctly
    assert result["evaluated_samples"] == 2
    assert result["skipped_samples"] == 0
    assert result["accuracy"] == pytest.approx(1.0)


def test_baseline_skips_missing_files(tmp_path, fake_engine, fake_loader):
    """Nonexistent audio paths are skipped, not crashed on."""
    missing = str(tmp_path / "does_not_exist.wav")
    manifest = _write_manifest(tmp_path, [
        {"sample_id": "s1", "file_path": missing, "speaker_id": "spk1",
         "emotion": "sad", "raw_emotion": "SAD"},
    ])
    records = _records_from_manifest(manifest)

    result = evaluate_sensevoice_baseline(records, EmotionModelConfig())

    assert result["status"] == "NOT_YET_MEASURED"
    assert result["evaluated_samples"] == 0
    assert result["skipped_samples"] == 1
    assert fake_loader == []  # loader never invoked for missing files
