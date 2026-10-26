"""
RAG Service for VoiceSense AI backend runtime.
Encapsulates embedding model, FAISS vector store, retriever, and intent router.
Executes compute-intensive vector operations off the asyncio event loop using threadpool.
"""

import asyncio
from dataclasses import dataclass, asdict
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rag.embeddings import MultilingualE5Embeddings, DEFAULT_MODEL_ID, EMBEDDING_DIMENSION
from rag.vectorstore import FAISSVectorStore, IndexConfigMismatchError
from rag.retriever import RAGRetriever, RetrievedChunk
from rag.intent_router import IntentRouter, IntentClassification

logger = logging.getLogger(__name__)


@dataclass
class RAGTurnResult:
    intent: IntentClassification
    chunks: List[RetrievedChunk]
    grounded_context: str
    cited_docs: List[Dict[str, Any]]
    retrieval_performed: bool


class RAGService:
    """
    Singleton service managing Intent Gating and Knowledge Retrieval.
    Ensures that non-knowledge (chat) turns NEVER execute vector searches.
    """

    def __init__(
        self,
        index_dir: str = "rag/vectorstore",
        model_id: str = DEFAULT_MODEL_ID,
        similarity_threshold: float = 0.70,
    ):
        self.index_dir = Path(index_dir)
        self.model_id = model_id
        self.similarity_threshold = similarity_threshold

        self.embedder: Optional[MultilingualE5Embeddings] = None
        self.vectorstore: Optional[FAISSVectorStore] = None
        self.retriever: Optional[RAGRetriever] = None
        self.intent_router: Optional[IntentRouter] = None
        self.is_initialized: bool = False

    def initialize(self) -> None:
        """
        Loads models and vector index at application startup.
        Safe initialization: does not crash if vector store is not yet built.
        """
        logger.info("Initializing RAGService...")
        self.embedder = MultilingualE5Embeddings(
            model_id=self.model_id,
        )

        self.vectorstore = FAISSVectorStore(
            dimension=EMBEDDING_DIMENSION,
            model_name=self.model_id,
            index_dir=str(self.index_dir),
        )

        if self.index_dir.is_dir() and (self.index_dir / FAISSVectorStore.INDEX_FILENAME).exists():
            try:
                self.vectorstore.load(str(self.index_dir))
                logger.info(
                    f"RAGService: Successfully loaded index from '{self.index_dir}' "
                    f"({len(self.vectorstore.chunks)} chunks)."
                )
            except IndexConfigMismatchError as e:
                logger.error(f"RAGService: Config mismatch loading index: {e}")
            except Exception as e:
                logger.error(f"RAGService: Failed to load index from '{self.index_dir}': {e}")
        else:
            logger.info(
                f"RAGService: Vector store directory '{self.index_dir}' does not contain an index. "
                f"RAG will operate in idle mode until documents are ingested."
            )

        self.retriever = RAGRetriever(
            vectorstore=self.vectorstore,
            embedder=self.embedder,
            top_k=3,
            similarity_threshold=self.similarity_threshold,
        )

        self.intent_router = IntentRouter(
            embedder=self.embedder,
            similarity_threshold=0.80,
        )

        self.is_initialized = True
        logger.info("RAGService initialization complete.")

    def classify_intent(self, query: str) -> IntentClassification:
        """
        Evaluates input query against the Intent Gate.
        """
        if not self.intent_router:
            return IntentClassification(
                intent="chat",
                score=1.0,
                method="default_chat",
                raw_query=query,
            )
        return self.intent_router.classify(query)

    async def process_turn(
        self,
        transcript: str,
        top_k: int = 3,
        threshold: Optional[float] = None,
    ) -> RAGTurnResult:
        """
        Hard Gate Pipeline:
        1. Classify intent.
        2. If 'chat': return immediately with ZERO vector search.
        3. If 'knowledge_query': run retriever off event loop via threadpool.
           If retrieval finds chunks above threshold, format grounded context.
           If retrieval yields nothing or fails, fall back to plain chat cleanly.
        """
        intent = self.classify_intent(transcript)

        # Invariant check: Chat queries NEVER touch FAISS
        if intent.intent != "knowledge_query":
            return RAGTurnResult(
                intent=intent,
                chunks=[],
                grounded_context="",
                cited_docs=[],
                retrieval_performed=False,
            )

        # Knowledge query: execute retrieval in worker thread
        if not self.retriever or not self.retriever.is_ready:
            logger.info("Knowledge query detected, but RAG index is not loaded. Falling back to chat.")
            return RAGTurnResult(
                intent=intent,
                chunks=[],
                grounded_context="",
                cited_docs=[],
                retrieval_performed=False,
            )

        chunks = await asyncio.to_thread(
            self.retriever.retrieve,
            transcript,
            top_k=top_k,
            threshold=threshold,
        )

        grounded_context, cited_docs = self.retriever.format_grounded_context(chunks)

        return RAGTurnResult(
            intent=intent,
            chunks=chunks,
            grounded_context=grounded_context,
            cited_docs=cited_docs,
            retrieval_performed=True,
        )

    def get_health_status(self) -> Dict[str, Any]:
        """Returns health telemetry for /api/health."""
        index_loaded = bool(self.vectorstore and self.vectorstore.is_loaded)
        total_chunks = len(self.vectorstore.chunks) if index_loaded else 0

        if not self.is_initialized:
            status = "unavailable"
        elif index_loaded and total_chunks > 0:
            status = "ok"
        else:
            status = "no_index"

        return {
            "status": status,
            "index_loaded": index_loaded,
            "total_chunks": total_chunks,
            "model_name": self.model_id,
            "dimension": EMBEDDING_DIMENSION,
        }


# Global singleton instance
rag_service = RAGService()
