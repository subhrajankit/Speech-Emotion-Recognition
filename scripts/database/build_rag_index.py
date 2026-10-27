#!/usr/bin/env python3
"""
Pointer / shim redirecting to canonical RAG ingestion module.
Canonical module: rag.ingestion (Usage: python -m rag.ingestion --docs data/documents --index-dir data/index)
"""
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from rag.ingestion import main

if __name__ == "__main__":
    main()
