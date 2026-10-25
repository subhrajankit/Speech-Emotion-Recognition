"""
Emotion classification neural head architecture.
Supports PyTorch nn.Module when torch is installed, with a standalone NumPy
inference fallback for lightweight deployments.
"""

from typing import Dict, Any, Optional, Tuple, Union
import numpy as np

from ai.models.emotion.config import EmotionModelConfig

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None


if TORCH_AVAILABLE:
    class AttentionPooling(nn.Module):
        """
        Learned attention pooling over temporal feature sequences.
        """
        def __init__(self, input_dim: int):
            super().__init__()
            self.attention = nn.Sequential(
                nn.Linear(input_dim, 128),
                nn.Tanh(),
                nn.Linear(128, 1)
            )

        def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
            # x: (batch_size, seq_len, input_dim)
            weights = self.attention(x)  # (batch_size, seq_len, 1)
            if mask is not None:
                weights = weights.masked_fill(mask.unsqueeze(-1) == 0, -1e9)
            weights = F.softmax(weights, dim=1)
            pooled = torch.sum(x * weights, dim=1)  # (batch_size, input_dim)
            return pooled

    class EmotionClassifier(nn.Module):
        """
        PyTorch classification head on top of audio feature representations.
        """
        def __init__(self, config: EmotionModelConfig):
            super().__init__()
            self.config = config

            if config.pooling == "attention":
                self.pool = AttentionPooling(config.embedding_dim)
            else:
                self.pool = None

            self.norm = nn.LayerNorm(config.embedding_dim)
            self.fc1 = nn.Linear(config.embedding_dim, config.hidden_dim)
            self.act = nn.ReLU()
            self.dropout = nn.Dropout(config.dropout)
            self.fc2 = nn.Linear(config.hidden_dim, config.num_classes)

        def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
            """
            Args:
                x: (batch, seq_len, embedding_dim) or (batch, embedding_dim)
            Returns:
                logits: (batch, num_classes)
            """
            if x.dim() == 3:
                if self.pool is not None:
                    pooled = self.pool(x, mask=mask)
                elif self.config.pooling == "max":
                    pooled = torch.max(x, dim=1)[0]
                else:  # 'mean'
                    if mask is not None:
                        mask_expanded = mask.unsqueeze(-1).float()
                        sum_x = torch.sum(x * mask_expanded, dim=1)
                        count = torch.clamp(mask_expanded.sum(dim=1), min=1.0)
                        pooled = sum_x / count
                    else:
                        pooled = torch.mean(x, dim=1)
            else:
                pooled = x

            out = self.norm(pooled)
            out = self.fc1(out)
            out = self.act(out)
            out = self.dropout(out)
            logits = self.fc2(out)
            return logits

        def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
            """
            Compute softmax class probabilities.
            """
            self.eval()
            with torch.no_grad():
                logits = self.forward(x)
                probs = F.softmax(logits, dim=-1)
            return probs
else:
    class EmotionClassifier:  # type: ignore
        def __init__(self, config: EmotionModelConfig):
            self.config = config
            raise RuntimeError(
                "PyTorch is not installed. To use EmotionClassifier with PyTorch, "
                "install torch via `pip install torch`."
            )


def softmax_numpy(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """
    Numerically stable softmax on NumPy arrays.
    """
    exp_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return exp_x / np.sum(exp_x, axis=axis, keepdims=True)


class NumPyEmotionClassifier:
    """
    Lightweight, dependency-free NumPy emotion classification head.
    Used for inference and testing when PyTorch is optional or offline.
    """
    def __init__(self, config: EmotionModelConfig, weights: Optional[Dict[str, np.ndarray]] = None):
        self.config = config
        self.weights = weights or self._initialize_weights()

    def _initialize_weights(self) -> Dict[str, np.ndarray]:
        # Deterministic Xavier/He initialization for tests and smoke runs
        rng = np.random.RandomState(42)
        emb_dim = self.config.embedding_dim
        hid_dim = self.config.hidden_dim
        num_classes = self.config.num_classes

        w1 = rng.randn(emb_dim, hid_dim).astype(np.float32) * np.sqrt(2.0 / emb_dim)
        b1 = np.zeros(hid_dim, dtype=np.float32)
        w2 = rng.randn(hid_dim, num_classes).astype(np.float32) * np.sqrt(2.0 / hid_dim)
        b2 = np.zeros(num_classes, dtype=np.float32)
        gamma = np.ones(emb_dim, dtype=np.float32)
        beta = np.zeros(emb_dim, dtype=np.float32)

        return {
            "w1": w1, "b1": b1,
            "w2": w2, "b2": b2,
            "gamma": gamma, "beta": beta
        }

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        x: (batch, seq_len, emb_dim) or (batch, emb_dim) or (emb_dim,)
        """
        if x.ndim == 1:
            x = x.reshape(1, -1)
        elif x.ndim == 3:
            x = np.mean(x, axis=1)

        # LayerNorm
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        x_norm = (x - mean) / np.sqrt(var + 1e-5)
        x_norm = x_norm * self.weights["gamma"] + self.weights["beta"]

        # FC1 + ReLU
        h = np.maximum(0.0, np.dot(x_norm, self.weights["w1"]) + self.weights["b1"])

        # FC2
        logits = np.dot(h, self.weights["w2"]) + self.weights["b2"]
        return logits

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        logits = self.forward(x)
        return softmax_numpy(logits, axis=-1)
