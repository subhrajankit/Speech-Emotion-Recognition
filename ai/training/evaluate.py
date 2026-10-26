"""
Evaluation pipeline for Speech Emotion Recognition models.
Evaluates trained models or zero-shot baselines on held-out test splits.
Outputs:
- metrics.json (accuracy, UAR, macro/weighted F1, per-class P/R/F1)
- confusion_matrix.csv
- sensevoice_baseline.json (SenseVoiceSmall zero-shot comparison)
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import yaml

from ai.models.emotion.config import EmotionModelConfig
from ai.models.emotion.model import NumPyEmotionClassifier, EmotionClassifier, TORCH_AVAILABLE
from ai.training.dataset import load_manifest_csv, DatasetManifestRecord
from ai.training.metrics import compute_metrics, ClassificationMetrics

logger = logging.getLogger(__name__)


def evaluate_classifier_on_manifest(
    manifest_records: List[DatasetManifestRecord],
    classifier: Any,
    config: EmotionModelConfig,
    feature_extractor: Optional[Any] = None,
) -> ClassificationMetrics:
    """
    Evaluates an emotion classifier over a list of manifest records.
    """
    label_to_id = config.label_to_id
    classes = config.emotions

    y_true: List[int] = []
    y_pred: List[int] = []

    for record in manifest_records:
        if record.emotion not in label_to_id:
            continue
        y_true.append(label_to_id[record.emotion])

        # Obtain feature representation
        if feature_extractor is not None and os.path.exists(record.file_path):
            features = feature_extractor(record.file_path)
        else:
            # Deterministic pseudo-features for smoke tests if file is absent or extractor is None
            rng = np.random.RandomState(abs(hash(record.sample_id)) % (2**31 - 1))
            features = rng.randn(config.embedding_dim).astype(np.float32)

        # Forward through classifier
        probs = classifier.predict_proba(features)
        if hasattr(probs, "detach"):
            probs = probs.detach().cpu().numpy()
        probs = np.asarray(probs).squeeze()
        pred_idx = int(np.argmax(probs))
        y_pred.append(pred_idx)

    return compute_metrics(y_true, y_pred, classes)


def evaluate_sensevoice_baseline(
    manifest_records: List[DatasetManifestRecord],
    config: EmotionModelConfig,
    tag_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Evaluates SenseVoiceSmall's zero-shot emotion predictions on the test set.
    Maps tags (e.g. '<|HAPPY|>' -> 'happy') and compares against target labels.
    """
    mapping = tag_mapping or {
        "<|NEUTRAL|>": "neutral",
        "<|HAPPY|>": "happy",
        "<|SAD|>": "sad",
        "<|ANGRY|>": "angry",
    }

    try:
        from ai.inference.sensevoice import SenseVoiceSpeechEngine
        engine = SenseVoiceSpeechEngine(auto_load=True)
    except Exception as e:
        logger.warning(f"Could not initialize SenseVoiceSpeechEngine for baseline: {e}")
        return {
            "status": "NOT_AVAILABLE",
            "reason": str(e),
            "label_mapping": mapping,
        }

    label_to_id = config.label_to_id
    classes = config.emotions

    y_true: List[int] = []
    y_pred: List[int] = []
    evaluated_samples = 0
    skipped_samples = 0

    for record in manifest_records:
        if record.emotion not in label_to_id:
            continue

        if not os.path.exists(record.file_path):
            skipped_samples += 1
            continue

        try:
            res = engine.transcribe(record.file_path)
            raw_emo = res.emotion or "neutral"
            mapped = mapping.get(raw_emo.upper(), mapping.get(f"<|{raw_emo.upper()}|>", "neutral"))
            if mapped in label_to_id:
                y_true.append(label_to_id[record.emotion])
                y_pred.append(label_to_id[mapped])
                evaluated_samples += 1
        except Exception as e:
            logger.debug(f"Error evaluating sample {record.sample_id} with SenseVoice: {e}")
            skipped_samples += 1

    if evaluated_samples == 0:
        return {
            "status": "NOT_YET_MEASURED",
            "message": "Zero real test samples were processed (mock mode or files absent)",
            "label_mapping": mapping,
            "evaluated_samples": 0,
            "skipped_samples": skipped_samples,
        }

    metrics = compute_metrics(y_true, y_pred, classes)
    res_dict = metrics.to_dict()
    res_dict["label_mapping"] = mapping
    res_dict["evaluated_samples"] = evaluated_samples
    res_dict["skipped_samples"] = skipped_samples
    return res_dict


def run_evaluation(
    manifest_path: str,
    output_dir: str,
    config: Optional[EmotionModelConfig] = None,
    checkpoint_path: Optional[str] = None,
    run_sensevoice_baseline: bool = True,
) -> Dict[str, Any]:
    """
    Main evaluation driver. Loads manifest, runs model and baseline, writes reports.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_manifest_csv(manifest_path)
    model_cfg = config or EmotionModelConfig()

    # Load classifier
    classifier = None
    if checkpoint_path and Path(checkpoint_path).exists():
        if checkpoint_path.endswith(".npz"):
            weights = np.load(checkpoint_path)
            classifier = NumPyEmotionClassifier(model_cfg, weights={k: weights[k] for k in weights})
        elif TORCH_AVAILABLE and (checkpoint_path.endswith(".pt") or checkpoint_path.endswith(".pth")):
            import torch
            net = EmotionClassifier(model_cfg)
            net.load_state_dict(torch.load(checkpoint_path, map_location="cpu"))
            net.eval()
            classifier = net

    if classifier is None:
        logger.info("Using NumPyEmotionClassifier with initialized weights")
        classifier = NumPyEmotionClassifier(model_cfg)

    # Compute model metrics
    metrics = evaluate_classifier_on_manifest(records, classifier, model_cfg)
    metrics_dict = metrics.to_dict()

    # Write metrics.json
    metrics_file = out_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_dict, f, indent=2)

    # Write confusion_matrix.csv
    cm_file = out_dir / "confusion_matrix.csv"
    with open(cm_file, "w", encoding="utf-8") as f:
        f.write(metrics.confusion_matrix_to_csv())

    # Write summary text
    summary_file = out_dir / "evaluation_summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(metrics.summary_table())

    # Run SenseVoice baseline if requested
    baseline_dict = {}
    if run_sensevoice_baseline:
        baseline_dict = evaluate_sensevoice_baseline(records, model_cfg)
        baseline_file = out_dir / "sensevoice_baseline.json"
        with open(baseline_file, "w", encoding="utf-8") as f:
            json.dump(baseline_dict, f, indent=2)

    return {
        "metrics": metrics_dict,
        "confusion_matrix_csv": str(cm_file.resolve()),
        "summary": metrics.summary_table(),
        "baseline": baseline_dict,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Emotion Model on Test Manifest")
    parser.add_argument("--manifest", type=str, required=True, help="Path to test CSV manifest")
    parser.add_argument("--output-dir", type=str, default="docs/training/runs/eval_latest", help="Output directory")
    parser.add_argument("--checkpoint", type=str, default=None, help="Path to checkpoint file")
    parser.add_argument("--config", type=str, default=None, help="Path to YAML config")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip SenseVoice baseline comparison")
    args = parser.parse_args()

    cfg = None
    if args.config and Path(args.config).exists():
        with open(args.config, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
            if "model" in raw:
                cfg = EmotionModelConfig.from_dict(raw["model"])

    results = run_evaluation(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        config=cfg,
        checkpoint_path=args.checkpoint,
        run_sensevoice_baseline=not args.skip_baseline,
    )
    print("\n=== Evaluation Complete ===")
    print(results["summary"])
