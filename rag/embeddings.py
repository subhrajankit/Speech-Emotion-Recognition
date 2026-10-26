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
        device: str = "cpu",
    ):
        self.model_id = model_id
        self.dimension = EMBEDDING_DIMENSION
        self.device = device
        self.model = None
        self.is_loaded = False
        self._load_model()

    def _load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model '{self.model_id}' on {self.device}...")
            self.model = SentenceTransformer(self.model_id, device=self.device)
            self.is_loaded = True
            logger.info("MultilingualE5Embeddings loaded successfully.")
        except Exception as e:
            self.model = None
            self.is_loaded = False
            raise RuntimeError(
                f"Failed to load embedding model '{self.model_id}' on {self.device} ({e}). "
                "Ensure sentence-transformers is installed and model weights are accessible."
            ) from e

    @staticmethod
    def normalize_vector(vec: np.ndarray) -> np.ndarray:
        """Applies L2 normalization along the last axis."""
        if vec.ndim == 1:
            norm = np.linalg.norm(vec)
            return (vec / norm) if norm > 1e-12 else vec
        norm = np.linalg.norm(vec, axis=-1, keepdims=True)
        return np.where(norm > 1e-12, vec / norm, vec)

    def embed_passages(self, passages: List[str]) -> np.ndarray:
        """
        Embeds a list of document passages with the mandatory 'passage: ' prefix.
        Returns:
            np.ndarray of shape (len(passages), 384), dtype float32, L2-normalized.
        """
        if not passages:
            return np.empty((0, self.dimension), dtype=np.float32)

        if not self.is_loaded or self.model is None:
            raise RuntimeError("MultilingualE5Embeddings is not loaded.")

        prefixed = [f"passage: {p.strip()}" for p in passages]
        embeddings = self.model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.array(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embeds a single search query with the mandatory 'query: ' prefix.
        Returns:
            np.ndarray of shape (384,), dtype float32, L2-normalized.
        """
        if not self.is_loaded or self.model is None:
            raise RuntimeError("MultilingualE5Embeddings is not loaded.")

        prefixed = f"query: {query.strip()}"
        embedding = self.model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.array(embedding, dtype=np.float32)

    def embed_queries(self, queries: List[str]) -> np.ndarray:
        """
        Embeds multiple queries (or symmetric similarity texts) with 'query: ' prefix.
        Returns:
            np.ndarray of shape (len(queries), 384), dtype float32, L2-normalized.
        """
        if not queries:
            return np.empty((0, self.dimension), dtype=np.float32)

        if not self.is_loaded or self.model is None:
            raise RuntimeError("MultilingualE5Embeddings is not loaded.")

        prefixed = [f"query: {q.strip()}" for q in queries]
        embeddings = self.model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.array(embeddings, dtype=np.float32)
