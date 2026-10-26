"""
FAISS inner-product vector store with strict configuration and metadata validation.
Stores index.faiss, chunks.json, and index_metadata.json.
Raises IndexConfigMismatchError when loaded index does not match the active configuration.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import faiss
    FAISS_AVAILABLE = True
except (ImportError, Exception):
    faiss = None
    FAISS_AVAILABLE = False
    logger.warning("faiss package not available or blocked by system policy. Using NumpyVectorIndex fallback.")

import numpy as np

logger = logging.getLogger(__name__)


class IndexConfigMismatchError(Exception):
    """Raised when index metadata does not match active system configuration."""
    pass


class NumpyVectorIndex:
    """
    Lightweight pure-numpy vector index fallback for environments where native C++ faiss
    is blocked by Windows App Control or unavailable.
    Performs inner product on L2-normalized float32 vectors, mathematically identical
    to faiss.IndexFlatIP.
    """
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.vectors = np.empty((0, dimension), dtype=np.float32)

    def add(self, vectors: np.ndarray) -> None:
        if vectors.shape[0] == 0:
            return
        vecs_f32 = np.ascontiguousarray(vectors, dtype=np.float32)
        if self.vectors.shape[0] == 0:
            self.vectors = vecs_f32
        else:
            self.vectors = np.vstack([self.vectors, vecs_f32])

    def search(self, query_vec: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        if self.vectors.shape[0] == 0:
            return np.empty((1, 0), dtype=np.float32), np.empty((1, 0), dtype=np.int64)
        q = np.ascontiguousarray(query_vec.reshape(1, -1), dtype=np.float32)
        # Inner product on normalized vectors equals cosine similarity
        scores = np.dot(self.vectors, q.T).flatten()
        top_k = min(k, len(scores))
        indices = np.argsort(scores)[::-1][:top_k]
        distances = scores[indices]
        return np.expand_dims(distances, axis=0), np.expand_dims(indices, axis=0)

    @property
    def ntotal(self) -> int:
        return self.vectors.shape[0]


@dataclass
class IndexMetadata:
    model_name: str
    dimension: int
    chunk_size: int
    chunk_overlap: int
    doc_hashes: Dict[str, str]
    total_chunks: int
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexMetadata":
        return cls(
            model_name=data.get("model_name", ""),
            dimension=int(data.get("dimension", 384)),
            chunk_size=int(data.get("chunk_size", 500)),
            chunk_overlap=int(data.get("chunk_overlap", 100)),
            doc_hashes=data.get("doc_hashes", {}),
            total_chunks=int(data.get("total_chunks", 0)),
            created_at=data.get("created_at", ""),
        )


class FAISSVectorStore:
    """
    Manages FAISS inner-product index and chunk persistence with metadata integrity.
    """

    INDEX_FILENAME = "index.faiss"
    CHUNKS_FILENAME = "chunks.json"
    METADATA_FILENAME = "index_metadata.json"

    def __init__(
        self,
        dimension: int = 384,
        model_name: str = "intfloat/multilingual-e5-small",
        index_dir: Optional[str] = None,
    ):
        self.dimension = dimension
        self.model_name = model_name
        self.index_dir = Path(index_dir) if index_dir else None

        self.index: Any = None
        self._vectors: Optional[np.ndarray] = None
        self.chunks: List[Dict[str, Any]] = []
        self.metadata: Optional[IndexMetadata] = None
        self.is_loaded: bool = False

    def build(
        self,
        embeddings: np.ndarray,
        chunks: List[Dict[str, Any]],
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        doc_hashes: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Builds a new FAISS IndexFlatIP (or NumpyVectorIndex fallback) from embeddings and chunk metadata.
        """
        if embeddings.shape[0] != len(chunks):
            raise ValueError(
                f"Embedding count ({embeddings.shape[0]}) does not match chunk count ({len(chunks)})."
            )
        if embeddings.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding dimension ({embeddings.shape[1]}) does not match expected ({self.dimension})."
            )

        emb_f32 = np.ascontiguousarray(embeddings, dtype=np.float32)
        self._vectors = emb_f32

        # IndexFlatIP calculates inner product. Because embeddings are L2-normalized,
        # inner product equals exact cosine similarity.
        if FAISS_AVAILABLE and faiss is not None:
            self.index = faiss.IndexFlatIP(self.dimension)
            if emb_f32.shape[0] > 0:
                self.index.add(emb_f32)
        else:
            self.index = NumpyVectorIndex(self.dimension)
            if emb_f32.shape[0] > 0:
                self.index.add(emb_f32)

        self.chunks = chunks
        self.metadata = IndexMetadata(
            model_name=self.model_name,
            dimension=self.dimension,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            doc_hashes=doc_hashes or {},
            total_chunks=len(chunks),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.is_loaded = True
        logger.info(
            f"Built vector index with {len(chunks)} chunks (dimension: {self.dimension}, "
            f"model: {self.model_name}, backend={'faiss' if FAISS_AVAILABLE else 'numpy'})."
        )

    def save(self, target_dir: Optional[str] = None) -> None:
        """
        Saves the vector index, chunk data, and metadata JSON to disk.
        """
        out_dir = Path(target_dir) if target_dir else self.index_dir
        if not out_dir:
            raise ValueError("No directory specified to save FAISS index.")

        out_dir.mkdir(parents=True, exist_ok=True)

        if self.index is None or self.metadata is None:
            raise ValueError("Cannot save an uninitialized or empty FAISS vector store.")

        index_path = out_dir / self.INDEX_FILENAME
        npy_path = out_dir / "vectors.npy"

        # 1. Save binary index (or numpy fallback)
        if FAISS_AVAILABLE and faiss is not None and hasattr(faiss, "write_index") and not isinstance(self.index, NumpyVectorIndex):
            faiss.write_index(self.index, str(index_path))
            if self._vectors is not None:
                np.save(str(npy_path), self._vectors)
        else:
            vecs = getattr(self.index, "vectors", None)
            if vecs is None and self._vectors is not None:
                vecs = self._vectors
            if vecs is None:
                vecs = np.empty((0, self.dimension), dtype=np.float32)
            # Save both as index.faiss (numpy binary) and vectors.npy for cross-platform portability
            np.save(str(index_path), vecs)
            np.save(str(npy_path), vecs)

        # 2. Save Chunks JSON
        chunks_path = out_dir / self.CHUNKS_FILENAME
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=2)

        # 3. Save Metadata JSON
        meta_path = out_dir / self.METADATA_FILENAME
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata.to_dict(), f, indent=2)

        logger.info(f"Saved vector index, chunks, and metadata to '{out_dir}'.")

    def load(self, source_dir: Optional[str] = None) -> None:
        """
        Loads the vector index and verifies config metadata.
        Refuses to load if model_name or dimension do not match active config.
        """
        load_dir = Path(source_dir) if source_dir else self.index_dir
        if not load_dir or not load_dir.is_dir():
            raise FileNotFoundError(f"Vector store directory '{load_dir}' does not exist.")

        index_path = load_dir / self.INDEX_FILENAME
        npy_path = load_dir / "vectors.npy"
        chunks_path = load_dir / self.CHUNKS_FILENAME
        meta_path = load_dir / self.METADATA_FILENAME

        if (not index_path.exists() and not npy_path.exists()) or not chunks_path.exists() or not meta_path.exists():
            raise FileNotFoundError(
                f"Vector store files incomplete in '{load_dir}'. Expected {self.INDEX_FILENAME}, "
                f"{self.CHUNKS_FILENAME}, and {self.METADATA_FILENAME}."
            )

        # 1. Load and validate metadata FIRST
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
        loaded_meta = IndexMetadata.from_dict(meta_data)

        if loaded_meta.model_name != self.model_name:
            raise IndexConfigMismatchError(
                f"Index model mismatch: index was built with '{loaded_meta.model_name}', "
                f"but active configuration requires '{self.model_name}'."
            )

        if loaded_meta.dimension != self.dimension:
            raise IndexConfigMismatchError(
                f"Index dimension mismatch: index dimension is {loaded_meta.dimension}, "
                f"but active configuration requires dimension {self.dimension}."
            )

        # 2. Load vector index
        if FAISS_AVAILABLE and faiss is not None:
            try:
                self.index = faiss.read_index(str(index_path))
            except Exception:
                target_file = npy_path if npy_path.exists() else index_path
                vecs = np.load(str(target_file))
                self.index = faiss.IndexFlatIP(self.dimension)
                if vecs.shape[0] > 0:
                    self.index.add(np.ascontiguousarray(vecs, dtype=np.float32))
        else:
            target_file = npy_path if npy_path.exists() else index_path
            try:
                vecs = np.load(str(target_file))
                self.index = NumpyVectorIndex(self.dimension)
                if vecs.shape[0] > 0:
                    self.index.add(vecs)
            except Exception as e:
                raise RuntimeError(f"Cannot load vector index fallback: {e}")

        # 3. Load chunks
        with open(chunks_path, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

        self.metadata = loaded_meta
        self.index_dir = load_dir
        self.is_loaded = True

        logger.info(
            f"Successfully loaded FAISS index from '{load_dir}' with {len(self.chunks)} chunks. "
            f"Config validated: model={self.model_name}, dim={self.dimension}."
        )

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 3,
        threshold: float = 0.0,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Executes inner product search. Returns list of (chunk_dict, score) passing threshold.
        """
        if not self.is_loaded or self.index is None or len(self.chunks) == 0:
            return []

        # Ensure correct shape (1, dimension)
        if query_vec.ndim == 1:
            query_vec = np.expand_dims(query_vec, axis=0)

        query_vec_f32 = np.ascontiguousarray(query_vec, dtype=np.float32)
        k = min(top_k, len(self.chunks))
        if k <= 0:
            return []

        scores, indices = self.index.search(query_vec_f32, k)

        results: List[Tuple[Dict[str, Any], float]] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            float_score = float(score)
            if float_score >= threshold:
                results.append((self.chunks[idx], float_score))

        return results
