"""
Ingestion CLI module for VoiceSense AI.
Usage:
    python -m rag.ingestion --docs rag/documents --index-dir rag/vectorstore

Builds a FAISS inner-product index and persists chunks + index metadata.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Any

from rag.chunking import DocumentChunker
from rag.embeddings import MultilingualE5Embeddings, DEFAULT_MODEL_ID, EMBEDDING_DIMENSION
from rag.vectorstore import FAISSVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rag.ingestion")


def run_ingestion(
    docs_dir: str = "data/documents",
    index_dir: str = "data/index",
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    model_id: str = DEFAULT_MODEL_ID,
    embedder: Optional[Any] = None,
) -> int:
    """
    Executes end-to-end ingestion pipeline:
    1. Parse docs from docs_dir.
    2. Compute SHA-256 hashes and split into overlapping chunks.
    3. Generate multilingual-e5-small normalized embeddings (with "passage: " prefix).
    4. Build and save FAISS IndexFlatIP index and metadata JSON.
    Returns:
        total_chunks (int)
    """
    start_time = time.perf_counter()
    docs_path = Path(docs_dir)
    index_path = Path(index_dir)

    logger.info(f"=== Starting RAG Document Ingestion ===")
    logger.info(f"Documents directory: '{docs_path.resolve()}'")
    logger.info(f"Target index directory: '{index_path.resolve()}'")
    logger.info(f"Chunk parameters: size={chunk_size}, overlap={chunk_overlap}")
    logger.info(f"Embedding model: '{model_id}' (dim={EMBEDDING_DIMENSION})")

    if not docs_path.exists() or not docs_path.is_dir():
        logger.error(f"Documents directory '{docs_path}' does not exist.")
        return 0

    # 1. Chunk documents
    chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks, doc_hashes = chunker.process_directory(docs_path)

    if not chunks:
        logger.warning(
            f"No parseable documents found in '{docs_path}'. "
            f"Supported extensions: .md, .txt, .pdf, .docx. Index was not built."
        )
        return 0

    doc_count = len(doc_hashes)
    chunk_count = len(chunks)
    logger.info(f"Chunking complete: {chunk_count} chunks extracted across {doc_count} document(s).")

    # 2. Generate embeddings
    logger.info(f"Generating embeddings for {chunk_count} passages (prefix='passage: ')...")
    emb_start = time.perf_counter()
    if embedder is None:
        embedder = MultilingualE5Embeddings(model_id=model_id)
    passages = [c["text"] for c in chunks]
    embeddings = embedder.embed_passages(passages)
    emb_duration = time.perf_counter() - emb_start

    logger.info(
        f"Embeddings generated in {emb_duration:.3f}s "
        f"({(emb_duration / max(1, chunk_count)) * 1000:.1f}ms/chunk). "
        f"Shape: {embeddings.shape}"
    )

    # 3. Build & Save FAISS Vector Store
    vectorstore = FAISSVectorStore(
        dimension=EMBEDDING_DIMENSION,
        model_name=model_id,
        index_dir=str(index_path),
    )
    vectorstore.build(
        embeddings=embeddings,
        chunks=chunks,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        doc_hashes=doc_hashes,
    )
    vectorstore.save(str(index_path))

    total_duration = time.perf_counter() - start_time
    logger.info(f"=== Ingestion Finished Successfully ===")
    logger.info(f"Total time: {total_duration:.3f}s")
    logger.info(f"Total documents: {doc_count}")
    logger.info(f"Total chunks: {chunk_count}")
    logger.info(f"Index location: '{index_path.resolve()}'")

    return chunk_count


def main():
    parser = argparse.ArgumentParser(description="Ingest documents and build FAISS vector index.")
    parser.add_argument("--docs", default="data/documents", help="Path to input documents directory.")
    parser.add_argument("--index-dir", default="data/index", help="Path to output vectorstore directory.")
    parser.add_argument("--chunk-size", type=int, default=500, help="Max chunk size in characters.")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Overlap size in characters.")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Embedding model ID.")
    args = parser.parse_args()
    try:
        count = run_ingestion(
            docs_dir=args.docs,
            index_dir=args.index_dir,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            model_id=args.model_id,
        )
        if count == 0:
            sys.exit(1)
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
