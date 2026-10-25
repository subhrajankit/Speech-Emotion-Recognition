"""
Emotion model training, dataset preprocessing, and evaluation package.
"""

from ai.training.dataset import (
    create_speaker_independent_split,
    scan_crema_d_directory,
    save_manifest_csv,
    load_manifest_csv,
    compute_class_weights,
    compute_class_distribution,
)
from ai.training.metrics import compute_metrics, ClassificationMetrics

__all__ = [
    "create_speaker_independent_split",
    "scan_crema_d_directory",
    "save_manifest_csv",
    "load_manifest_csv",
    "compute_class_weights",
    "compute_class_distribution",
    "compute_metrics",
    "ClassificationMetrics",
]
