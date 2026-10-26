"""
Intent Router for VoiceSense AI.
Strict hard gate separating conversational dialogue from document retrieval.
Normal conversation must NEVER touch FAISS or retrieve documents.

Returns:
    {intent: "chat" | "knowledge_query", score: float, method: str}
"""

from dataclasses import dataclass, asdict
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from rag.embeddings import MultilingualE5Embeddings

logger = logging.getLogger(__name__)


@dataclass
class IntentClassification:
    intent: str  # "chat" | "knowledge_query"
    score: float
    method: str  # "rule" | "embedding_similarity" | "default_chat"
    raw_query: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Explicit knowledge query regex patterns (English, Hindi Devanagari, Hinglish Latin)
KNOWLEDGE_RULES: List[Tuple[str, str]] = [
    # English patterns
    (r"\baccording to (the )?(\w+ )*(document|doc|file|pdf|policy|handbook|manual|spec|guidelines?|contract|guide|rules?)\b", "en_according_doc"),
    (r"\bin the (\w+ )*(document|doc|file|pdf|policy|handbook|manual|spec|contract|guidelines?|code of conduct)\b", "en_in_doc"),
    (r"\bwhat does (the |section \d+ of the )?(\w+ )*(policy|handbook|manual|document|spec|guidelines?|contract|code of conduct) (say|specify|state)\b", "en_doc_say"),
    (r"\bsearch (the )?(\w+ )*(documents?|docs|files?|manual|handbook|pdf)\b", "en_search_doc"),
    (r"\blook up (in )?(the )?(\w+ )*(docs|files|manual|handbook|policy|reimbursement limit)\b", "en_lookup_doc"),
    (r"\bcheck (the )?(\w+ )*(manual|handbook|policy|schedule|guidelines?|rules?|contract|spec)\b", "en_check_doc"),
    (r"\b(refund window|refund policy|warranty coverage|parental leave|maternity leave|leave policy|sick leave|severance policy)\b", "en_specific_policy"),
    (r"\b(termination clause|confidentiality obligations|reimbursement limit|working hours for remote|gift acceptance)\b", "en_policy_clause"),
    (r"\b(system requirements for installation|api rate limits?|server maintenance schedule)\b", "en_technical_spec"),
    
    # Hindi Devanagari patterns
    (r"(पॉलिसी|दस्तावेज़|हैंडबुक|मैन्युअल|गाइड|फाइल|कांट्रैक्ट|डॉक्यूमेंट|नियम पुस्तिका) (के अनुसार|में|के मुताबिक)", "hi_doc_reference"),
    (r"(दस्तावेज़|फाइल|मैन्युअल|हैंडबुक|डॉक्यूमेंट) (में क्या लिखा है|चेक करें|देखें|बताए गए|दिए गए)", "hi_doc_query"),
    (r"(रिफंड कितने दिनों में|वारंटी की क्या शर्तें|मैटरनिटी लीव|सर्वर मेंटेनेंस का क्या समय|नोटिस पीरियड|भत्ते की अधिकतम सीमा|सिक्योरिटी नियमों|कैंसिलेशन फीस)", "hi_policy_terms"),

    # Hinglish Latin patterns
    (r"\b(docs?|documents?|files?|pdf|policy|handbook|manual|guidelines?) mein (\w+ )*(check|dekho|kya|likha|rules|coverage|requirements)\b", "hinglish_doc_query"),
    (r"\b(company policy|employee handbook|hr manual|document|file|guidelines?|handbook) ke (according|hisab|mutabiq)\b", "hinglish_according_policy"),
    (r"\baccording to (the )?(\w+ )*(file|doc|document|pdf|policy)\b", "hinglish_according_doc"),
    (r"\b(leave policy|refund kab tak|warranty kitne saal|overtime pay|travel allowance|resignation notice period|health insurance coverage|remote work ke kya rules)\b", "hinglish_terms"),
]

# Knowledge anchor exemplars for Tier 2 embedding similarity
KNOWLEDGE_EXEMPLARS: List[str] = [
    "What does the policy state about employee benefits?",
    "Where in the documentation can I find setup steps?",
    "What are the terms of the service agreement?",
    "How does the refund guarantee work according to documents?",
    "What is the scheduled downtime mentioned in the maintenance doc?",
    "कंपनी की पॉलिसी में क्या नियम दिए गए हैं?",
    "दस्तावेज़ के आधार पर क्या शर्तें हैं?",
    "Policy ke hisab se company ke rules kya hain?",
    "Uploaded documents mein specification check karo.",
]

