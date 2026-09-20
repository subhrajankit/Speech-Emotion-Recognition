#!/usr/bin/env python3
"""
Standalone script to parse documents in data/documents/ and build a FAISS vector index.
Supports PDF, DOCX, TXT, and Markdown files.
Executed on-demand or during ingestion, NEVER per-request.
"""
import os
import sys
import argparse
import logging
from typing import List, Dict, Any, Optional

# Ensure project root is in pythonpath
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.backend.rag.embeddings import MultilingualE5Embeddings
from src.backend.rag.index import build_faiss_index
from src.backend.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_rag_index")

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_ALLOWED_FILE_SIZE_BYTES = settings.MAX_RAG_UPLOAD_SIZE_BYTES  # 10 MB default

def validate_document_file(file_path: str, allowed_base_dir: Optional[str] = None) -> bool:
    """
    Security validation for uploaded/ingested RAG documents (Phase 11):
    1. Prevents directory traversal (canonical path check against allowed_base_dir).
    2. Enforces allowed extension whitelist (.pdf, .docx, .txt, .md).
    3. Checks file size does not exceed MAX_ALLOWED_FILE_SIZE_BYTES.
    4. Validates magic bytes / MIME signatures to prevent file disguise attacks:
       - PDF: starts with b"%PDF"
       - DOCX: starts with b"PK\x03\x04" (ZIP archive container)
       - TXT/MD: valid UTF-8 without binary null bytes (\\x00)
    """
    # 1. Path traversal verification
    real_path = os.path.realpath(file_path)
    if allowed_base_dir:
        real_base = os.path.realpath(allowed_base_dir)
        if not real_path.startswith(real_base):
            logger.error(f"[SECURITY] Directory traversal attempt detected: '{file_path}' resolves outside '{allowed_base_dir}'.")
            return False

    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        logger.error(f"File does not exist or is not a regular file: '{file_path}'")
        return False

    # 2. Extension validation
    ext = os.path.splitext(real_path)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        logger.error(f"[SECURITY] Disallowed file extension '{ext}' for file '{file_path}'. Allowed: {ALLOWED_DOCUMENT_EXTENSIONS}")
        return False

    # 3. File size cap
    file_size = os.path.getsize(real_path)
    if file_size > MAX_ALLOWED_FILE_SIZE_BYTES:
        logger.error(f"[SECURITY] File size {file_size} exceeds quota {MAX_ALLOWED_FILE_SIZE_BYTES} bytes ({file_path}).")
        return False
    if file_size == 0:
        logger.warning(f"File '{file_path}' is empty (0 bytes).")
        return False

    # 4. Magic bytes & content safety checks
    try:
        with open(real_path, "rb") as f:
            header = f.read(1024)

        if ext == ".pdf":
            if not header.startswith(b"%PDF"):
                logger.error(f"[SECURITY] Fake PDF header detected in '{file_path}'. Expected '%PDF'.")
                return False
        elif ext == ".docx":
            if not header.startswith(b"PK\x03\x04"):
                logger.error(f"[SECURITY] Fake DOCX header detected in '{file_path}'. Expected ZIP signature 'PK\\x03\\x04'.")
                return False
        elif ext in [".txt", ".md"]:
            if b"\x00" in header:
                logger.error(f"[SECURITY] Binary null bytes detected in text document '{file_path}'.")
                return False
            # Verify valid UTF-8 decoding
            try:
                header.decode("utf-8")
            except UnicodeDecodeError:
                logger.error(f"[SECURITY] Non-UTF8 text encoding in '{file_path}'.")
                return False
    except Exception as e:
        logger.error(f"Failed to inspect magic bytes for '{file_path}': {e}")
        return False

    return True

