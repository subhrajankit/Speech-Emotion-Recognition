"""
Emotion model configuration schema.
Config-driven hyperparameters for model architecture and label mappings.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EmotionModelConfig(BaseModel):
    """
    Configuration for the emotion classification model architecture.
    """
    model_name: str = Field(default="wav2vec2_classifier", description="Model identifier")
    backbone: str = Field(default="facebook/wav2vec2-base", description="Backbone feature extractor")
    embedding_dim: int = Field(default=768, description="Feature extractor output dimension")
    hidden_dim: int = Field(default=256, description="Hidden layer dimension")
    dropout: float = Field(default=0.2, description="Dropout probability")
    pooling: str = Field(default="mean", description="Pooling method: 'mean', 'max', or 'attention'")
    emotions: List[str] = Field(
        default=["neutral", "happy", "sad", "angry"],
        description="Target emotion classes in index order"
    )

    @property
    def num_classes(self) -> int:
        return len(self.emotions)

    @property
    def label_to_id(self) -> Dict[str, int]:
        return {label: i for i, label in enumerate(self.emotions)}

    @property
    def id_to_label(self) -> Dict[int, str]:
        return {i: label for i, label in enumerate(self.emotions)}

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmotionModelConfig":
        return cls(**data)
