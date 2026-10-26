"""
Document ingestion and recursive character chunker.
Supports .md, .txt, .pdf, and .docx formats.
Generates SHA256 document hashes and structured chunk metadata.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file for integrity and metadata tracking."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_text_from_file(file_path: Path) -> str:
    """Extracts raw text content from Markdown, Plaintext, PDF, or Word documents."""
    suffix = file_path.suffix.lower()

    if suffix in (".md", ".txt"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    elif suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except Exception as e:
            logger.error(f"Failed to read PDF '{file_path}': {e}")
            raise

    elif suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Failed to read DOCX '{file_path}': {e}")
            raise

    else:
        logger.warning(f"Unsupported file extension '{suffix}' for file '{file_path}'. Reading as plaintext.")
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


class DocumentChunker:
    """
    Splits text into chunks of `chunk_size` characters with `chunk_overlap`.
    Prefers splitting on paragraphs, then sentences, then whitespace.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        if chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size}).")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str, doc_name: str, doc_hash: str) -> List[Dict[str, Any]]:
        """
        Chunks text and attaches document metadata.
        """
        clean_text = text.strip()
        if not clean_text:
            return []

        chunks: List[Dict[str, Any]] = []
        start = 0
        text_len = len(clean_text)
        chunk_idx = 0

        while start < text_len:
            end = min(start + self.chunk_size, text_len)

            # If not at the end of the text, look for clean boundaries
            if end < text_len:
                # 1. Paragraph boundary
                p_break = clean_text.rfind("\n\n", start, end)
                if p_break != -1 and p_break > start + (self.chunk_size // 2):
                    end = p_break + 2
                else:
                    # 2. Sentence boundary
                    s_break = max(
                        clean_text.rfind(". ", start, end),
                        clean_text.rfind("। ", start, end),  # Hindi purna viram
                        clean_text.rfind("? ", start, end),
                        clean_text.rfind("! ", start, end),
                    )
                    if s_break != -1 and s_break > start + (self.chunk_size // 2):
                        end = s_break + 2
                    else:
                        # 3. Word boundary
                        w_break = clean_text.rfind(" ", start, end)
                        if w_break != -1 and w_break > start + (self.chunk_size // 2):
                            end = w_break + 1

            chunk_content = clean_text[start:end].strip()
            if chunk_content:
                chunks.append({
                    "chunk_id": f"{doc_name}:{chunk_idx}",
                    "doc_name": doc_name,
                    "doc_hash": doc_hash,
                    "chunk_index": chunk_idx,
                    "text": chunk_content,
                    "char_start": start,
                    "char_end": end,
                })
                chunk_idx += 1

            if end >= text_len:
                break

            step = self.chunk_size - self.chunk_overlap
            start += max(1, step)

        return chunks

    def process_directory(self, docs_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Parses all documents in `docs_dir`, computes hashes, and returns (chunks, doc_hashes).
        """
        supported_extensions = {".md", ".txt", ".pdf", ".docx"}
        all_chunks: List[Dict[str, Any]] = []
        doc_hashes: Dict[str, str] = {}

        if not docs_dir.exists():
            return all_chunks, doc_hashes

        files = [
            p for p in docs_dir.iterdir()
            if p.is_file() and p.suffix.lower() in supported_extensions and not p.name.startswith(".")
        ]

        for file_path in sorted(files, key=lambda f: f.name):
            doc_name = file_path.name
            doc_hash = compute_file_sha256(file_path)
            doc_hashes[doc_name] = doc_hash

            text = extract_text_from_file(file_path)
            doc_chunks = self.chunk_text(text, doc_name=doc_name, doc_hash=doc_hash)
            all_chunks.extend(doc_chunks)
            logger.info(f"Processed document '{doc_name}': {len(doc_chunks)} chunks created.")

        return all_chunks, doc_hashes
