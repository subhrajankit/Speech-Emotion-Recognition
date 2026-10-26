"""
Unit tests for MultilingualE5Embeddings.
Verifies prefix conventions ('query: ', 'passage: '), L2 normalization,
and vector dimensions.
"""

import numpy as np
import pytest
from rag.embeddings import MultilingualE5Embeddings, EMBEDDING_DIMENSION

pytestmark = pytest.mark.model


def test_embedding_dimensions_and_types():
    embedder = MultilingualE5Embeddings()
    assert embedder.dimension == EMBEDDING_DIMENSION
    assert embedder.dimension == 384

    query_vec = embedder.embed_query("What is the refund policy?")
    assert isinstance(query_vec, np.ndarray)
    assert query_vec.shape == (384,)
    assert query_vec.dtype == np.float32

    passages = [
        "Refunds are processed within 5 business days.",
        "Full refunds are available within 30 days.",
    ]
    passage_vecs = embedder.embed_passages(passages)
    assert isinstance(passage_vecs, np.ndarray)
    assert passage_vecs.shape == (2, 384)
    assert passage_vecs.dtype == np.float32


def test_vector_l2_normalization():
    """Inner product on L2-normalized vectors mathematically equals cosine similarity."""
    embedder = MultilingualE5Embeddings()

    vec = embedder.embed_query("Server maintenance schedule")
    norm = np.linalg.norm(vec)
    assert pytest.approx(norm, rel=1e-4) == 1.0

    passages = ["Doc A content", "Doc B content", "Doc C content"]
    vecs = embedder.embed_passages(passages)
    for v in vecs:
        assert pytest.approx(np.linalg.norm(v), rel=1e-4) == 1.0


def test_empty_passages_handling():
    embedder = MultilingualE5Embeddings()
    empty_vecs = embedder.embed_passages([])
    assert empty_vecs.shape == (0, 384)

    empty_queries = embedder.embed_queries([])
    assert empty_queries.shape == (0, 384)


def test_prefix_convention_preservation(monkeypatch):
    """
    Verifies that 'query: ' and 'passage: ' prefixes are strictly applied
    as required by intfloat/multilingual-e5-small model card.
    """
    embedder = MultilingualE5Embeddings()
    recorded_texts = []

    def fake_encode(texts, **kwargs):
        if isinstance(texts, str):
            recorded_texts.append(texts)
            return np.ones(384, dtype=np.float32) / np.sqrt(384)
        else:
            recorded_texts.extend(texts)
            arr = np.ones((len(texts), 384), dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            return arr / norms

    monkeypatch.setattr(embedder.model, "encode", fake_encode)

    embedder.embed_query("check vacation policy")
    assert len(recorded_texts) == 1
    assert recorded_texts[0] == "query: check vacation policy"

    embedder.embed_passages(["first passage text", "second passage text"])
    assert len(recorded_texts) == 3
    assert recorded_texts[1] == "passage: first passage text"
    assert recorded_texts[2] == "passage: second passage text"
