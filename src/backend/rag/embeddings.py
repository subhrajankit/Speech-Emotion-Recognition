"""
Embedding service using multilingual-e5-small (384-dimensional dense vectors).
Loaded once at application startup. Supports passage and query formatting.
"""
import logging
import re
import numpy as np
from typing import List, Union

logger = logging.getLogger(__name__)

class MultilingualE5Embeddings:
    """
    Multilingual E5 Small Embedding Model wrapper.
    E5 requires 'query: ' and 'passage: ' prefixes for asymmetric semantic search.
    Vector dimension: 384.
    """
    def __init__(self, model_id: str = "intfloat/multilingual-e5-small", mock: bool = False, device: str = "cpu"):
        self.model_id = model_id
        self.dimension = 384
        self.mock = mock
        self.device = device
        self.model = None
        self.is_loaded = False
        self._load_model()

    def _load_model(self):
        if self.mock:
            logger.info("Initializing MultilingualE5Embeddings in MOCK mode.")
            self.is_loaded = True
            return

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model '{self.model_id}' on {self.device}...")
            self.model = SentenceTransformer(self.model_id, device=self.device)
            self.is_loaded = True
            logger.info("MultilingualE5Embeddings loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer ('{e}'). Falling back to deterministic embedding mode.")
            self.model = None
            self.is_loaded = True

    def _deterministic_mock_embedding(self, text: str) -> np.ndarray:
        """
        Produces a normalized 384-dimensional embedding using deterministic token hashing.
        Filters stopwords to prioritize meaningful semantic keywords across queries and passages.
        """
        import hashlib
        stopwords = {
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
            "is", "are", "was", "were", "be", "been", "this", "that", "it",
            "what", "how", "who", "when", "where", "which", "query", "passage",
            "according", "tell", "me", "about", "please", "can", "you"
        }
        vec = np.zeros(self.dimension, dtype=np.float32)
        tokens = re.findall(r'[a-zA-Z0-9\u0900-\u097F]+', text.lower())
        meaningful_tokens = [t for t in tokens if t not in stopwords and len(t) >= 2]

        if not meaningful_tokens:
            vec[0] = 1.0
            return vec

        for token in meaningful_tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimension
            vec[h] += 1.0

        norm = np.linalg.norm(vec)
        return (vec / norm) if norm > 0 else vec


    def embed_passages(self, passages: List[str]) -> np.ndarray:
        """
        Embeds a list of document passages using 'passage: ' prefix.
        Returns float32 numpy array of shape (len(passages), 384).
        """
        if not passages:
            return np.empty((0, self.dimension), dtype=np.float32)

        prefixed = [f"passage: {p.strip()}" for p in passages]

        if self.model is not None and not self.mock:
            try:
                embeddings = self.model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
                return np.array(embeddings, dtype=np.float32)
            except Exception as e:
                logger.error(f"Error generating embeddings via model: {e}")

        # Deterministic fallback / mock embedding
        vectors = [self._deterministic_mock_embedding(text) for text in prefixed]
        return np.vstack(vectors)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embeds a single search query using 'query: ' prefix.
        Returns normalized float32 numpy array of shape (384,).
        """
        prefixed = f"query: {query.strip()}"

        if self.model is not None and not self.mock:
            try:
                embedding = self.model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
                return np.array(embedding, dtype=np.float32)
            except Exception as e:
                logger.error(f"Error generating query embedding via model: {e}")

        return self._deterministic_mock_embedding(prefixed)
