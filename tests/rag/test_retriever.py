"""
Unit and integration tests for RAGRetriever.
Asserts top-k accuracy, score thresholding, citation formatting,
and zero citation fabrication.
"""

from pathlib import Path
import time
import pytest

from rag.embeddings import MultilingualE5Embeddings
from rag.ingestion import run_ingestion
from rag.retriever import RAGRetriever
from rag.vectorstore import FAISSVectorStore


@pytest.fixture(scope="module")
def built_fixture_vectorstore(tmp_path_factory):
    """Builds an isolated vectorstore from the fixture documents."""
    tmp_dir = tmp_path_factory.mktemp("retriever_store")
    fixtures_dir = Path("tests/fixtures/sample_docs")

    run_ingestion(
        docs_dir=str(fixtures_dir),
        index_dir=str(tmp_dir),
    )

    store = FAISSVectorStore(
        dimension=384,
        model_name="intfloat/multilingual-e5-small",
        index_dir=str(tmp_dir),
    )
    store.load()
    return store


def test_top_k_retrieval_facts(built_fixture_vectorstore):
    """
    Verifies that questions answerable from the fixture docs retrieve
    the exact expected chunks with high scores.
    """
    embedder = MultilingualE5Embeddings()
    retriever = RAGRetriever(
        vectorstore=built_fixture_vectorstore,
        embedder=embedder,
        top_k=2,
        similarity_threshold=0.10,
    )

    # 1. Query: Customer refund policy
    start_t = time.perf_counter()
    chunks1 = retriever.retrieve("According to policy, what is the refund window?")
    search_latency_ms = (time.perf_counter() - start_t) * 1000

    assert len(chunks1) > 0
    top_chunk1 = chunks1[0]
    assert top_chunk1.doc_name == "company_policy_fixture.md"
    assert "30 days" in top_chunk1.text
    assert "money-back guarantee" in top_chunk1.text
    assert top_chunk1.score > 0.10
    # Assert fast retrieval (< 50ms)
    assert search_latency_ms < 50.0

    # 2. Query: Maintenance schedule
    chunks2 = retriever.retrieve("When is the cloud server maintenance scheduled?")
    assert len(chunks2) > 0
    top_chunk2 = chunks2[0]
    assert top_chunk2.doc_name == "maintenance_schedule_fixture.txt"
    assert "02:00 UTC" in top_chunk2.text


def test_score_threshold_filters_unrelated_queries(built_fixture_vectorstore):
    """
    If similarity does not meet threshold, retriever returns empty list.
    Never fabricates context or citations.
    """
    embedder = MultilingualE5Embeddings()
    retriever = RAGRetriever(
        vectorstore=built_fixture_vectorstore,
        embedder=embedder,
        top_k=3,
        similarity_threshold=0.99,  # Impossibly high threshold
    )

    chunks = retriever.retrieve("Random unrelated query that should not pass")
    assert chunks == []

    context_str, cited_docs = retriever.format_grounded_context(chunks)
    assert context_str == ""
    assert cited_docs == []


def test_grounded_context_and_citation_formatting(built_fixture_vectorstore):
    """
    Verifies that formatted context contains excerpt blocks and cited_docs references for the UI.
    """
    embedder = MultilingualE5Embeddings()
    retriever = RAGRetriever(
        vectorstore=built_fixture_vectorstore,
        embedder=embedder,
        top_k=2,
        similarity_threshold=0.10,
    )

    chunks = retriever.retrieve("Parental leave policy")
    assert len(chunks) > 0

    context_str, cited_docs = retriever.format_grounded_context(chunks)
    assert "--- GROUNDED KNOWLEDGE BASE EXCERPTS" in context_str
    assert "company_policy_fixture.md" in context_str
    assert "16 weeks" in context_str

    assert len(cited_docs) == len(chunks)
    assert any(ref["doc_name"] == "company_policy_fixture.md" for ref in cited_docs)
    for ref in cited_docs:
        assert "doc_name" in ref
        assert "chunk_id" in ref
        assert "score" in ref
