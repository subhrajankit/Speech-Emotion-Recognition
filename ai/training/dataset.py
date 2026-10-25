"""
Dataset management, parser, and speaker-independent split generator.
Enforces strict zero speaker overlap between train, validation, and test splits.
Reuses ai.preprocessing.audio for consistent acoustic features.
"""

import os
import csv
import logging
import random
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional, Any, Union
import numpy as np

from ai.preprocessing.audio import load_and_preprocess_audio

logger = logging.getLogger(__name__)

# CREMA-D 3-letter emotion code to canonical lowercase emotion
CREMA_D_EMOTION_MAP: Dict[str, str] = {
    "ANG": "angry",
    "DIS": "disgusted",
    "FEA": "fearful",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}


class DatasetManifestRecord:
    """
    Structured record for a single audio sample in a split manifest.
    """
    def __init__(
        self,
        sample_id: str,
        file_path: str,
        speaker_id: str,
        emotion: str,
        raw_emotion: str,
        duration_sec: float = 0.0,
    ):
        self.sample_id = sample_id
        self.file_path = file_path
        self.speaker_id = speaker_id
        self.emotion = emotion
        self.raw_emotion = raw_emotion
        self.duration_sec = duration_sec

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "file_path": self.file_path,
            "speaker_id": self.speaker_id,
            "emotion": self.emotion,
            "raw_emotion": self.raw_emotion,
            "duration_sec": round(self.duration_sec, 3),
        }


def parse_crema_d_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """
    Parses CREMA-D filename format: {SpeakerID}_{Sentence}_{EmotionCode}_{Intensity}.wav
    Example: '1001_DFA_ANG_XX.wav' -> ('1001_DFA_ANG_XX', '1001', 'ANG')
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    if len(parts) >= 3:
        speaker_id = parts[0]
        emotion_code = parts[2]
        return stem, speaker_id, emotion_code
    return None


def scan_crema_d_directory(
    audio_dir: Union[str, Path],
    target_emotions: Optional[List[str]] = None,
    emotion_map: Optional[Dict[str, str]] = None,
) -> List[DatasetManifestRecord]:
    """
    Scans a directory of CREMA-D WAV files and parses them into manifest records.
    Filters by target_emotions if provided.
    """
    audio_path = Path(audio_dir)
    if not audio_path.exists():
        logger.warning(f"Audio directory does not exist: {audio_dir}")
        return []

    target_emotions = target_emotions or ["neutral", "happy", "sad", "angry"]
    mapping = emotion_map or CREMA_D_EMOTION_MAP
    records: List[DatasetManifestRecord] = []

    for file in sorted(audio_path.glob("*.wav")):
        parsed = parse_crema_d_filename(file.name)
        if not parsed:
            continue
        sample_id, speaker_id, raw_code = parsed
        canonical_emotion = mapping.get(raw_code.upper())
        if canonical_emotion and canonical_emotion in target_emotions:
            records.append(
                DatasetManifestRecord(
                    sample_id=sample_id,
                    file_path=str(file.resolve()),
                    speaker_id=speaker_id,
                    emotion=canonical_emotion,
                    raw_emotion=raw_code,
                )
            )

    return records


def create_speaker_independent_split(
    records: List[DatasetManifestRecord],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
) -> Tuple[List[DatasetManifestRecord], List[DatasetManifestRecord], List[DatasetManifestRecord]]:
    """
    Partitions records into train, validation, and test splits strictly by speaker_id.
    Guarantees zero speaker overlap across splits:
        set(train_speakers) & set(val_speakers) == empty
        set(train_speakers) & set(test_speakers) == empty
        set(val_speakers) & set(test_speakers) == empty
    """
    if not records:
        return [], [], []

    # Verify ratios
    total_ratio = train_ratio + val_ratio + test_ratio
    if not (0.99 <= total_ratio <= 1.01):
        raise ValueError(f"Split ratios must sum to 1.0, got {total_ratio}")

    # Unique speakers
    unique_speakers = sorted(list(set(r.speaker_id for r in records)))
    if len(unique_speakers) < 3:
        raise ValueError(
            f"Need at least 3 distinct speakers for speaker-independent train/val/test splits, "
            f"found {len(unique_speakers)}: {unique_speakers}"
        )

    # Shuffle speakers deterministically
    rng = random.Random(seed)
    shuffled_speakers = list(unique_speakers)
    rng.shuffle(shuffled_speakers)

    n_speakers = len(shuffled_speakers)
    n_train = max(1, int(round(n_speakers * train_ratio)))
    n_val = max(1, int(round(n_speakers * val_ratio)))
    
    # Ensure all splits get at least 1 speaker and all speakers are assigned
    train_speakers = set(shuffled_speakers[:n_train])
    val_speakers = set(shuffled_speakers[n_train : n_train + n_val])
    test_speakers = set(shuffled_speakers[n_train + n_val :])

    if not test_speakers:
        # Borrow one from train if rounding ate it
        test_speaker = train_speakers.pop()
        test_speakers.add(test_speaker)

    # Strict invariant validation
    assert len(train_speakers & val_speakers) == 0, "Speaker leakage between train and val!"
    assert len(train_speakers & test_speakers) == 0, "Speaker leakage between train and test!"
    assert len(val_speakers & test_speakers) == 0, "Speaker leakage between val and test!"

    train_records = [r for r in records if r.speaker_id in train_speakers]
    val_records = [r for r in records if r.speaker_id in val_speakers]
    test_records = [r for r in records if r.speaker_id in test_speakers]

    logger.info(
        f"Split complete. Speakers: train={len(train_speakers)}, val={len(val_speakers)}, "
        f"test={len(test_speakers)}. Samples: train={len(train_records)}, val={len(val_records)}, "
        f"test={len(test_records)}"
    )

    return train_records, val_records, test_records


def save_manifest_csv(records: List[DatasetManifestRecord], output_path: Union[str, Path]) -> str:
    """
    Writes a list of DatasetManifestRecord to a CSV manifest file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["sample_id", "file_path", "speaker_id", "emotion", "raw_emotion", "duration_sec"]
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r.to_dict())

    return str(path.resolve())


def load_manifest_csv(manifest_path: Union[str, Path]) -> List[DatasetManifestRecord]:
    """
    Loads records from a CSV manifest file.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    records: List[DatasetManifestRecord] = []
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(
                DatasetManifestRecord(
                    sample_id=row["sample_id"],
                    file_path=row["file_path"],
                    speaker_id=row["speaker_id"],
                    emotion=row["emotion"],
                    raw_emotion=row.get("raw_emotion", ""),
                    duration_sec=float(row.get("duration_sec", 0.0)),
                )
            )
    return records


def compute_class_distribution(records: List[DatasetManifestRecord]) -> Dict[str, int]:
    """
    Counts samples per emotion class.
    """
    distribution: Dict[str, int] = {}
    for r in records:
        distribution[r.emotion] = distribution.get(r.emotion, 0) + 1
    return distribution


def compute_class_weights(
    records: List[DatasetManifestRecord],
    emotions: List[str]
) -> Dict[str, float]:
    """
    Computes balanced class weights via inverse frequency:
    weight[c] = total_samples / (num_classes * count[c])
    """
    counts = compute_class_distribution(records)
    total_samples = len(records)
    num_classes = len(emotions)

    weights: Dict[str, float] = {}
    for emo in emotions:
        c = counts.get(emo, 0)
        if c > 0:
            weights[emo] = round(total_samples / float(num_classes * c), 4)
        else:
            weights[emo] = 1.0

    return weights
