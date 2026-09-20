"""
Prompt builder module for VoiceSense AI.
Constructs system prompts conditioned on detected emotion and language,
and manages conversation history window within a configurable token budget.
"""

from typing import List, Dict, Any, Optional

LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "yue": "Cantonese",
    "bn": "Bengali",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
}


def estimate_tokens(text: str) -> int:
    """
    Estimates token count for text using a character and whitespace heuristic.
    Averages ~4 chars per token for English and ~1.5 chars per token for CJK/Indic.
    """
    if not text:
        return 0
    words = len(text.split())
    chars = len(text)
    return max(1, int(max(words * 1.3, chars / 3.5)))


class PromptBuilder:
    """
    Builds structured chat messages for LLM completion conditioned on
    acoustic and lexical perception context.
    """

    DEFAULT_SYSTEM_TEMPLATE = (
        "You are SenseAI, an empathetic, helpful, and concise multilingual voice assistant.\n"
        "Strict Guidelines:\n"
        "1. Emotion Awareness: {emotion_instruction}\n"
        "2. Spoken Conciseness: Answer concisely in 1 to 2 clear sentences suitable for spoken audio playback.\n"
        "3. No Reasoning Chains: Never produce internal thoughts, chain-of-thought, or long reasoning explanations. Provide only the direct spoken response.\n"
        "4. Language & Tone: Reply in the user's spoken language ({language_display}) naturally."
    )

    @classmethod
    def resolve_language_display(cls, language: Optional[str]) -> str:
        if not language:
            return "the user's language"
        lang_code = language.lower().strip()
        return LANGUAGE_NAMES.get(lang_code, lang_code)

    @classmethod
    def resolve_emotion_instruction(cls, emotion: Optional[str]) -> str:
        if not emotion or emotion.lower() in ("neutral", "none", "unknown"):
            return "The user's tone is calm or neutral. Maintain a polite, warm, and natural conversational tone."
        
        emo = emotion.lower().strip()
        if emo in ("sad", "fearful", "disgusted"):
            return f"The user's detected emotional tone is '{emo}'. Acknowledge this with brief, genuine empathy and reassurance, then directly answer."
        elif emo in ("happy", "surprised"):
            return f"The user's detected emotional tone is '{emo}'. Maintain an upbeat, encouraging, and supportive tone."
        elif emo in ("angry", "frustrated"):
            return f"The user's detected emotional tone is '{emo}'. Respond in a calm, soothing, de-escalating manner without being argumentative."
        else:
            return f"The user's detected emotional tone is '{emo}'. Adapt to this emotional tone naturally and briefly, but do not dwell on it."

    @classmethod
    def build_system_prompt(
        cls,
        emotion: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """
        Constructs the system prompt including detected emotion guidance
        and language matching instructions.
        """
        emotion_instruction = cls.resolve_emotion_instruction(emotion)
        language_display = cls.resolve_language_display(language)

        return cls.DEFAULT_SYSTEM_TEMPLATE.format(
            emotion_instruction=emotion_instruction,
            language_display=language_display
        )

    @classmethod
    def build_chat_messages(
        cls,
        transcript: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        emotion: Optional[str] = None,
        language: Optional[str] = None,
        max_history_tokens: int = 1024,
    ) -> List[Dict[str, str]]:
        """
        Builds a full chat messages payload:
        [
          {"role": "system", "content": ...},
          ...retained_history_turns,
          {"role": "user", "content": transcript}
        ]
        Applies a token budget across historical turns, keeping the most recent.
        """
        system_prompt = cls.build_system_prompt(emotion=emotion, language=language)

        # Budget dedicated to historical turns
        available_budget = max(0, max_history_tokens)

        retained_history: List[Dict[str, str]] = []
        if conversation_history:
            accumulated_tokens = 0
            temp_history: List[Dict[str, str]] = []

            for turn in reversed(conversation_history):
                role = turn.get("role")
                content = turn.get("content", "")
                if role not in ("user", "assistant") or not content:
                    continue

                turn_tokens = estimate_tokens(content)
                if accumulated_tokens + turn_tokens <= available_budget:
                    temp_history.append({"role": role, "content": content})
                    accumulated_tokens += turn_tokens
                else:
                    break

            retained_history = list(reversed(temp_history))

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(retained_history)
        messages.append({"role": "user", "content": transcript})

        return messages
