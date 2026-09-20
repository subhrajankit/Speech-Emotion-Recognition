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

__all__ = [
    "LanguageRouter",
    "RoutingDecision",
    "LanguageIdentifier",
    "INDIC_LANGUAGES",
    "SENSEVOICE_LANGUAGES",
]
