"""
Embedding service using multilingual-e5-small (384-dimensional dense vectors).
Follows model card prefix conventions:
- "query: " for search queries and symmetric similarity matching.
- "passage: " for document chunks and passages.
Vectors are strictly L2-normalized.
"""

import hashlib
import logging
import re
from typing import List, Optional, Union
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384


class MultilingualE5Embeddings:
    """
    Multilingual E5 Small Embedding Model wrapper.
    Prefix conventions (intfloat/multilingual-e5-small):
      - Query prefix: "query: "
      - Passage prefix: "passage: "
    Output vectors are L2-normalized float32 arrays.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        mock: bool = False,
        device: str = "cpu",
    ):
        self.model_id = model_id
        self.dimension = EMBEDDING_DIMENSION
        self.mock = mock
        self.device = device
        self.model = None
        self.is_loaded = False
        self._load_model()

    def _load_model(self) -> None:
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
            logger.warning(
                f"SentenceTransformer not available or could not load model ('{e}'). "
                f"Using deterministic normalized embedding fallback."
            )
            self.model = None
            self.is_loaded = True

    @staticmethod
    def normalize_vector(vec: np.ndarray) -> np.ndarray:
        """Applies L2 normalization along the last axis."""
        if vec.ndim == 1:
            norm = np.linalg.norm(vec)
            return (vec / norm) if norm > 1e-12 else vec
        norm = np.linalg.norm(vec, axis=-1, keepdims=True)
        return np.where(norm > 1e-12, vec / norm, vec)

    def _deterministic_mock_embedding(self, text: str) -> np.ndarray:
        """
        Produces a normalized 384-dimensional embedding using deterministic token hashing.
        Used when running offline or in unit tests where full PyTorch/HF model weights
        are not loaded.
        """
        stopwords = {
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
            "is", "are", "was", "were", "be", "been", "this", "that", "it",
            "what", "how", "who", "when", "where", "which", "query", "passage",
            "according", "tell", "me", "about", "please", "can", "you",
            "hai", "kya", "mein", "ko", "se", "aur", "ke", "ka", "ki"
        }
        vec = np.zeros(self.dimension, dtype=np.float32)
        tokens = re.findall(r"[\w\u0900-\u097F]+", text.lower())
        meaningful_tokens = [t for t in tokens if t not in stopwords and len(t) >= 2]

        if not meaningful_tokens:
            vec[0] = 1.0
            return vec

        for idx, token in enumerate(meaningful_tokens):
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimension
            # Weigh earlier terms slightly higher
            weight = 1.0 / (1.0 + 0.05 * idx)
            vec[h] += weight

        return self.normalize_vector(vec)

    def embed_passages(self, passages: List[str]) -> np.ndarray:
        """
        Embeds a list of document passages with the mandatory 'passage: ' prefix.
        Returns:
            np.ndarray of shape (len(passages), 384), dtype float32, L2-normalized.
        """
        if not passages:
            return np.empty((0, self.dimension), dtype=np.float32)

        prefixed = [f"passage: {p.strip()}" for p in passages]

        if self.model is not None and not self.mock:
            try:
                embeddings = self.model.encode(
                    prefixed,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return np.array(embeddings, dtype=np.float32)
            except Exception as e:
                logger.error(f"Inference error with SentenceTransformer: {e}. Falling back.")

        vectors = [self._deterministic_mock_embedding(text) for text in prefixed]
        return np.vstack(vectors).astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embeds a single search query with the mandatory 'query: ' prefix.
        Returns:
            np.ndarray of shape (384,), dtype float32, L2-normalized.
        """
        prefixed = f"query: {query.strip()}"

        if self.model is not None and not self.mock:
            try:
                embedding = self.model.encode(
                    prefixed,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return np.array(embedding, dtype=np.float32)
            except Exception as e:
                logger.error(f"Inference error with SentenceTransformer: {e}. Falling back.")

        return self._deterministic_mock_embedding(prefixed).astype(np.float32)

    def embed_queries(self, queries: List[str]) -> np.ndarray:
        """
        Embeds multiple queries (or symmetric similarity texts) with 'query: ' prefix.
        Returns:
            np.ndarray of shape (len(queries), 384), dtype float32, L2-normalized.
        """
        if not queries:
            return np.empty((0, self.dimension), dtype=np.float32)

        prefixed = [f"query: {q.strip()}" for q in queries]

        if self.model is not None and not self.mock:
            try:
                embeddings = self.model.encode(
                    prefixed,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return np.array(embeddings, dtype=np.float32)
            except Exception as e:
                logger.error(f"Inference error with SentenceTransformer: {e}. Falling back.")

        vectors = [self._deterministic_mock_embedding(text) for text in prefixed]
        return np.vstack(vectors).astype(np.float32)
