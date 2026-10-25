"""
Comprehensive evaluation metrics for Speech Emotion Recognition.
Pure NumPy implementation providing:
- Overall Accuracy
- Unweighted Average Recall (UAR / Balanced Accuracy)
- Per-class Precision, Recall, and F1
- Macro F1 and Weighted F1
- Confusion Matrix (array, CSV string, text heatmap)
"""

import csv
import io
from typing import Dict, List, Any, Optional, Union
import numpy as np


class ClassificationMetrics:
    """
    Container for classification evaluation metrics.
    """
    def __init__(
        self,
        accuracy: float,
        uar: float,
        macro_f1: float,
        weighted_f1: float,
        per_class: Dict[str, Dict[str, float]],
        confusion_matrix: np.ndarray,
        classes: List[str],
        total_samples: int,
    ):
        self.accuracy = accuracy
        self.uar = uar
        self.macro_f1 = macro_f1
        self.weighted_f1 = weighted_f1
        self.per_class = per_class
        self.confusion_matrix = confusion_matrix
        self.classes = classes
        self.total_samples = total_samples

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_samples": self.total_samples,
            "accuracy": round(self.accuracy, 4),
            "uar": round(self.uar, 4),
            "macro_f1": round(self.macro_f1, 4),
            "weighted_f1": round(self.weighted_f1, 4),
            "per_class": {
                cls: {k: round(v, 4) for k, v in metrics.items()}
                for cls, metrics in self.per_class.items()
            },
            "confusion_matrix": self.confusion_matrix.tolist(),
            "classes": self.classes,
        }

    def confusion_matrix_to_csv(self) -> str:
        """
        Serializes confusion matrix to CSV string format.
        Rows: True label; Columns: Predicted label.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["true_label"] + [f"pred_{c}" for c in self.classes])
        for i, cls in enumerate(self.classes):
            row = [cls] + [int(self.confusion_matrix[i, j]) for j in range(len(self.classes))]
            writer.writerow(row)
        return output.getvalue()

    def summary_table(self) -> str:
        """
        Formatted ASCII text table of the evaluation results.
        """
        lines = [
            f"{'Class':<12} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Support':<8}",
            "-" * 60,
        ]
        for cls in self.classes:
            m = self.per_class[cls]
            lines.append(
                f"{cls:<12} | {m['precision']:<10.4f} | {m['recall']:<10.4f} | {m['f1']:<10.4f} | {int(m['support']):<8}"
            )
        lines.append("-" * 60)
        lines.append(f"Accuracy:    {self.accuracy:.4f}")
        lines.append(f"UAR:         {self.uar:.4f} (Unweighted Average Recall)")
        lines.append(f"Macro F1:    {self.macro_f1:.4f}")
        lines.append(f"Weighted F1: {self.weighted_f1:.4f}")
        return "\n".join(lines)


def compute_metrics(
    y_true: Union[List[int], np.ndarray],
    y_pred: Union[List[int], np.ndarray],
    classes: List[str],
) -> ClassificationMetrics:
    """
    Computes all standard SER evaluation metrics from true and predicted class indices.
    """
    y_true_arr = np.asarray(y_true, dtype=int)
    y_pred_arr = np.asarray(y_pred, dtype=int)

    if len(y_true_arr) != len(y_pred_arr):
        raise ValueError(
            f"y_true (len {len(y_true_arr)}) and y_pred (len {len(y_pred_arr)}) must have the same length"
        )

    num_classes = len(classes)
    total_samples = len(y_true_arr)

    if total_samples == 0:
        return ClassificationMetrics(
            accuracy=0.0,
            uar=0.0,
            macro_f1=0.0,
            weighted_f1=0.0,
            per_class={c: {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0} for c in classes},
            confusion_matrix=np.zeros((num_classes, num_classes), dtype=int),
            classes=classes,
            total_samples=0,
        )

    # Compute confusion matrix C[i, j] = count of (true=i, pred=j)
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true_arr, y_pred_arr):
        if 0 <= t < num_classes and 0 <= p < num_classes:
            cm[t, p] += 1

    accuracy = float(np.sum(y_true_arr == y_pred_arr)) / float(total_samples)

    per_class: Dict[str, Dict[str, float]] = {}
    recalls = []
    f1s = []
    supports = []

    for i, cls_name in enumerate(classes):
        tp = float(cm[i, i])
        fp = float(np.sum(cm[:, i]) - tp)
        fn = float(np.sum(cm[i, :]) - tp)
        support = float(np.sum(cm[i, :]))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class[cls_name] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        recalls.append(recall)
        f1s.append(f1)
        supports.append(support)

    uar = float(np.mean(recalls)) if recalls else 0.0
    macro_f1 = float(np.mean(f1s)) if f1s else 0.0

    # Weighted F1
    if total_samples > 0:
        weighted_f1 = float(sum(f1 * sup for f1, sup in zip(f1s, supports)) / float(total_samples))
    else:
        weighted_f1 = 0.0

    return ClassificationMetrics(
        accuracy=accuracy,
        uar=uar,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        per_class=per_class,
        confusion_matrix=cm,
        classes=classes,
        total_samples=total_samples,
    )
