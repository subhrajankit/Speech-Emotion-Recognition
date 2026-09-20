"""
AI Speech Inference package.
Exposes SpeechResult, SpeechEngine, and SenseVoiceSpeechEngine.
"""

from ai.inference.types import SpeechResult
from ai.inference.engine import SpeechEngine


def __getattr__(name: str):
    if name in (
        "SenseVoiceSpeechEngine",
        "parse_sensevoice_output",
        "SENSEVOICE_LANG_TAGS",
        "SENSEVOICE_EMO_TAGS",
        "SENSEVOICE_EVENT_TAGS",
    ):
        import ai.inference.sensevoice as _sv
        return getattr(_sv, name)
    if name in (
        "IndicConformerSpeechEngine",
    ):
        import ai.inference.indicconformer as _ic
        return getattr(_ic, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "SpeechResult",
    "SpeechEngine",
    "SenseVoiceSpeechEngine",
    "IndicConformerSpeechEngine",
    "parse_sensevoice_output",
    "SENSEVOICE_LANG_TAGS",
    "SENSEVOICE_EMO_TAGS",
    "SENSEVOICE_EVENT_TAGS",
]
