"""
FAISS vector index management for document chunks.
Builds and loads dense vector indices with serialized chunk metadata.
"""
import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    faiss = None
    FAISS_AVAILABLE = False
    logger.warning("faiss package not found. Using NumpyIndex fallback.")

class NumpyVectorIndex:
    """Lightweight pure-numpy vector index fallback for environments without faiss."""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.vectors = np.empty((0, dimension), dtype=np.float32)

    def add(self, vectors: np.ndarray):
        if self.vectors.shape[0] == 0:
            self.vectors = vectors.astype(np.float32)
        else:
            self.vectors = np.vstack([self.vectors, vectors.astype(np.float32)])

    def search(self, query_vec: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        if self.vectors.shape[0] == 0:
            return np.empty((1, 0), dtype=np.float32), np.empty((1, 0), dtype=np.int64)

        # Dot product / cosine similarity on normalized vectors
        scores = np.dot(self.vectors, query_vec.T).flatten()
        top_k = min(k, len(scores))
        indices = np.argsort(scores)[::-1][:top_k]
        distances = scores[indices]
        return np.expand_dims(distances, axis=0), np.expand_dims(indices, axis=0)

    def ntotal(self) -> int:
        return self.vectors.shape[0]


def build_faiss_index(
    embeddings: np.ndarray,
    chunks: List[Dict[str, Any]],
    output_dir: Optional[str] = "data/index"
) -> Tuple[Any, List[Dict[str, Any]]]:
    """
    Builds an Inner Product (cosine similarity on normalized vectors) FAISS index.
    Saves index to output_dir/rag.index and chunks to output_dir/chunks.json if output_dir given.
    """
    dimension = embeddings.shape[1] if embeddings.shape[0] > 0 else 384

    if FAISS_AVAILABLE:
        index = faiss.IndexFlatIP(dimension)
        if embeddings.shape[0] > 0:
            index.add(embeddings.astype(np.float32))
    else:
        index = NumpyVectorIndex(dimension)
        if embeddings.shape[0] > 0:
            index.add(embeddings)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        index_path = os.path.join(output_dir, "rag.index")
        chunks_path = os.path.join(output_dir, "chunks.json")

        if FAISS_AVAILABLE and isinstance(index, faiss.Index):
            faiss.write_index(index, index_path)
        else:
            np.save(index_path + ".npy", embeddings)

        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully saved vector index with {len(chunks)} chunks to '{output_dir}'.")

    return index, chunks


def load_faiss_index(
    index_dir: str = "data/index"
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    """
    Loads FAISS index and metadata chunks from disk.
    Returns (index, chunks). If index does not exist, returns (None, []).
    """
    index_path = os.path.join(index_dir, "rag.index")
    chunks_path = os.path.join(index_dir, "chunks.json")

    if not os.path.exists(chunks_path):
        logger.info(f"No existing chunks metadata found at '{chunks_path}'.")
        return None, []

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    if FAISS_AVAILABLE and os.path.exists(index_path):
        try:
            index = faiss.read_index(index_path)
            logger.info(f"Loaded FAISS index with {index.ntotal} vectors from '{index_path}'.")
            return index, chunks
        except Exception as e:
            logger.error(f"Error reading FAISS index: {e}")

    npy_path = index_path + ".npy"
    if os.path.exists(npy_path):
        vecs = np.load(npy_path)
        index = NumpyVectorIndex(vecs.shape[1])
        index.add(vecs)
        logger.info(f"Loaded Numpy vector index with {index.ntotal()} vectors from '{npy_path}'.")
        return index, chunks

    return None, chunks
