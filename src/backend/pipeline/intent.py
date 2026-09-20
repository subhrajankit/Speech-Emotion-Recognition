import re
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class IntentCategory(str, Enum):
    CHAT = "chat"
    KNOWLEDGE = "knowledge"
    COMMAND = "command"

@dataclass
class IntentResult:
    """
    Result of the Intent Classification hard gate.
    """
    category: IntentCategory
    confidence: float
    matched_rule: Optional[str]
    raw_query: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "confidence": self.confidence,
            "matched_rule": self.matched_rule,
            "raw_query": self.raw_query
        }

# Regex patterns for deterministic Command routing
COMMAND_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(set (a )?timer|stopwatch|cancel timer)\b", "timer"),
    (r"\b(set (an? )?alarm|wake me up)\b", "alarm"),
    (r"\b(remind me( to)?|set (a )?reminder)\b", "reminder"),
    (r"\b(calculate|\d+\s*[\+\-\*\/]\s*\d+|what is \d+\s*(plus|minus|times|divided by))\b", "calculator"),
    (r"\b(turn (on|off)|switch (on|off)|volume (up|down|mute))\b", "device_control"),
]

# Phase 18: Explicit Command Whitelist Sandboxing
# No command executes unless its action identifier is explicitly present in this set.
COMMAND_WHITELIST: Dict[str, str] = {
    "timer": "Set or cancel local countdown timer",
    "alarm": "Set local wake alarm",
    "reminder": "Schedule local notification reminder",
    "calculator": "Perform local arithmetic calculation",
    "device_control": "Adjust local audio volume or mute state",
}


# Regex patterns for explicit Knowledge / RAG retrieval routing
KNOWLEDGE_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(according to|in the document(s)?|in the file(s)?|in the pdf)\b", "doc_reference"),
    (r"\b(search (the )?documents?|look up in (the )?(docs|files|manual|handbook))\b", "doc_search"),
    (r"\b(what does the (policy|handbook|manual|document|spec) say)\b", "policy_lookup"),
    (r"\b(company policy|hr policy|refund policy|return policy|terms of service)\b", "policy_query"),
    (r"\b(documentation for|read the readme|check the manual)\b", "manual_lookup"),
]

class IntentRouter:
    """
    Hard Gate Intent Router between ASR and reasoning/retrieval stages.
    Enforces strict branching:
    1. 'command' -> Deterministic operations (calculator, timer, reminder)
    2. 'knowledge' -> Local RAG document retrieval (Phase 6)
    3. 'chat' -> Direct LLM dialogue (Default)

    Gracefully degrades 'knowledge' to 'chat' if FAISS index is missing or unindexed.
    """
    def __init__(self, retriever: Optional[Any] = None):
        self.retriever = retriever
        self._compiled_commands = [(re.compile(pat, re.IGNORECASE), name) for pat, name in COMMAND_PATTERNS]
        self._compiled_knowledge = [(re.compile(pat, re.IGNORECASE), name) for pat, name in KNOWLEDGE_PATTERNS]

    def is_command_whitelisted(self, action_name: str) -> bool:
        """
        Validates whether a detected command action is explicitly in the approved security whitelist.
        """
        base = action_name.replace("command:", "").strip()
        return base in COMMAND_WHITELIST

    def classify(self, transcript: str, retriever: Optional[Any] = None) -> IntentResult:
        """
        Classifies input transcript into one of the 3 intent categories.
        Defaults strictly to 'chat'.
        Falls back to 'chat' if 'knowledge' is matched but the FAISS vector index is missing or corrupt.
        """
        if not transcript or not transcript.strip():
            return IntentResult(
                category=IntentCategory.CHAT,
                confidence=1.0,
                matched_rule=None,
                raw_query=""
            )

        cleaned = transcript.strip()

        # 1. Evaluate Command Gate
        for regex, rule_name in self._compiled_commands:
            if regex.search(cleaned):
                logger.info(f"[IntentRouter] Gate matched COMMAND: {rule_name}")
                return IntentResult(
                    category=IntentCategory.COMMAND,
                    confidence=0.95,
                    matched_rule=f"command:{rule_name}",
                    raw_query=cleaned
                )

        # 2. Evaluate Knowledge Gate (RAG)
        for regex, rule_name in self._compiled_knowledge:
            if regex.search(cleaned):
                active_retriever = retriever if retriever is not None else self.retriever
                if active_retriever is not None and not getattr(active_retriever, "is_loaded", False):
                    logger.warning(
                        f"[IntentRouter] Knowledge intent matched ('{rule_name}'), but FAISS vector index is missing or unloaded. "
                        f"Gracefully falling back to CHAT branch."
                    )
                    return IntentResult(
                        category=IntentCategory.CHAT,
                        confidence=0.80,
                        matched_rule=f"knowledge_fallback:{rule_name}",
                        raw_query=cleaned
                    )

                logger.info(f"[IntentRouter] Gate matched KNOWLEDGE: {rule_name}")
                return IntentResult(
                    category=IntentCategory.KNOWLEDGE,
                    confidence=0.95,
                    matched_rule=f"knowledge:{rule_name}",
                    raw_query=cleaned
                )

        # 3. Default Gate: General Chat (NEVER RAG by default)
        return IntentResult(
            category=IntentCategory.CHAT,
            confidence=1.0,
            matched_rule=None,
            raw_query=cleaned
        )
