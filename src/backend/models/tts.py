"""
Backward-compatibility adapter for IndicParlerTTS.
Implementation moved to src.backend.tts.indic_parler.
"""
from ..tts.indic_parler import IndicParlerTTS, EMOTION_STYLE_MAPPING, get_tts_style_description

__all__ = [
    "IndicParlerTTS",
    "EMOTION_STYLE_MAPPING",
    "get_tts_style_description"
]

