"""
AI Routing Package for VoiceSense AI.
Handles language routing, ASR engine dispatch, and intent gating.
"""

from ai.routing.language_router import (
    LanguageRouter,
    RoutingDecision,
    LanguageIdentifier,
    INDIC_LANGUAGES,
    SENSEVOICE_LANGUAGES,
)
from ai.routing.language_identifier import VoxLingua107LanguageIdentifier

__all__ = [
    "LanguageRouter",
    "RoutingDecision",
    "LanguageIdentifier",
    "VoxLingua107LanguageIdentifier",
    "INDIC_LANGUAGES",
    "SENSEVOICE_LANGUAGES",
]
