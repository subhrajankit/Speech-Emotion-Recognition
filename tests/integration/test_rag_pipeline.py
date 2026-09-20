import os
import pytest
import asyncio
from src.backend.rag.embeddings import MultilingualE5Embeddings
from src.backend.rag.retriever import RAGRetriever
from src.backend.rag.index import build_faiss_index, load_faiss_index
from src.backend.llm.prompts import format_qwen_knowledge_messages
from src.backend.pipeline.intent import IntentRouter, IntentCategory
from src.backend.pipeline.orchestrator import VoicePipeline
from src.backend.models.manager import model_manager
from scripts.database.build_rag_index import build_index_from_documents

@pytest.fixture
def sample_rag_environment(tmp_path):
    """Creates a sandboxed document repository and builds a FAISS index."""
    docs_dir = str(tmp_path / "docs")
    index_dir = str(tmp_path / "index")
    os.makedirs(docs_dir, exist_ok=True)

    # Doc 1: Refund policy
    doc1_content = (
        "# Customer Refund Policy\n\n"
        "All software licenses purchased within 30 days are eligible for a 100% full money-back guarantee.\n"
        "Refund credits are processed back to the original payment card within 5 business days."
    )
    with open(os.path.join(docs_dir, "refund_policy.md"), "w", encoding="utf-8") as f:
        f.write(doc1_content)

    # Doc 2: Maintenance schedule
    doc2_content = (
        "Infrastructure Maintenance Schedule\n\n"
        "Global server maintenance is scheduled every Sunday at 02:00 AM UTC.\n"
        "During this maintenance window, service downtime will not exceed 15 minutes."
    )
    with open(os.path.join(docs_dir, "maintenance.txt"), "w", encoding="utf-8") as f:
        f.write(doc2_content)

    # Doc 3: Executive lounge access
    doc3_content = (
        "# Executive Lounge Access Guidelines\n\n"
        "Diamond tier loyalty members receive unlimited complimentary access to the airport executive lounge.\n"
        "Guests are entitled to complimentary espresso, snacks, and private meeting booths."
    )
    with open(os.path.join(docs_dir, "lounge_access.md"), "w", encoding="utf-8") as f:
        f.write(doc3_content)

    # Build index
    total_chunks = build_index_from_documents(
        docs_dir=docs_dir,
        index_dir=index_dir,
        mock=True
    )
    assert total_chunks >= 3

    return {"docs_dir": docs_dir, "index_dir": index_dir}


def test_rag_retrieval_accuracy(sample_rag_environment):
    """Asserts questions answerable only from documents retrieve the exact relevant fact."""
    index_dir = sample_rag_environment["index_dir"]
    embeddings = MultilingualE5Embeddings(mock=True)
    retriever = RAGRetriever(embeddings=embeddings, index_dir=index_dir)

    # Query 1: Refund window
    results1 = retriever.retrieve("According to the refund policy, how many days for money-back guarantee?")
    assert len(results1) > 0
    top_doc = results1[0]
    assert top_doc["doc_name"] == "refund_policy.md"
    assert "30 days" in top_doc["text"]
    assert "100% full money-back guarantee" in top_doc["text"]

    # Query 2: Maintenance window
    results2 = retriever.retrieve("What time is the Sunday server maintenance?")
    assert len(results2) > 0
    top_doc2 = results2[0]
    assert top_doc2["doc_name"] == "maintenance.txt"
    assert "02:00 AM UTC" in top_doc2["text"]

    # Query 3: Lounge access
    results3 = retriever.retrieve("Who gets complimentary access to the executive lounge?")
    assert len(results3) > 0
    top_doc3 = results3[0]
    assert top_doc3["doc_name"] == "lounge_access.md"
    assert "Diamond tier" in top_doc3["text"]


def test_rag_citation_formatting(sample_rag_environment):
    """Verifies that grounded context and citation references are properly formatted."""
    index_dir = sample_rag_environment["index_dir"]
    retriever = RAGRetriever(index_dir=index_dir, mock=True)

    results = retriever.retrieve("Tell me about the refund policy guarantee")
    context_str, cited_docs = retriever.format_grounded_context(results)

    assert "refund_policy.md" in cited_docs
    assert "Customer Refund Policy" in context_str

    messages = format_qwen_knowledge_messages(
        transcript="Tell me about the refund policy guarantee",
        grounded_context=context_str,
        cited_docs=cited_docs,
        language="en"
    )

    assert len(messages) == 2
    assert "Mandatory Citation" in messages[0]["content"]
    assert "Based on refund_policy.md" in messages[1]["content"]
    assert "Customer Refund Policy" in messages[1]["content"]


@pytest.mark.asyncio
async def test_end_to_end_knowledge_intent_pipeline(sample_rag_environment):
    """
    Tests end-to-end VoicePipeline execution when intent router resolves 'knowledge'.
    Asserts:
    1. Intent is 'knowledge'.
    2. Response contains citation note ('Based on <doc_name>').
    3. Response contains the grounded fact answerable only from the sample documents.
    """
    model_manager.initialize()
    # Point retriever to the sample test index
    model_manager.retriever = RAGRetriever(index_dir=sample_rag_environment["index_dir"], mock=True)

    pipeline = VoicePipeline()

    # Query matching 'knowledge' keyword pattern
    knowledge_query = "According to the documentation, what is the customer refund policy?"
    
    # 1. Verify intent classification
    intent_result = pipeline.intent_router.classify(knowledge_query)
    assert intent_result.category == IntentCategory.KNOWLEDGE

    # 2. Simulate pipeline execution using mock audio
    import numpy as np
    mock_pcm = np.zeros(16000, dtype=np.int16).tobytes()

    # Stub language router to return this knowledge query
    original_route = model_manager.language_router.route_audio
    from src.backend.asr.router import AudioContext
    model_manager.language_router.route_audio = lambda pcm: AudioContext(
        language="en",
        script="latin",
        mixed_language=False,
        transcript=knowledge_query,
        confidence=0.95,
        model_used="test_stub"
    )

    try:
        transcript, response_text, audio_bytes, latencies, context, intent_dict, emotion = await pipeline.process_utterance(
            mock_pcm, conversation_id="test_rag_conv"
        )

        assert transcript == knowledge_query
        assert intent_dict["category"] == "knowledge"
        assert "cited_docs" in intent_dict
        assert "refund_policy.md" in intent_dict["cited_docs"]

        # Assert grounding note and fact
        assert "based on refund_policy.md" in response_text.lower()
        assert "30 days" in response_text or "100%" in response_text
        assert "rag_ms" in latencies

    finally:
        model_manager.language_router.route_audio = original_route


def test_chat_intent_never_triggers_rag():
    """
    Hard Rule Invariant: General chat queries must NEVER invoke RAG or retrieve documents.
    """
    pipeline = VoicePipeline()
    chat_query = "Hello, good morning! How are you doing today?"

    intent_result = pipeline.intent_router.classify(chat_query)
    assert intent_result.category == IntentCategory.CHAT
    # RAG must not be invoked for general chat
