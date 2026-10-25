"""
Unit tests validating evaluation metrics against hand-calculated ground truth.
Verifies Accuracy, UAR, Per-class Precision/Recall/F1, Macro F1, Weighted F1,
and Confusion Matrix formatting.
"""

import numpy as np
import pytest

from ai.training.metrics import compute_metrics, ClassificationMetrics


def test_compute_metrics_hand_calculated_reference():
    """
    Test against an exact hand-calculated 4-class reference scenario:
    8 samples total, 2 samples per class:
        Classes: ['neutral', 'happy', 'sad', 'angry']
        y_true = [0, 0, 1, 1, 2, 2, 3, 3]
        y_pred = [0, 1, 1, 1, 2, 3, 3, 0]
    """
    classes = ["neutral", "happy", "sad", "angry"]
    y_true = [0, 0, 1, 1, 2, 2, 3, 3]
    y_pred = [0, 1, 1, 1, 2, 3, 3, 0]

    metrics = compute_metrics(y_true, y_pred, classes)

    # 1. Total samples & Accuracy (5 correct out of 8 = 0.625)
    assert metrics.total_samples == 8
    assert metrics.accuracy == pytest.approx(0.625, abs=1e-5)

    # 2. Confusion matrix verification:
    # Row 0: [1, 1, 0, 0]
    # Row 1: [0, 2, 0, 0]
    # Row 2: [0, 0, 1, 1]
    # Row 3: [1, 0, 0, 1]
    expected_cm = np.array([
        [1, 1, 0, 0],
        [0, 2, 0, 0],
        [0, 0, 1, 1],
        [1, 0, 0, 1],
    ], dtype=int)
    np.testing.assert_array_equal(metrics.confusion_matrix, expected_cm)

    # 3. Class 0 ('neutral'): TP=1, FP=1, FN=1 -> Prec=0.5, Rec=0.5, F1=0.5
    m0 = metrics.per_class["neutral"]
    assert m0["precision"] == pytest.approx(0.5, abs=1e-5)
    assert m0["recall"] == pytest.approx(0.5, abs=1e-5)
    assert m0["f1"] == pytest.approx(0.5, abs=1e-5)
    assert m0["support"] == 2.0

    # 4. Class 1 ('happy'): TP=2, FP=1, FN=0 -> Prec=2/3, Rec=1.0, F1=0.8
    m1 = metrics.per_class["happy"]
    assert m1["precision"] == pytest.approx(2.0 / 3.0, abs=1e-5)
    assert m1["recall"] == pytest.approx(1.0, abs=1e-5)
    assert m1["f1"] == pytest.approx(0.8, abs=1e-5)
    assert m1["support"] == 2.0

    # 5. Class 2 ('sad'): TP=1, FP=0, FN=1 -> Prec=1.0, Rec=0.5, F1=2/3
    m2 = metrics.per_class["sad"]
    assert m2["precision"] == pytest.approx(1.0, abs=1e-5)
    assert m2["recall"] == pytest.approx(0.5, abs=1e-5)
    assert m2["f1"] == pytest.approx(2.0 / 3.0, abs=1e-5)
    assert m2["support"] == 2.0

    # 6. Class 3 ('angry'): TP=1, FP=1, FN=1 -> Prec=0.5, Rec=0.5, F1=0.5
    m3 = metrics.per_class["angry"]
    assert m3["precision"] == pytest.approx(0.5, abs=1e-5)
    assert m3["recall"] == pytest.approx(0.5, abs=1e-5)
    assert m3["f1"] == pytest.approx(0.5, abs=1e-5)
    assert m3["support"] == 2.0

    # 7. UAR (Unweighted Average Recall): mean(0.5, 1.0, 0.5, 0.5) = 2.5 / 4 = 0.625
    assert metrics.uar == pytest.approx(0.625, abs=1e-5)

    # 8. Macro F1: mean(0.5, 0.8, 2/3, 0.5) = 2.466667 / 4 ≈ 0.616667
    expected_macro_f1 = (0.5 + 0.8 + (2.0 / 3.0) + 0.5) / 4.0
    assert metrics.macro_f1 == pytest.approx(expected_macro_f1, abs=1e-5)

    # 9. Weighted F1 (supports are equal so equal to Macro F1)
    assert metrics.weighted_f1 == pytest.approx(expected_macro_f1, abs=1e-5)


def test_confusion_matrix_csv_export():
    """Verify CSV serialization of confusion matrix."""
    classes = ["neutral", "happy"]
    y_true = [0, 1]
    y_pred = [0, 0]

    metrics = compute_metrics(y_true, y_pred, classes)
    csv_str = metrics.confusion_matrix_to_csv()

    lines = [line.strip() for line in csv_str.strip().splitlines()]
    assert lines[0] == "true_label,pred_neutral,pred_happy"
    assert lines[1] == "neutral,1,0"
    assert lines[2] == "happy,1,0"


def test_empty_metrics():
    """Empty inputs return zero metrics gracefully without division by zero."""
    metrics = compute_metrics([], [], ["neutral", "happy"])
    assert metrics.total_samples == 0
    assert metrics.accuracy == 0.0
    assert metrics.uar == 0.0
    assert metrics.macro_f1 == 0.0
