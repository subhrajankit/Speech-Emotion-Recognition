"""
Reproducible Emotion Model Training Pipeline — SCAFFOLD / NOT YET TRAINING.

WARNING: This script does NOT perform real acoustic emotion model training.
It generates dataset manifests and saves the classifier head's RANDOM INITIAL
weights as `untrained_init_weights.npz`. That artifact is an initialization
snapshot for pipeline plumbing tests only — it is NOT a trained checkpoint and
must never be loaded by serving code or presented as a production model.

Features:
- Config-driven (YAML)
- Fixed seeds across torch, numpy, and random
- Environment and git commit hash tracking
- Speaker-independent train/val/test split generation
- Explicit class imbalance handling (weighted loss)
- Saves model checkpoints, run metadata, and evaluation results to docs/training/runs/<run_id>/
"""

import os
import sys
import json
import time
import random
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import yaml

from ai.models.emotion.config import EmotionModelConfig
from ai.models.emotion.model import (
    NumPyEmotionClassifier,
    EmotionClassifier,
    TORCH_AVAILABLE,
)
from ai.training.dataset import (
    DatasetManifestRecord,
    scan_crema_d_directory,
    create_speaker_independent_split,
    save_manifest_csv,
    compute_class_distribution,
    compute_class_weights,
)
from ai.training.evaluate import run_evaluation

logger = logging.getLogger(__name__)


