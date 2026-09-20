"""
Unit tests for the SenseAI Model Context Protocol (MCP) server.
Verifies JSON-RPC 2.0 handshake, tools listing, read-only search/history queries, and error handling.
"""

import os
import json
import tempfile
import pytest

from src.backend.mcp_server.server import SenseAIMCPServer
from src.backend.database.storage import EmotionStorage
from src.backend.rag.retriever import RAGRetriever


@pytest.fixture
def mock_retriever():
    """Provides a RAGRetriever initialized with in-memory test documents."""
    retriever = RAGRetriever(mock=True)
    sample_chunks = [
        {
            "doc_name": "company_policy.md",
            "chunk_id": 1,
            "text": "Full-time employees are entitled to 20 days of paid annual leave.",
            "source_file": "data/documents/company_policy.md"
        },
        {
            "doc_name": "developer_guide.md",
            "chunk_id": 2,
            "text": "All API endpoints must bind strictly to 127.0.0.1 for security.",
            "source_file": "data/documents/developer_guide.md"
        }
    ]
    retriever.build_in_memory_index(sample_chunks)
    return retriever


@pytest.fixture
def temp_storage():
    """Provides an EmotionStorage backed by a temporary SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_mcp.db")
        storage = EmotionStorage(db_path=db_path)
        storage.save_emotion_event(
            conversation_id="session_alpha_123",
            primary_emotion="happy",
            confidence=0.92,
            valence=0.75,
            arousal=0.60,
            raw_transcript="I love how fast this assistant responds!"
        )
        storage.save_emotion_event(
            conversation_id="session_alpha_123",
            primary_emotion="neutral",
            confidence=0.88,
            valence=0.05,
            arousal=0.10,
            raw_transcript="Can you check my annual leave balance?"
        )
        yield storage


def test_mcp_initialize_and_ping():
    server = SenseAIMCPServer()

    # 1. Initialize
    init_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-agent", "version": "1.0.0"}
        }
    })
    raw_resp = server.process_line(init_req)
    assert raw_resp is not None
    resp = json.loads(raw_resp)
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "senseai-mcp-server"
    assert "tools" in resp["result"]["capabilities"]

    # 2. Notification initialized (must return None, no response)
    notif = json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    })
    assert server.process_line(notif) is None

    # 3. Ping
    ping_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "ping"
    })
    raw_resp = server.process_line(ping_req)
    assert raw_resp is not None
    resp = json.loads(raw_resp)
    assert resp["id"] == 2
    assert resp["result"] == {}


def test_mcp_tools_list():
    server = SenseAIMCPServer()
    list_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/list"
    })
    raw_resp = server.process_line(list_req)
    assert raw_resp is not None
    resp = json.loads(raw_resp)
    assert resp["id"] == 10

    tools = resp["result"]["tools"]
    assert len(tools) == 2
    tool_names = [t["name"] for t in tools]
    assert "search_documents" in tool_names
    assert "get_conversation_history" in tool_names

    search_tool = next(t for t in tools if t["name"] == "search_documents")
    assert "query" in search_tool["inputSchema"]["required"]

    history_tool = next(t for t in tools if t["name"] == "get_conversation_history")
    assert "session_id" in history_tool["inputSchema"]["required"]


def test_mcp_search_documents(mock_retriever):
    server = SenseAIMCPServer(retriever=mock_retriever)

    call_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {
            "name": "search_documents",
            "arguments": {
                "query": "annual leave policy",
                "top_k": 2
            }
        }
    })
    raw_resp = server.process_line(call_req)
    assert raw_resp is not None
    resp = json.loads(raw_resp)
    assert resp["id"] == 20
    assert resp["result"]["isError"] is False

    content_text = resp["result"]["content"][0]["text"]
    assert "company_policy.md" in content_text or "leave" in content_text


def test_mcp_get_conversation_history(temp_storage):
    server = SenseAIMCPServer(storage=temp_storage)

    call_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 30,
        "method": "tools/call",
        "params": {
            "name": "get_conversation_history",
            "arguments": {
                "session_id": "session_alpha_123",
                "limit": 5
            }
        }
    })
    raw_resp = server.process_line(call_req)
    assert raw_resp is not None
    resp = json.loads(raw_resp)
    assert resp["id"] == 30
    assert resp["result"]["isError"] is False

    content_text = resp["result"]["content"][0]["text"]
    assert "session_alpha_123" in content_text
    assert "HAPPY" in content_text
    assert "annual leave" in content_text


def test_mcp_validation_and_errors():
    server = SenseAIMCPServer()

    # 1. Invalid JSON
    raw_resp = server.process_line("{invalid json")
    assert raw_resp is not None
    resp = json.loads(raw_resp)
    assert resp["error"]["code"] == -32700

    # 2. Unknown method
    raw_resp = server.process_line(json.dumps({"jsonrpc": "2.0", "id": 99, "method": "unknown_method"}))
    resp = json.loads(raw_resp)
    assert resp["error"]["code"] == -32601

    # 3. Unknown tool
    raw_resp = server.process_line(json.dumps({
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {"name": "delete_all_data", "arguments": {}}
    }))
    resp = json.loads(raw_resp)
    assert resp["error"]["code"] == -32601
    assert "Unknown tool" in resp["error"]["message"]

    # 4. Missing required query in search_documents
    raw_resp = server.process_line(json.dumps({
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {"name": "search_documents", "arguments": {}}
    }))
    resp = json.loads(raw_resp)
    assert resp["result"]["isError"] is True
    assert "required" in resp["result"]["content"][0]["text"]

    # 5. Missing required session_id in get_conversation_history
    raw_resp = server.process_line(json.dumps({
        "jsonrpc": "2.0",
        "id": 102,
        "method": "tools/call",
        "params": {"name": "get_conversation_history", "arguments": {}}
    }))
    resp = json.loads(raw_resp)
    assert resp["result"]["isError"] is True
    assert "required" in resp["result"]["content"][0]["text"]
