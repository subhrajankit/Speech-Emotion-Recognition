"""
Tests for Document Chunking, Ingestion CLI, and FAISS Vector Store integrity.
Verifies metadata tracking, SHA-256 document hashing, and config mismatch checks.
"""

from pathlib import Path
import json
import pytest

from rag.chunking import DocumentChunker, compute_file_sha256
from rag.ingestion import run_ingestion
from rag.vectorstore import FAISSVectorStore, IndexConfigMismatchError
from tests.test_doubles import FakeEmbeddings


def test_compute_file_sha256(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello VoiceSense RAG", encoding="utf-8")

    h = compute_file_sha256(test_file)
    assert isinstance(h, str)
    assert len(h) == 64  # SHA-256 is 64 hex characters


def test_document_chunker_basic():
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
    sample_text = (
        "This is paragraph one.\n\n"
        "This is paragraph two containing some more sentences to split.\n\n"
        "This is paragraph three."
    )
    chunks = chunker.chunk_text(sample_text, doc_name="test.md", doc_hash="dummy_hash")
    assert len(chunks) >= 2
    for c in chunks:
        assert c["doc_name"] == "test.md"
        assert c["doc_hash"] == "dummy_hash"
        assert len(c["text"]) <= 120  # respects bounded boundary extension


def test_ingestion_cli_on_fixture_docs(tmp_path):
    """
    Tests end-to-end ingestion pipeline on test fixture documents:
    1. Runs ingestion.
    2. Verifies files are saved: index.faiss, chunks.json, index_metadata.json.
    3. Verifies metadata schema and document hashes.
    """
    fixtures_dir = Path("tests/fixtures/sample_docs")
    assert fixtures_dir.is_dir(), "Fixture docs directory must exist"

    index_dir = tmp_path / "test_vectorstore"

    fake_emb = FakeEmbeddings(model_id="intfloat/multilingual-e5-small", dimension=384)
    total_chunks = run_ingestion(
        docs_dir=str(fixtures_dir),
        index_dir=str(index_dir),
        chunk_size=300,
        chunk_overlap=50,
        embedder=fake_emb,
    )

    assert total_chunks > 0

    index_file = index_dir / "index.faiss"
    chunks_file = index_dir / "chunks.json"
    meta_file = index_dir / "index_metadata.json"

    assert index_file.exists()
    assert chunks_file.exists()
    assert meta_file.exists()

    # Verify metadata fields
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["model_name"] == "intfloat/multilingual-e5-small"
    assert meta["dimension"] == 384
    assert meta["chunk_size"] == 300
    assert meta["chunk_overlap"] == 50
    assert meta["total_chunks"] == total_chunks
    assert "company_policy_fixture.md" in meta["doc_hashes"]
    assert len(meta["doc_hashes"]["company_policy_fixture.md"]) == 64


def test_index_config_mismatch_rejection(tmp_path):
    """
    Refuses to load an index built with a different model or dimension.
    Guarantees clear error message and prevents silent vector mismatch.
    """
    fixtures_dir = Path("tests/fixtures/sample_docs")
    index_dir = tmp_path / "test_mismatch_store"

    # Build index with standard config
    fake_emb = FakeEmbeddings(model_id="intfloat/multilingual-e5-small", dimension=384)
    run_ingestion(
        docs_dir=str(fixtures_dir),
        index_dir=str(index_dir),
        embedder=fake_emb,
    )

    # 1. Attempt to load with a different model name
    store_wrong_model = FAISSVectorStore(
        dimension=384,
        model_name="different-org/different-model",
        index_dir=str(index_dir),
    )
    with pytest.raises(IndexConfigMismatchError) as exc_info:
        store_wrong_model.load()
    assert "Index model mismatch" in str(exc_info.value)
    assert "different-org/different-model" in str(exc_info.value)

    # 2. Attempt to load with a different dimension
    store_wrong_dim = FAISSVectorStore(
        dimension=768,  # Different dimension
        model_name="intfloat/multilingual-e5-small",
        index_dir=str(index_dir),
    )
    with pytest.raises(IndexConfigMismatchError) as exc_info_dim:
        store_wrong_dim.load()
    assert "Index dimension mismatch" in str(exc_info_dim.value)
    assert "768" in str(exc_info_dim.value)


def test_ingestion_empty_directory_returns_zero(tmp_path):
    empty_docs = tmp_path / "empty_docs"
    empty_docs.mkdir()

    out_store = tmp_path / "empty_store"
    count = run_ingestion(docs_dir=str(empty_docs), index_dir=str(out_store))
    assert count == 0
    assert not (out_store / "index.faiss").exists()
