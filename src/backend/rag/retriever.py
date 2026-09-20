"""
RAG Retriever service.
Performs top-k dense vector retrieval and prepares grounded context with document citations.
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from .embeddings import MultilingualE5Embeddings
from .index import load_faiss_index, build_faiss_index

logger = logging.getLogger(__name__)

class RAGRetriever:
    """
    RAG Retriever querying FAISS index via multilingual-e5-small embeddings.
    Only invoked when intent category is 'knowledge'.
    """
    def __init__(
        self,
        embeddings: Optional[MultilingualE5Embeddings] = None,
        index_dir: str = "data/index",
        mock: bool = False
    ):
        self.embeddings = embeddings or MultilingualE5Embeddings(mock=mock)
        self.index_dir = index_dir
        self.index = None
        self.chunks: List[Dict[str, Any]] = []
        self.is_loaded = False
        self.reload_index()

    def reload_index(self):
        """Loads or reloads the FAISS index and chunk metadata from disk."""
        self.index, self.chunks = load_faiss_index(self.index_dir)
        self.is_loaded = self.index is not None and len(self.chunks) > 0
        logger.info(f"RAGRetriever initialized (loaded={self.is_loaded}, chunks={len(self.chunks)}).")

    def retrieve(self, query: str, top_k: int = 3, min_score: float = 0.25) -> List[Dict[str, Any]]:
        """
        Retrieves top-k relevant document chunks for the query.
        Each result item contains { doc_name, text, score, chunk_id, source_file }.
        """
        if not query or not query.strip():
            return []

        if not self.is_loaded or self.index is None or len(self.chunks) == 0:
            logger.warning("RAGRetriever: No index or chunks loaded.")
            return []

        query_vec = self.embeddings.embed_query(query)
        query_vec = np.expand_dims(query_vec, axis=0)

        # FAISS search
        distances, indices = self.index.search(query_vec, min(top_k, len(self.chunks)))

        results = []
        if distances.shape[1] > 0:
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self.chunks):
                    continue
                score = float(dist)
                if score >= min_score or len(results) == 0:  # Always include top result if above zero
                    chunk_meta = dict(self.chunks[idx])
                    chunk_meta["score"] = round(score, 4)
                    results.append(chunk_meta)

        return results

    def format_grounded_context(self, retrieved_chunks: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
        """
        Constructs context text and list of unique cited documents.
        Returns (context_str, doc_citations).
        """
        if not retrieved_chunks:
            return "", []

        cited_docs = []
        context_parts = []

        for i, chunk in enumerate(retrieved_chunks, 1):
            doc = chunk.get("doc_name", "document")
            if doc not in cited_docs:
                cited_docs.append(doc)
            text = chunk.get("text", "").strip()
            context_parts.append(f"[Document: {doc} | Section: {chunk.get('chunk_id', i)}]\n{text}")

        context_str = "\n\n".join(context_parts)
        return context_str, cited_docs

    def build_in_memory_index(self, chunks: List[Dict[str, Any]]):
        """Allows test fixtures to build a temporary in-memory index."""
        self.chunks = chunks
        texts = [c["text"] for c in chunks]
        embeddings = self.embeddings.embed_passages(texts)
        self.index, _ = build_faiss_index(embeddings, chunks, output_dir=None)
        self.is_loaded = True
