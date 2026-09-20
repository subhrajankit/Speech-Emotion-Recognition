"""
Prediction schema for /api/predict.
Extends SpeechResult with an optional assistant block for downstream LLM phases.
"""

from typing import Optional, Dict, Any
from pydantic import Field

from ai.inference.types import SpeechResult


class PredictionResponse(SpeechResult):
    """
    Extends SpeechResult with an optional assistant block.
    In Phase 2, assistant defaults to None. Later phases populate it with LLM responses.
    """
    assistant: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional downstream assistant response block added by future phases."
    )
