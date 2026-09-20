import re
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Set, Tuple, Dict, Any
from .indicconformer import IndicConformerASR
from ..models.asr import SenseVoiceASR

logger = logging.getLogger(__name__)

# Hardcoded common Latin-script Hindi words for lightweight Hinglish heuristic
HINGLISH_COMMON_WORDS: Set[str] = {
    "kya", "hai", "hain", "kaise", "ho", "bhai", "yaar", "theek", "haan",
    "nahin", "nahi", "accha", "achha", "mera", "meri", "hum", "aap", "tum",
    "karo", "karna", "raha", "rahi", "rahe", "chahiye", "samajh", "batao",
    "bolo", "chal", "chalo", "kuch", "bahut", "aaj", "kal", "ab", "pehle",
    "kaun", "kahan", "kab", "kyun", "kyu", "wala", "wali", "wale", "toh"
}

# Common English vocabulary words to verify mixed language presence
COMMON_ENGLISH_WORDS: Set[str] = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it",
    "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
    "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
    "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "people", "into", "year", "your", "good", "some", "could",
    "them", "see", "other", "than", "then", "now", "look", "only", "come",
    "its", "over", "think", "also", "back", "after", "use", "two", "how",
    "our", "work", "first", "well", "way", "even", "new", "want", "because",
    "any", "these", "give", "day", "most", "us", "weather", "today", "tomorrow",
    "hello", "hey", "help", "assistant", "call", "play", "music", "song", "please"
}

# The 5 primary languages directly supported by SenseVoiceSmall
SENSEVOICE_LANGUAGES: Set[str] = {"en", "zh", "yue", "ja", "ko"}

@dataclass
class AudioContext:
    """
    Standardized Context Object representing speech recognition and linguistic properties.
    """
    language: str           # e.g., 'en', 'hi', 'hinglish', 'zh', 'ja', 'ko'
    script: str             # 'latin', 'devanagari', 'hanzi', etc.
    mixed_language: bool    # True when code-mixing (e.g. Hinglish) is present
    transcript: str         # Transcribed utterance text
    confidence: float       # Confidence score [0.0 - 1.0]
    model_used: str         # 'sensevoice', 'indicconformer', or 'hinglish_heuristic'
    raw_emotion: str = "neutral"  # SenseVoice SER tag or label

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def detect_script(text: str) -> str:
    """Detects primary script of the transcription."""
    if re.search(r'[\u0900-\u097F]', text):
        return "devanagari"
    elif re.search(r'[\u4E00-\u9FFF]', text):
        return "hanzi"
    elif re.search(r'[\u3040-\u30FF]', text):
        return "japanese"
    elif re.search(r'[\uAC00-\uD7AF]', text):
        return "hangul"
    elif re.search(r'[a-zA-Z]', text):
        return "latin"
    return "unknown"


def evaluate_hinglish_heuristic(transcript: str, confidence: float) -> Tuple[bool, Optional[AudioContext]]:
    """
    Evaluates whether a transcript matches the Hinglish heuristic:
    - Text contains Latin-script Hindi words mixed with English.
    - If criteria are met, returns (True, AudioContext(language="hinglish", script="latin", mixed_language=True, ...))
    """
    words = set(re.findall(r'[a-zA-Z]+', transcript.lower()))
    if not words:
        return False, None

    hindi_matches = words.intersection(HINGLISH_COMMON_WORDS)
    english_matches = words.intersection(COMMON_ENGLISH_WORDS)

    # Condition: contains Latin-script Hindi words AND (contains English words OR confidence is marginal)
    is_mixed = len(hindi_matches) >= 1 and (len(english_matches) >= 1 or (len(words) >= 2 and confidence < 0.85))

    if is_mixed:
        ctx = AudioContext(
            language="hinglish",
            script="latin",
            mixed_language=True,
            transcript=transcript,
            confidence=confidence,
            model_used="hinglish_heuristic"
        )
        return True, ctx

    return False, None


