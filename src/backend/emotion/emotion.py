import re
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Set, Optional

logger = logging.getLogger(__name__)

# Approximate Valence/Arousal Coordinate Mapping (Russell's Circumplex Model of Affect)
# NOTE: This is a fixed lookup approximation for SenseVoice labels, not a learned continuous regression.
SENSEVOICE_EMOTION_COORDINATES: Dict[str, Tuple[float, float]] = {
    "neutral":   (0.0, 0.0),
    "happy":     (0.8, 0.6),
    "sad":       (-0.7, -0.4),
    "angry":     (-0.6, 0.8),
    "fearful":   (-0.6, 0.7),
    "disgusted": (-0.6, 0.3),
    "surprised": (0.4, 0.8),
    "excited":   (0.8, 0.8),
}

# Lightweight lexical sentiment dictionaries (fast, zero model overhead)
POSITIVE_WORDS: Set[str] = {
    "good", "great", "excellent", "amazing", "wonderful", "happy", "love",
    "awesome", "pleased", "delighted", "fantastic", "glad", "nice", "perfect",
    "brilliant", "super", "cool", "thank", "thanks", "helpful", "appreciate",
    "accha", "badhiya", "shukriya", "dhanyawad"
}

NEGATIVE_WORDS: Set[str] = {
    "bad", "terrible", "horrible", "awful", "sad", "unhappy", "angry", "hate",
    "worst", "upset", "frustrated", "disappointed", "poor", "pain", "hurt",
    "annoyed", "wrong", "fail", "failed", "broken", "useless", "stupid",
    "kharab", "ganda", "pareshan"
}

@dataclass
class EmotionState:
    """
    Richer emotional state representing acoustic SER and lexical polarity.
    """
    primary: str            # 'neutral', 'happy', 'sad', 'angry', etc.
    confidence: float       # [0.0, 1.0]
    valence: float          # [-1.0, 1.0] Pleasantness vs. Unpleasantness
    arousal: float          # [-1.0, 1.0] Low Activation vs. High Activation
    lexical_polarity: float = 0.0 # [-1.0, 1.0] Text sentiment score

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_lexical_polarity(text: str) -> float:
    """
    Calculates quick text sentiment polarity in range [-1.0, 1.0]
    using lightweight lexicon matching.
    """
    if not text:
        return 0.0

    tokens = re.findall(r'[a-zA-Z\u0900-\u097F]+', text.lower())
    if not tokens:
        return 0.0

    pos_count = sum(1 for w in tokens if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in tokens if w in NEGATIVE_WORDS)

    total = pos_count + neg_count
    if total == 0:
        return 0.0

    return (pos_count - neg_count) / float(total)


def extract_sensevoice_emotion_label(raw_tag_or_label: str) -> str:
    """
    Cleans SenseVoice raw output tag (e.g. '<|HAPPY|>' -> 'happy').
    """
    if not raw_tag_or_label:
        return "neutral"

    cleaned = raw_tag_or_label.replace("<|", "").replace("|>", "").strip().lower()
    return cleaned if cleaned in SENSEVOICE_EMOTION_COORDINATES else "neutral"


class EmotionAnalyzer:
    """
    Emotion Analyzer fusing SenseVoice Speech Emotion Recognition (SER)
    with lexical transcript polarity.
    """
    def __init__(self):
        self.coordinates = SENSEVOICE_EMOTION_COORDINATES

    def analyze(
        self,
        raw_emotion: str = "neutral",
        confidence: float = 0.85,
        transcript: str = ""
    ) -> EmotionState:
        """
        Fuses acoustic emotion classification with lexical text sentiment.
        """
        primary = extract_sensevoice_emotion_label(raw_emotion)
        base_valence, base_arousal = self.coordinates.get(primary, (0.0, 0.0))
        lexical_pol = calculate_lexical_polarity(transcript)

        # Valence modulation:
        # If acoustic emotion is neutral, lexical sentiment can shift valence
        if primary == "neutral":
            fused_valence = 0.5 * lexical_pol
            fused_arousal = 0.2 * abs(lexical_pol)
            # If lexical sentiment is strongly polarized, adjust primary label
            if lexical_pol > 0.4:
                primary = "happy"
            elif lexical_pol < -0.4:
                primary = "sad"
        else:
            # If acoustic emotion is distinct, fuse acoustic (70%) with lexical (30%)
            fused_valence = (0.7 * base_valence) + (0.3 * lexical_pol)
            fused_arousal = base_arousal

        # Clamp values to [-1.0, 1.0]
        fused_valence = max(-1.0, min(1.0, round(fused_valence, 3)))
        fused_arousal = max(-1.0, min(1.0, round(fused_arousal, 3)))

        return EmotionState(
            primary=primary,
            confidence=round(confidence, 2),
            valence=fused_valence,
            arousal=fused_arousal,
            lexical_polarity=round(lexical_pol, 2)
        )