# Conversational chat anchor exemplars
CHAT_EXEMPLARS: List[str] = [
    "Hello, how are you today?",
    "Good morning, tell me a joke.",
    "I am feeling very tired and stressed today.",
    "Thank you for your assistance, you are very helpful.",
    "What should I do this evening?",
    "नमस्ते, आप कैसे हैं?",
    "मुझे बहुत अच्छा लग रहा है आज।",
    "Hi yaar, kya chal raha hai?",
    "Bhai thoda rest karne jaa raha hoon.",
]


class IntentRouter:
    """
    Two-Tier Hybrid Intent Router Gate:
    1. Tier 1 (Regex Rules): Sub-millisecond matching of explicit knowledge phrases.
    2. Tier 2 (Exemplar Cosine Similarity): Fallback embedding similarity via multilingual-e5-small.
    3. Tier 3 (Default): Fallback unconditionally to 'chat'.
    """

    def __init__(
        self,
        embedder: Optional[MultilingualE5Embeddings] = None,
        similarity_threshold: float = 0.80,
    ):
        self.embedder = embedder or MultilingualE5Embeddings()
        self.similarity_threshold = similarity_threshold
        self._compiled_rules = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in KNOWLEDGE_RULES
        ]

        # Lazy-computed exemplar embeddings
        self._knowledge_anchor_vecs: Optional[np.ndarray] = None
        self._chat_anchor_vecs: Optional[np.ndarray] = None

    def _ensure_anchor_embeddings(self) -> None:
        if self._knowledge_anchor_vecs is None:
            self._knowledge_anchor_vecs = self.embedder.embed_queries(KNOWLEDGE_EXEMPLARS)
        if self._chat_anchor_vecs is None:
            self._chat_anchor_vecs = self.embedder.embed_queries(CHAT_EXEMPLARS)

    def classify(self, query: str) -> IntentClassification:
        """
        Classifies an input query into either 'chat' or 'knowledge_query'.
        Guaranteed to default to 'chat' if no knowledge cues match.
        """
        clean_query = query.strip() if query else ""
        if not clean_query:
            return IntentClassification(
                intent="chat",
                score=1.0,
                method="default_chat",
                raw_query="",
            )

        # -----------------------------------------------------------------
        # Tier 1: Fast Regex Rules (< 0.2ms)
        # -----------------------------------------------------------------
        for pattern, rule_name in self._compiled_rules:
            if pattern.search(clean_query):
                logger.debug(f"IntentRouter: Matched Tier 1 rule '{rule_name}' for query.")
                return IntentClassification(
                    intent="knowledge_query",
                    score=0.95,
                    method="rule",
                    raw_query=clean_query,
                )

        # -----------------------------------------------------------------
        # Tier 2: Semantic Exemplar Cosine Similarity (< 12ms)
        # -----------------------------------------------------------------
        try:
            self._ensure_anchor_embeddings()
            query_vec = self.embedder.embed_query(clean_query)

            # Compute inner product with knowledge anchors and chat anchors
            # Because vectors are L2-normalized, inner product == cosine similarity.
            k_sims = np.dot(self._knowledge_anchor_vecs, query_vec)
            c_sims = np.dot(self._chat_anchor_vecs, query_vec)

            max_k_sim = float(np.max(k_sims)) if len(k_sims) > 0 else 0.0
            max_c_sim = float(np.max(c_sims)) if len(c_sims) > 0 else 0.0

            # If strongly similar to knowledge anchor and more similar than to chat
            if max_k_sim >= self.similarity_threshold and max_k_sim > max_c_sim:
                logger.debug(
                    f"IntentRouter: Matched Tier 2 embedding similarity "
                    f"(k_sim={max_k_sim:.3f}, c_sim={max_c_sim:.3f})."
                )
                return IntentClassification(
                    intent="knowledge_query",
                    score=round(max_k_sim, 4),
                    method="embedding_similarity",
                    raw_query=clean_query,
                )

            # Otherwise, closer to chat or below knowledge threshold
            return IntentClassification(
                intent="chat",
                score=round(max(max_c_sim, 1.0 - max_k_sim), 4),
                method="default_chat",
                raw_query=clean_query,
            )

        except Exception as e:
            logger.warning(f"Error in Tier 2 intent classification: {e}. Defaulting to chat.")
            return IntentClassification(
                intent="chat",
                score=1.0,
                method="default_chat",
                raw_query=clean_query,
            )
