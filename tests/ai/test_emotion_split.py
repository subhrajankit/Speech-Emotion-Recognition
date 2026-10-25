"""
Unit tests for speaker-independent dataset splitting and manifest generation.
Guarantees zero speaker leakage between train, val, and test splits.
"""

import tempfile
from pathlib import Path
import pytest

from ai.training.dataset import (
    DatasetManifestRecord,
    create_speaker_independent_split,
    save_manifest_csv,
    load_manifest_csv,
    compute_class_weights,
    compute_class_distribution,
    parse_crema_d_filename,
)


def test_crema_d_filename_parsing():
    """Verify regex/stem parsing for CREMA-D naming format."""
    parsed = parse_crema_d_filename("1001_DFA_ANG_XX.wav")
    assert parsed is not None
    sample_id, speaker_id, emotion_code = parsed
    assert sample_id == "1001_DFA_ANG_XX"
    assert speaker_id == "1001"
    assert emotion_code == "ANG"

    # Non-conforming filename returns None
    assert parse_crema_d_filename("random_file.wav") is None


def test_speaker_independent_split_zero_leakage():
    """
    Core Invariant: Zero speaker leakage between train, val, and test sets.
    """
    records = []
    # 10 speakers, 4 samples each
    speakers = [f"spk_{i:02d}" for i in range(10)]
    emotions = ["neutral", "happy", "sad", "angry"]

    for spk in speakers:
        for emo in emotions:
            records.append(
                DatasetManifestRecord(
                    sample_id=f"{spk}_{emo}",
                    file_path=f"data/{spk}_{emo}.wav",
                    speaker_id=spk,
                    emotion=emo,
                    raw_emotion=emo[:3].upper(),
                    duration_sec=2.0,
                )
            )

    train_recs, val_recs, test_recs = create_speaker_independent_split(
        records, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42
    )

    train_speakers = set(r.speaker_id for r in train_recs)
    val_speakers = set(r.speaker_id for r in val_recs)
    test_speakers = set(r.speaker_id for r in test_recs)

    # Invariants
    assert len(train_speakers) > 0
    assert len(val_speakers) > 0
    assert len(test_speakers) > 0

    # ZERO LEAKAGE
    assert len(train_speakers & val_speakers) == 0, "Train and Val share speakers!"
    assert len(train_speakers & test_speakers) == 0, "Train and Test share speakers!"
    assert len(val_speakers & test_speakers) == 0, "Val and Test share speakers!"

    # All records accounted for
    assert len(train_recs) + len(val_recs) + len(test_recs) == len(records)


def test_split_reproducibility():
    """Fixed seed must produce identical splits across runs."""
    records = [
        DatasetManifestRecord(f"s_{i}", f"f_{i}", f"spk_{i % 5}", "happy", "HAP")
        for i in range(25)
    ]

    t1, v1, te1 = create_speaker_independent_split(records, seed=123)
    t2, v2, te2 = create_speaker_independent_split(records, seed=123)

    assert [r.sample_id for r in t1] == [r.sample_id for r in t2]
    assert [r.sample_id for r in v1] == [r.sample_id for r in v2]
    assert [r.sample_id for r in te1] == [r.sample_id for r in te2]


def test_split_insufficient_speakers():
    """Must raise ValueError if fewer than 3 speakers are provided."""
    records = [
        DatasetManifestRecord("s_1", "f_1", "spk_1", "neutral", "NEU"),
        DatasetManifestRecord("s_2", "f_2", "spk_2", "happy", "HAP"),
    ]
    with pytest.raises(ValueError, match="Need at least 3 distinct speakers"):
        create_speaker_independent_split(records)


def test_manifest_roundtrip():
    """Verify CSV manifest save and load operations preserve all attributes."""
    records = [
        DatasetManifestRecord("s1", "/path/to/1.wav", "spk1", "neutral", "NEU", 1.5),
        DatasetManifestRecord("s2", "/path/to/2.wav", "spk2", "happy", "HAP", 2.8),
    ]

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        save_manifest_csv(records, tmp_path)
        loaded = load_manifest_csv(tmp_path)
        assert len(loaded) == 2
        assert loaded[0].sample_id == "s1"
        assert loaded[0].speaker_id == "spk1"
        assert loaded[0].emotion == "neutral"
        assert loaded[0].duration_sec == pytest.approx(1.5, abs=1e-3)
        assert loaded[1].emotion == "happy"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_class_imbalance_weights():
    """Test inverse-frequency class weight computation."""
    records = [
        DatasetManifestRecord("1", "p", "s1", "neutral", "NEU"),
        DatasetManifestRecord("2", "p", "s1", "neutral", "NEU"),
        DatasetManifestRecord("3", "p", "s1", "neutral", "NEU"),
        DatasetManifestRecord("4", "p", "s1", "happy", "HAP"),
    ]
    emotions = ["neutral", "happy"]
    weights = compute_class_weights(records, emotions)

    # Total = 4, classes = 2
    # neutral count = 3 -> weight = 4 / (2 * 3) = 4/6 = 0.6667
    # happy count = 1 -> weight = 4 / (2 * 1) = 4/2 = 2.0
    assert weights["neutral"] == pytest.approx(0.6667, abs=1e-3)
    assert weights["happy"] == pytest.approx(2.0, abs=1e-3)
