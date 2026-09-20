"""
SenseAI Model Context Protocol (MCP) Server.
Specification: 2024-11-05 (JSON-RPC 2.0 over stdio).

Exposes read-only bridges to:
1. RAG vector document retriever (`search_documents`)
2. Conversation transcripts and emotion history (`get_conversation_history`)

Strict Invariant:
- Read-only access only.
- No model invocation, no pipeline triggering, no write/delete tools.
"""

import sys
import json
import logging
from typing import Dict, Any, Optional, List

from ..rag.retriever import RAGRetriever
from ..database.storage import EmotionStorage

# Configure stderr logger so stdin/stdout remain clean for JSON-RPC
logger = logging.getLogger("senseai-mcp")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("[%(asctime)s] [SenseAI-MCP] %(levelname)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "senseai-mcp-server"
SERVER_VERSION = "0.1.0"


class SenseAIMCPServer:
    """
    Standard MCP server running JSON-RPC 2.0 over stdio.
    Provides external agents with read-only tools to query knowledge and session history.
    """

    def __init__(
        self,
        retriever: Optional[RAGRetriever] = None,
        storage: Optional[EmotionStorage] = None,
        index_dir: str = "data/index",
        db_path: str = "database/dev.db"
    ):
        self.retriever = retriever or RAGRetriever(index_dir=index_dir)
        self.storage = storage or EmotionStorage(db_path=db_path)
        self.initialized = False

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns the JSON schemas for the two exposed read-only tools."""
        return [
            {
                "name": "search_documents",
                "description": (
                    "Perform semantic vector search against local RAG knowledge documents. "
                    "Returns relevant excerpts with document citations and similarity scores."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query to search documents for."
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of relevant chunks to retrieve (default: 3).",
                            "default": 3
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_conversation_history",
                "description": (
                    "Retrieve past emotion observations, valence/arousal coordinates, and spoken transcripts "
                    "for a given conversation or session ID. Read-only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The unique conversation_id or session identifier."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of historical records to return (default: 10).",
                            "default": 10
                        }
                    },
                    "required": ["session_id"]
                }
            }
        ]

    def handle_search_documents(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes read-only semantic document retrieval."""
        query = arguments.get("query", "").strip()
        if not query:
            return {
                "content": [{"type": "text", "text": "Error: 'query' parameter is required and cannot be empty."}],
                "isError": True
            }

        top_k = int(arguments.get("top_k", 3))
        chunks = self.retriever.retrieve(query=query, top_k=top_k)

        if not chunks:
            return {
                "content": [{"type": "text", "text": f"No relevant documents found for query: '{query}'."}],
                "isError": False
            }

        formatted_lines = [f"Found {len(chunks)} relevant document excerpt(s) for query: '{query}':\n"]
        for idx, chunk in enumerate(chunks, 1):
            doc = chunk.get("doc_name", "Unknown Document")
            chunk_id = chunk.get("chunk_id", idx)
            score = chunk.get("score", 0.0)
            text = chunk.get("text", "").strip()
            formatted_lines.append(f"[{idx}] Source: {doc} (Chunk #{chunk_id}, Relevance Score: {score:.4f})")
            formatted_lines.append(f"{text}\n")

        return {
            "content": [{"type": "text", "text": "\n".join(formatted_lines).strip()}],
            "isError": False
        }

    def handle_get_conversation_history(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes read-only session emotion and transcript lookup."""
        session_id = arguments.get("session_id", "").strip()
        if not session_id:
            return {
                "content": [{"type": "text", "text": "Error: 'session_id' parameter is required and cannot be empty."}],
                "isError": True
            }

        limit = int(arguments.get("limit", 10))
        history = self.storage.get_history(conversation_id=session_id, limit=limit)

        if not history:
            return {
                "content": [{"type": "text", "text": f"No historical records found for session_id: '{session_id}'."}],
                "isError": False
            }

        formatted_lines = [f"Conversation history for session '{session_id}' ({len(history)} record(s)):\n"]
        for idx, record in enumerate(history, 1):
            ts = record.get("timestamp", "unknown-time")
            emotion = record.get("primary_emotion", "neutral")
            conf = record.get("confidence", 0.0)
            valence = record.get("valence", 0.0)
            arousal = record.get("arousal", 0.0)
            transcript = record.get("raw_transcript", "").strip()

            formatted_lines.append(
                f"[{idx}] Timestamp: {ts} | Emotion: {emotion.upper()} (conf: {conf:.2f}, valence: {valence:.2f}, arousal: {arousal:.2f})"
            )
            formatted_lines.append(f"    Transcript: \"{transcript}\"\n")

        return {
            "content": [{"type": "text", "text": "\n".join(formatted_lines).strip()}],
            "isError": False
        }

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Dispatches incoming JSON-RPC 2.0 requests.
        Returns a response dict, or None for notifications.
        """
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if not method:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: 'method' is required."}
            }

        # Handle notifications (e.g. notifications/initialized)
        if method == "notifications/initialized" or method == "initialized":
            logger.info("Client completed MCP initialization handshake.")
            return None

        # 1. initialize
        if method == "initialize":
            self.initialized = True
            client_info = params.get("clientInfo", {})
            logger.info(f"Initialized by client: {client_info.get('name', 'unknown')} v{client_info.get('version', '')}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {
                            "listChanged": False
                        }
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    }
                }
            }

        # 2. ping
        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {}
            }

        # 3. tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.get_tool_definitions()
                }
            }

        # 4. tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "search_documents":
                result = self.handle_search_documents(arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
            elif tool_name == "get_conversation_history":
                result = self.handle_get_conversation_history(arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: Unknown tool '{tool_name}'."
                    }
                }

        # Unrecognized method
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: '{method}'."
            }
        }

    def process_line(self, line: str) -> Optional[str]:
        """
        Parses a single JSON-RPC line and returns the JSON-RPC response string (or None).
        """
        line = line.strip()
        if not line:
            return None

        try:
            req = json.loads(line)
        except json.JSONDecodeError as err:
            logger.error(f"JSON decode error: {err}")
            return json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(err)}"}
            })

        response = self.handle_request(req)
        if response is not None:
            return json.dumps(response)
        return None

    def run_stdio(self):
        """Runs the MCP server loop reading lines from stdin and emitting to stdout."""
        logger.info(f"SenseAI MCP Server started ({SERVER_NAME} v{SERVER_VERSION}) listening on stdio...")
        for raw_line in sys.stdin:
            resp = self.process_line(raw_line)
            if resp:
                sys.stdout.write(resp + "\n")
                sys.stdout.flush()
        logger.info("SenseAI MCP Server shut down.")


def main():
    server = SenseAIMCPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
