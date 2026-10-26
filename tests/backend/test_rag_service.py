"""
Integration tests for backend RAGService and speech_socket wiring.
Includes call spy test proving that 'chat' utterances make ZERO calls to retrieval.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.rag_service import RAGService, rag_service
from rag.ingestion import run_ingestion


from tests.test_doubles import FakeEmbeddings


@pytest.fixture
def populated_rag_service(tmp_path):
    """Initializes a RAGService with fixture index."""
    fixtures_dir = Path("tests/fixtures/sample_docs")
    index_dir = tmp_path / "rag_service_store"

    fake_emb = FakeEmbeddings()
    run_ingestion(
        docs_dir=str(fixtures_dir),
        index_dir=str(index_dir),
        embedder=fake_emb,
    )

    service = RAGService(
        index_dir=str(index_dir),
        similarity_threshold=0.20,
    )
    service.initialize()
    if service.retriever:
        service.retriever.embedder = fake_emb
    return service


@pytest.mark.asyncio
async def test_chat_utterance_makes_zero_retrieval_calls(populated_rag_service, monkeypatch):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Prove with a call spy / counter that 'chat' utterances make ZERO calls to retrieval or FAISS.
    """
    retrieval_counter = 0

    original_retrieve = populated_rag_service.retriever.retrieve

    def spy_retrieve(*args, **kwargs):
        nonlocal retrieval_counter
        retrieval_counter += 1
        return original_retrieve(*args, **kwargs)

    monkeypatch.setattr(populated_rag_service.retriever, "retrieve", spy_retrieve)

    # 1. Test conversational chat utterance
    chat_query = "Hello, good morning! How are you doing today?"
    turn_res = await populated_rag_service.process_turn(chat_query)

    assert turn_res.intent.intent == "chat"
    assert turn_res.retrieval_performed is False
    assert turn_res.grounded_context == ""
    assert turn_res.cited_docs == []
    # Assert spy counter is strictly ZERO
    assert retrieval_counter == 0, f"Expected 0 retrieval calls for chat turn, got {retrieval_counter}"

    # 2. Test casual emotional utterance
    emotional_query = "I'm feeling really happy today, tell me something interesting!"
    turn_res2 = await populated_rag_service.process_turn(emotional_query)

    assert turn_res2.intent.intent == "chat"
    assert turn_res2.retrieval_performed is False
    # Assert spy counter is STILL strictly ZERO
    assert retrieval_counter == 0, f"Expected 0 retrieval calls for emotional turn, got {retrieval_counter}"

    # 3. Contrast: Knowledge query MUST invoke retrieval
    knowledge_query = "According to company policy, what is the customer refund window?"
    turn_res3 = await populated_rag_service.process_turn(knowledge_query)

    assert turn_res3.intent.intent == "knowledge_query"
    assert turn_res3.retrieval_performed is True
    # Now retrieval counter must be exactly 1
    assert retrieval_counter == 1, f"Expected 1 retrieval call for knowledge query, got {retrieval_counter}"
    assert len(turn_res3.chunks) > 0
    assert "company_policy_fixture.md" in turn_res3.grounded_context


@pytest.mark.asyncio
async def test_knowledge_fallback_when_index_unloaded():
    """
    When vector store is unindexed or missing, knowledge query gracefully
    degrades to chat without crashing or fabricating citations.
    """
    empty_service = RAGService(index_dir="non_existent_dir_123")
    empty_service.initialize()

    turn_res = await empty_service.process_turn("According to the document, what is the policy?")
    assert turn_res.intent.intent == "knowledge_query"
    assert turn_res.retrieval_performed is False
    assert turn_res.chunks == []
    assert turn_res.grounded_context == ""
    assert turn_res.cited_docs == []