def extract_text_from_file(file_path: str) -> str:
    """Extracts raw text content from PDF, DOCX, TXT, or MD files."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except Exception as e:
            logger.error(f"Failed to read PDF '{file_path}': {e}")
            return ""

    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            return "\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Failed to read DOCX '{file_path}': {e}")
            return ""

    else:
        logger.warning(f"Unsupported document format: '{ext}' for file {file_path}")
        return ""

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """Splits raw text into sliding window chunks with overlap."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks = []
    start = 0
    text_len = len(cleaned)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        # Avoid splitting words if possible
        if end < text_len:
            space_idx = cleaned.rfind(" ", start, end)
            if space_idx > start + (chunk_size // 2):
                end = space_idx

        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break
        start = end - overlap

    return chunks

def build_index_from_documents(
    docs_dir: str = "data/documents",
    index_dir: str = "data/index",
    chunk_size: int = 500,
    overlap: int = 100,
    mock: bool = False
) -> int:
    """Processes all documents in docs_dir and builds a FAISS index."""
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        logger.warning(f"Documents directory '{docs_dir}' was empty. Created folder.")
        return 0

    valid_extensions = {".pdf", ".docx", ".txt", ".md"}
    doc_files = [
        f for f in os.listdir(docs_dir)
        if os.path.splitext(f)[1].lower() in valid_extensions and not f.startswith(".")
    ]

    if not doc_files:
        logger.warning(f"No PDF/DOCX/TXT/MD files found in '{docs_dir}'.")
        return 0

    logger.info(f"Found {len(doc_files)} document(s) in '{docs_dir}'. Processing...")

    all_chunks: List[Dict[str, Any]] = []
    chunk_counter = 1

    for file_name in doc_files:
        file_path = os.path.join(docs_dir, file_name)
        if not validate_document_file(file_path, allowed_base_dir=docs_dir):
            logger.warning(f"[SECURITY] Rejecting invalid or untrusted document: '{file_name}'. Skipping.")
            continue

        content = extract_text_from_file(file_path)
        if not content.strip():
            logger.warning(f"Skipping empty or unreadable file: '{file_name}'")
            continue

        raw_chunks = chunk_text(content, chunk_size=chunk_size, overlap=overlap)
        logger.info(f"File '{file_name}': generated {len(raw_chunks)} chunk(s).")

        for idx, text in enumerate(raw_chunks):
            all_chunks.append({
                "chunk_id": f"chunk_{chunk_counter}",
                "doc_name": file_name,
                "section_index": idx + 1,
                "text": text,
                "source_file": file_path,
                "char_count": len(text)
            })
            chunk_counter += 1

    if not all_chunks:
        logger.warning("No text chunks could be extracted from documents.")
        return 0

    logger.info(f"Total chunks extracted: {len(all_chunks)}. Computing embeddings with multilingual-e5-small...")
    embeddings_service = MultilingualE5Embeddings(mock=mock)
    passages = [c["text"] for c in all_chunks]
    vectors = embeddings_service.embed_passages(passages)

    logger.info(f"Embeddings computed with shape {vectors.shape}. Writing FAISS index to '{index_dir}'...")
    build_faiss_index(vectors, all_chunks, output_dir=index_dir)
    logger.info(f"Index successfully built and saved to '{index_dir}'.")
    return len(all_chunks)

def main():
    parser = argparse.ArgumentParser(description="Build FAISS RAG index from data/documents/")
    parser.add_argument("--docs-dir", default="data/documents", help="Path to documents folder")
    parser.add_argument("--index-dir", default="data/index", help="Path to save index and chunks")
    parser.add_argument("--chunk-size", type=int, default=500, help="Chunk size in characters")
    parser.add_argument("--overlap", type=int, default=100, help="Chunk overlap in characters")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock embeddings")
    args = parser.parse_args()

    total = build_index_from_documents(
        docs_dir=args.docs_dir,
        index_dir=args.index_dir,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        mock=args.mock
    )
    print(f"Done. Indexed {total} chunks.")

if __name__ == "__main__":
    main()