class LanguageRouter:
    """
    Language Router between VAD and ASR engines.
    1. Runs fast Language-ID / SenseVoice pass.
    2. Routes to IndicConformer-600m for Hindi and 21 Indic languages when SenseVoice LID
       is not in {en, zh, yue, ja, ko} or has low confidence.
    3. Evaluates Hinglish heuristic for mixed Latin-script Hindi + English dialogue.
    """
    def __init__(self, sensevoice_asr: SenseVoiceASR, indic_conformer: IndicConformerASR):
        self.sensevoice = sensevoice_asr
        self.indic_conformer = indic_conformer

    def route_transcript(self, text: str, detected_lang: str = "en", confidence: float = 0.9, raw_emotion: str = "neutral") -> AudioContext:
        """
        Routes an existing transcript through linguistic/heuristic checks.
        Useful for classification and testing without raw audio fixtures.
        """
        # Extract potential SenseVoice emotion tags embedded in transcription
        emotion_match = re.search(r'<\|(HAPPY|SAD|ANGRY|NEUTRAL|FEARFUL|DISGUSTED|SURPRISED|EXCITED)\|>', text, re.IGNORECASE)
        if emotion_match:
            raw_emotion = emotion_match.group(1).lower()
            text = re.sub(r'<\|[A-Za-z0-9_]+\|>', '', text).strip()

        script = detect_script(text)

        # 1. Check Devanagari script -> Hindi / Indic
        if script == "devanagari":
            if self.indic_conformer and getattr(self.indic_conformer, "is_loaded", False):
                return AudioContext(
                    language="hi",
                    script="devanagari",
                    mixed_language=False,
                    transcript=text,
                    confidence=confidence,
                    model_used="indicconformer",
                    raw_emotion=raw_emotion
                )
            logger.warning(
                "[LanguageRouter] Devanagari script detected but IndicConformer is unavailable/unloaded. "
                "Gracefully routing through SenseVoice."
            )
            return AudioContext(
                language="hi",
                script="devanagari",
                mixed_language=False,
                transcript=text,
                confidence=confidence,
                model_used="sensevoice",
                raw_emotion=raw_emotion
            )

        # 2. Check Hinglish heuristic on Latin text
        if script == "latin":
            is_hinglish, hinglish_ctx = evaluate_hinglish_heuristic(text, confidence)
            if is_hinglish and hinglish_ctx:
                hinglish_ctx.raw_emotion = raw_emotion
                return hinglish_ctx

        # 3. Check SenseVoice supported languages
        if detected_lang in SENSEVOICE_LANGUAGES and confidence >= 0.6:
            return AudioContext(
                language=detected_lang,
                script=script,
                mixed_language=False,
                transcript=text,
                confidence=confidence,
                model_used="sensevoice",
                raw_emotion=raw_emotion
            )

        # 4. Fallback to IndicConformer for other Indic languages if loaded
        if self.indic_conformer and getattr(self.indic_conformer, "is_loaded", False):
            return AudioContext(
                language="hi" if script == "devanagari" else detected_lang,
                script=script,
                mixed_language=False,
                transcript=text,
                confidence=confidence,
                model_used="indicconformer",
                raw_emotion=raw_emotion
            )

        logger.warning(
            "[LanguageRouter] IndicConformer unavailable/unloaded. "
            "Gracefully degrading to SenseVoice transcription (English/global)."
        )
        return AudioContext(
            language="en" if script != "devanagari" else "hi",
            script=script,
            mixed_language=False,
            transcript=text,
            confidence=confidence,
            model_used="sensevoice",
            raw_emotion=raw_emotion
        )


    def route_audio(self, pcm_bytes: bytes) -> AudioContext:
        """
        Full audio routing pass:
        1. Run SenseVoice ASR / LID.
        2. If SenseVoice confidence is low or language is not in its 5 supported languages,
           fall back to IndicConformer-600m (if loaded).
        3. Check Hinglish heuristic.
        """
        if not pcm_bytes:
            return AudioContext(
                language="en",
                script="latin",
                mixed_language=False,
                transcript="",
                confidence=0.0,
                model_used="none"
            )

        # Step 1: Run SenseVoice pass
        sv_text = self.sensevoice.transcribe(pcm_bytes)
        sv_confidence = 0.85 if sv_text else 0.0
        script = detect_script(sv_text)

        # If Devanagari or non-SenseVoice script detected, or low confidence
        if script == "devanagari" or sv_confidence < 0.6:
            # Check if IndicConformer is loaded and available
            if self.indic_conformer and getattr(self.indic_conformer, "is_loaded", False):
                ic_text, ic_confidence = self.indic_conformer.transcribe(pcm_bytes, target_lang="hi")
                if ic_confidence > sv_confidence:
                    return AudioContext(
                        language="hi",
                        script=detect_script(ic_text),
                        mixed_language=False,
                        transcript=ic_text,
                        confidence=ic_confidence,
                        model_used="indicconformer"
                    )
            else:
                logger.warning(
                    "[LanguageRouter] IndicConformer unavailable/unloaded. "
                    "Gracefully serving speech via SenseVoice instead."
                )

        # Step 2: Evaluate transcript through router
        return self.route_transcript(sv_text, detected_lang="en", confidence=sv_confidence)
