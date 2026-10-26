"""
RAG (Retrieval-Augmented Generation) package for VoiceSense AI.
Provides document chunking, multilingual-e5-small embeddings,
FAISS inner-product vector store, retrieval with thresholding,
and intent gating.
"""

__all__ = [
    "MultilingualE5Embeddings",
    "FAISSVectorStore",
    "IndexConfigMismatchError",
    "DocumentChunker",
    "RAGRetriever",
    "IntentRouter",
    "IntentClassification",
]
