# 05 — Data Sources Specification (Phase 6 RAG)

## 1. Overview
SenseAI utilizes a local, privacy-first Retrieval-Augmented Generation (RAG) architecture. Knowledge retrieval is strictly gated by the Intent Router and is only invoked when an utterance is classified into the `knowledge` intent category.

---

## 2. Ingestion Formats & Location
All local reference documents are placed in the static repository directory:
```
data/documents/
  ├── *.pdf      # Portable Document Format (extracted via pypdf)
  ├── *.docx     # Microsoft Word Documents (extracted via python-docx)
  ├── *.md       # Markdown documentation (UTF-8)
  └── *.txt       # Plain text reference manuals (UTF-8)
```

---

## 3. Chunking Pipeline
Ingestion is performed by the standalone script:
[`scripts/database/build_rag_index.py`](file:///D:/Capstone%20Project/NewSenseVoice/scripts/database/build_rag_index.py)

- **Execution Invariant**: Executed offline or on-demand when new documents are added. **NEVER run per-request**.
- **Window Strategy**: Sliding window with word boundary snapping:
  - `chunk_size`: 500 characters (~100 words).
  - `overlap`: 100 characters (~20 words).
- **Metadata Tracked per Chunk**:
  ```json
  {
    "chunk_id": "chunk_1",
    "doc_name": "company_policy.md",
    "section_index": 1,
    "text": "...",
    "source_file": "data/documents/company_policy.md",
    "char_count": 487
  }
  ```

---

## 4. Dense Vector Representation
- **Model**: `intfloat/multilingual-e5-small`
- **Embedding Dimension**: 384
- **Prefix Protocol**:
  - Documents / Passages: `"passage: " + text`
  - User Queries: `"query: " + text`
- **Normalization**: L2 normalized for cosine similarity matching.

---

## 5. Vector Index Storage
- **FAISS Index**: Stored in `data/index/rag.index` (`IndexFlatIP` inner product).
- **Chunk Metadata**: Stored in `data/index/chunks.json`.
- **Top-K Retrieval**: Defaults to `top_k = 3` with min score threshold $0.25$.
- **Citation Invariant**: All retrieved chunks are tagged with their source `doc_name`, and responses must explicitly cite `"Based on <doc_name>: "`.