def get_git_commit_hash() -> str:
    """
    Retrieves the current git commit hash.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def get_environment_info() -> Dict[str, str]:
    """
    Captures runtime environment package versions.
    """
    info = {
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "platform": sys.platform,
    }
    if TORCH_AVAILABLE:
        import torch
        info["torch_version"] = torch.__version__
        info["cuda_available"] = str(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["gpu_device"] = torch.cuda.get_device_name(0)
    else:
        info["torch_version"] = "NOT_INSTALLED"
        info["cuda_available"] = "False"

    try:
        import soundfile
        info["soundfile_version"] = soundfile.__version__
    except ImportError:
        pass

    return info


def set_seed(seed: int = 42) -> None:
    """
    Enforces deterministic random state across Python, NumPy, and PyTorch.
    """
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    if TORCH_AVAILABLE:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False


def generate_synthetic_smoke_records(
    num_samples: int = 40,
    num_speakers: int = 6,
    emotions: Optional[List[str]] = None,
) -> List[DatasetManifestRecord]:
    """
    Generates synthetic dataset manifest records for fast smoke testing
    when raw audio datasets are not yet downloaded on the host.
    """
    emotions = emotions or ["neutral", "happy", "sad", "angry"]
    records: List[DatasetManifestRecord] = []
    speakers = [f"speaker_{i:03d}" for i in range(1, num_speakers + 1)]

    for i in range(num_samples):
        spk = speakers[i % len(speakers)]
        emo = emotions[i % len(emotions)]
        records.append(
            DatasetManifestRecord(
                sample_id=f"sample_{i:04d}",
                file_path=f"data/raw/crema_d/smoke_{spk}_{emo}_{i:03d}.wav",
                speaker_id=spk,
                emotion=emo,
                raw_emotion=emo[:3].upper(),
                duration_sec=2.5,
            )
        )
    return records


def train_emotion_model(
    config_path: str,
    output_base_dir: str = "docs/training/runs",
    run_id: Optional[str] = None,
    smoke: bool = False,
) -> Dict[str, Any]:
    """
    Main training execution function.
    """
    start_time = time.time()
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # Resolve Run ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = run_id or f"run_{timestamp}"
    run_dir = Path(output_base_dir) / run_id
    checkpoints_dir = run_dir / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    # Seed
    seed = config_data.get("training", {}).get("seed", 42)
    set_seed(seed)

    # Dataset setup
    dataset_cfg = config_data.get("dataset", {})
    audio_dir = dataset_cfg.get("audio_dir", "data/raw/crema_d")
    target_emotions = dataset_cfg.get("target_emotions", ["neutral", "happy", "sad", "angry"])
    split_ratios = dataset_cfg.get("split_ratios", {"train": 0.70, "val": 0.15, "test": 0.15})
    manifest_dir = Path(dataset_cfg.get("manifest_dir", "data/metadata"))
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # Scan dataset
    records = scan_crema_d_directory(audio_dir, target_emotions=target_emotions)
    is_smoke = smoke or config_data.get("training", {}).get("smoke_test", False) or len(records) == 0

    if is_smoke and len(records) == 0:
        logger.info("Raw audio not found on disk. Generating synthetic records for smoke run.")
        records = generate_synthetic_smoke_records(num_samples=30, num_speakers=6, emotions=target_emotions)

    # Create speaker-independent split
    train_recs, val_recs, test_recs = create_speaker_independent_split(
        records,
        train_ratio=split_ratios.get("train", 0.70),
        val_ratio=split_ratios.get("val", 0.15),
        test_ratio=split_ratios.get("test", 0.15),
        seed=seed,
    )

    # Save manifest files
    train_manifest = manifest_dir / f"{dataset_cfg.get('name', 'crema_d')}_train.csv"
    val_manifest = manifest_dir / f"{dataset_cfg.get('name', 'crema_d')}_val.csv"
    test_manifest = manifest_dir / f"{dataset_cfg.get('name', 'crema_d')}_test.csv"

    save_manifest_csv(train_recs, train_manifest)
    save_manifest_csv(val_recs, val_manifest)
    save_manifest_csv(test_recs, test_manifest)

    # Class distributions & weights
    train_distribution = compute_class_distribution(train_recs)
    val_distribution = compute_class_distribution(val_recs)
    test_distribution = compute_class_distribution(test_recs)

    class_weighting_method = config_data.get("training", {}).get("class_weighting", "balanced_loss")
    class_weights = compute_class_weights(train_recs, target_emotions)

    # Model configuration
    model_cfg_dict = config_data.get("model", {})
    model_cfg_dict["emotions"] = target_emotions
    model_config = EmotionModelConfig.from_dict(model_cfg_dict)

    # Save model config JSON to checkpoint folder
    model_config_file = checkpoints_dir / "model_config.json"
    with open(model_config_file, "w", encoding="utf-8") as f:
        json.dump(model_config.to_dict(), f, indent=2)

    # Model training (PyTorch or NumPy fallback)
    epochs = config_data.get("training", {}).get("epochs", 5)
    batch_size = config_data.get("training", {}).get("batch_size", 16)

    # NumPy reference initialization snapshot.
    # NOTE: no feature extraction or gradient training is performed in this
    # scaffold — the saved weights are the random initialization only.
    np_classifier = NumPyEmotionClassifier(model_config)
    checkpoint_file = checkpoints_dir / "untrained_init_weights.npz"
    np.savez_compressed(
        checkpoint_file,
        **np_classifier.weights
    )
    logger.warning(
        "Saved UNTRAINED random-initialization weights to %s. "
        "This is not a trained emotion model.",
        checkpoint_file,
    )

    training_time = round(time.time() - start_time, 2)

    # Metadata record
    run_metadata = {
        "run_id": run_id,
        "run_type": "smoke_test" if is_smoke else "full_training",
        "timestamp": timestamp,
        "git_commit": get_git_commit_hash(),
        "environment": get_environment_info(),
        "dataset": {
            "name": dataset_cfg.get("name", "crema_d"),
            "target_emotions": target_emotions,
            "total_samples": len(records),
            "split_counts": {
                "train": len(train_recs),
                "val": len(val_recs),
                "test": len(test_recs),
            },
            "speaker_counts": {
                "train": len(set(r.speaker_id for r in train_recs)),
                "val": len(set(r.speaker_id for r in val_recs)),
                "test": len(set(r.speaker_id for r in test_recs)),
            },
            "class_distribution": {
                "train": train_distribution,
                "val": val_distribution,
                "test": test_distribution,
            },
            "class_weighting": {
                "method": class_weighting_method,
                "weights": class_weights,
            },
        },
        "model": model_config.to_dict(),
        "training_params": {
            "epochs": epochs,
            "batch_size": batch_size,
            "seed": seed,
            "training_time_sec": training_time,
            "training_performed": False,
        },
        "checkpoint_status": "UNTRAINED_RANDOM_INITIALIZATION",
        "checkpoint_warning": (
            "untrained_init_weights.npz contains random initial weights only; "
            "no acoustic features were extracted and no training was performed."
        ),
        "artifacts": {
            "checkpoint": str(checkpoint_file.resolve()),
            "model_config": str(model_config_file.resolve()),
            "train_manifest": str(train_manifest.resolve()),
            "val_manifest": str(val_manifest.resolve()),
            "test_manifest": str(test_manifest.resolve()),
        },
    }

    metadata_path = run_dir / "run_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2)

    # Run evaluation on test manifest
    eval_results = run_evaluation(
        manifest_path=str(test_manifest),
        output_dir=str(run_dir),
        config=model_config,
        checkpoint_path=str(checkpoint_file),
        run_sensevoice_baseline=config_data.get("evaluation", {}).get("sensevoice_baseline", True),
    )

    return {
        "run_id": run_id,
        "run_dir": str(run_dir.resolve()),
        "checkpoint": str(checkpoint_file.resolve()),
        "metadata": run_metadata,
        "evaluation": eval_results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Emotion Classification Model")
    parser.add_argument("--config", type=str, default="ai/training/config/crema_d_smoke.yaml", help="Path to config YAML")
    parser.add_argument("--smoke", action="store_true", help="Execute short smoke test")
    parser.add_argument("--run-id", type=str, default=None, help="Custom run identifier")
    args = parser.parse_args()

    res = train_emotion_model(
        config_path=args.config,
        run_id=args.run_id,
        smoke=args.smoke,
    )
    print(f"\nTraining pipeline finished. Run dir: {res['run_dir']}")
    print(f"Metrics: {res['evaluation']['metrics']}")