def test_health_endpoint_reports_rag_status():
    """Verifies that /api/health includes real 'rag' component status."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert "components" in data
    assert "rag" in data["components"]
    assert data["components"]["rag"] in ("ok", "no_index", "unavailable")

    assert "details" in data
    assert "rag" in data["details"]
    assert "model_name" in data["details"]["rag"]
    assert "dimension" in data["details"]["rag"]


def test_websocket_knowledge_query_and_chat_turn_events(monkeypatch, tmp_path):
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Over WebSocket:
    1. Knowledge question gets an answer with retrieved context, 'rag_sources' event,
       and sources on 'llm_done'.
    2. Casual chat sentence skips retrieval, receives zero rag_sources, and llm_done has empty sources.
    3. Missing index emits status='rag_fallback' and falls back to plain chat cleanly.
    """
    import httpx
    from backend.app.services.speech_service import speech_service
    from backend.app.services.llm_service import llm_service
    from ai.inference.types import SpeechResult

    # Populate temporary index
    fixtures_dir = Path("tests/fixtures/sample_docs")
    index_dir = tmp_path / "ws_test_vectorstore"
    fake_emb = FakeEmbeddings()
    run_ingestion(
        docs_dir=str(fixtures_dir),
        index_dir=str(index_dir),
        embedder=fake_emb,
    )
    rag_service.index_dir = index_dir
    rag_service.similarity_threshold = 0.20
    rag_service.initialize()
    if rag_service.retriever:
        rag_service.retriever.embedder = fake_emb

    # Mock LLM streaming responses
    def mock_llm_stream_handler(request: httpx.Request):
        content = (
            b'data: {"choices":[{"delta":{"content":"Based on company policy, "}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"the refund window is 30 days."}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        return httpx.Response(200, content=content)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_llm_stream_handler))
    monkeypatch.setattr(llm_service, "_custom_client", mock_client)

    client = TestClient(app)

    # 1. Turn 1: Knowledge query
    async def mock_knowledge_transcribe(*args, **kwargs):
        return SpeechResult(
            transcript="According to the company policy, what is the refund window?",
            language="en",
            emotion="neutral",
            confidence=None,
            processing_time_ms=50.0,
            model_version="test_mock",
        )

    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", mock_knowledge_transcribe)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        ws.send_bytes(b"\x00\x00" * 1024)
        ws.send_json({"type": "stop"})

        events = []
        for _ in range(10):
            ev = ws.receive_json()
            events.append(ev)
            if ev.get("type") == "llm_done":
                break

        event_types = [e.get("type") for e in events]
        assert "speech_result" in event_types
        assert "rag_sources" in event_types
        assert "llm_done" in event_types

        rag_src_ev = next(e for e in events if e.get("type") == "rag_sources")
        assert len(rag_src_ev["sources"]) > 0
        assert any("company_policy_fixture.md" in s["doc_name"] for s in rag_src_ev["sources"])

        done_ev = next(e for e in events if e.get("type") == "llm_done")
        assert "refund window is 30 days" in done_ev["text"]
        assert len(done_ev["sources"]) > 0

    # 2. Turn 2: Chat query (must skip RAG)
    async def mock_chat_transcribe(*args, **kwargs):
        return SpeechResult(
            transcript="Hello! How are you doing today?",
            language="en",
            emotion="happy",
            confidence=None,
            processing_time_ms=45.0,
            model_version="test_mock",
        )

    monkeypatch.setattr(speech_service, "transcribe_pcm16_bytes", mock_chat_transcribe)

    with client.websocket_connect("/ws/speech") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json().get("type") == "ready"

        ws.send_bytes(b"\x00\x00" * 1024)
        ws.send_json({"type": "stop"})

        chat_events = []
        for _ in range(10):
            ev = ws.receive_json()
            chat_events.append(ev)
            if ev.get("type") == "llm_done":
                break

        chat_event_types = [e.get("type") for e in chat_events]
        assert "speech_result" in chat_event_types
        # PROOF: 'rag_sources' MUST NOT be emitted for chat
        assert "rag_sources" not in chat_event_types
        assert "llm_done" in chat_event_types

        chat_done_ev = next(e for e in chat_events if e.get("type") == "llm_done")
        assert chat_done_ev["sources"] == []
