"""
Retriever component for VoiceSense AI RAG.
Executes top-k inner product search over FAISS index with score thresholding.
Enforces invariant: Never fabricate citations; return clean source references.
"""

from dataclasses import dataclass, asdict
import logging
from typing import Any, Dict, List, Optional, Tuple

from rag.embeddings import MultilingualE5Embeddings
from rag.vectorstore import FAISSVectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_name: str
    text: str
    score: float
    chunk_index: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RAGRetriever:
    """
    Coordinates query embedding and vector search over FAISSVectorStore.
    Filters by similarity threshold and formats grounded context for downstream LLM.
    """

    def __init__(
        self,
        vectorstore: Optional[FAISSVectorStore] = None,
        embedder: Optional[MultilingualE5Embeddings] = None,
        top_k: int = 3,
        similarity_threshold: float = 0.70,
    ):
        self.vectorstore = vectorstore
        self.embedder = embedder or MultilingualE5Embeddings()
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

    @property
    def is_ready(self) -> bool:
        return bool(self.vectorstore is not None and self.vectorstore.is_loaded)

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[RetrievedChunk]:
        """
        Embeds query with 'query: ' prefix and searches vector store.
        Returns only chunks that meet or exceed the similarity threshold.
        """
        clean_query = query.strip() if query else ""
        if not clean_query:
            return []

        if not self.is_ready:
            logger.debug("RAGRetriever: Vector store not loaded. Returning empty retrieval.")
            return []

        k = top_k if top_k is not None else self.top_k
        thresh = threshold if threshold is not None else self.similarity_threshold

        try:
            query_vec = self.embedder.embed_query(clean_query)
            raw_results = self.vectorstore.search(query_vec, top_k=k, threshold=thresh)

            retrieved: List[RetrievedChunk] = []
            for chunk_data, score in raw_results:
                retrieved.append(
                    RetrievedChunk(
                        chunk_id=chunk_data.get("chunk_id", ""),
                        doc_name=chunk_data.get("doc_name", "unknown_doc"),
                        text=chunk_data.get("text", ""),
                        score=round(score, 4),
                        chunk_index=int(chunk_data.get("chunk_index", 0)),
                    )
                )

            logger.info(
                f"RAG search for '{clean_query[:50]}...': {len(retrieved)} chunk(s) passed "
                f"threshold {thresh} (top_k={k})."
            )
            return retrieved

        except Exception as e:
            logger.error(f"Error during RAG retrieval: {e}. Gracefully returning empty context.")
            return []

    @staticmethod
    def format_grounded_context(
        chunks: List[RetrievedChunk],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Formats retrieved chunks into grounded text and extracts citation references.
        Returns:
            grounded_context_str: str, formatted document excerpt block.
            cited_docs: list of dicts with doc_name, chunk_id, score for UI.
        """
        if not chunks:
            return "", []

        context_lines: List[str] = [
            "--- GROUNDED KNOWLEDGE BASE EXCERPTS (Use these to answer) ---"
        ]
        cited_docs: List[Dict[str, Any]] = []
        seen_docs = set()

        for idx, chunk in enumerate(chunks, 1):
            context_lines.append(f"[Document {idx}: {chunk.doc_name} (Score: {chunk.score})]")
            context_lines.append(chunk.text)
            context_lines.append("")

            cited_docs.append({
                "doc_name": chunk.doc_name,
                "chunk_id": chunk.chunk_id,
                "score": chunk.score,
            })
            seen_docs.add(chunk.doc_name)

        context_lines.append("--- END EXCERPTS ---")
        return "\n".join(context_lines), cited_docs
