"""
SenseAI MCP Server package.
Exposes read-only access to RAG document retriever and conversation history.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import SenseAIMCPServer

__all__ = ["SenseAIMCPServer"]
