# 06 — Scraping Specification

## Status: Not Applicable — Static Document Upload Only

SenseAI Voice Assistant is a fully local, privacy-first system. In accordance with project requirements:

1. **No Web Scraping**:
   - Web scraping, live web crawling, and remote web document fetching are explicitly **not applicable** and out of scope.
   - The assistant does not connect to external websites or scrape third-party web services.

2. **Static Document Upload Only**:
   - All knowledge base ingestion is restricted to static, verified documents uploaded or placed locally into `data/documents/` (`.pdf`, `.docx`, `.md`, `.txt`).
   - The standalone indexer script [`scripts/database/build_rag_index.py`](file:///D:/Capstone%20Project/NewSenseVoice/scripts/database/build_rag_index.py) processes static files offline into local FAISS vector indices.
