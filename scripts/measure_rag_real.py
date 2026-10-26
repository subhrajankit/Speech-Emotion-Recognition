"""
Real RAG Evaluation Script
Measures intent router gate precision and recall, as well as FAISS retrieval
using real SentenceTransformer ('intfloat/multilingual-e5-small') embeddings.
"""

import json
from rag.intent_router import IntentRouter
from rag.vectorstore import FAISSVectorStore
from rag.embeddings import MultilingualE5Embeddings

def main():
    embedder = MultilingualE5Embeddings()
    router = IntentRouter(embedder=embedder)
    vectorstore = FAISSVectorStore()
    vectorstore.load("data/index")

    knowledge_queries = [
        "What is the company policy on remote work?",
        "What are the warranty terms for the hardware product?",
        "How do I setup the local development environment?",
    ]

    chat_utterances = [
        "Good morning! How are you doing today?",
        "I feel so happy that the weekend is finally here.",
        "Tell me a funny story about cats.",
    ]

    print("=== 3 KNOWLEDGE QUERIES ===")
    for q in knowledge_queries:
        cls = router.classify(q)
        query_vec = embedder.embed_queries([q])[0]
        hits = vectorstore.search(query_vec, top_k=2)
        chunk, score = hits[0]
        clean_snippet = chunk["text"].replace("\n", " ")[:80]
        doc_id = chunk.get("doc_name", chunk.get("chunk_id"))
        print(f"Query: {q}")
        print(f"  Intent: {cls.intent} (method={cls.method}, score={cls.score:.3f})")
        print(f"  Top Hit: {doc_id} (score={score:.3f}) snippet: {clean_snippet}...")

    print("\n=== 3 CHAT UTTERANCES ===")
    for q in chat_utterances:
        cls = router.classify(q)
        print(f"Query: {q}")
        print(f"  Intent: {cls.intent} (method={cls.method}, score={cls.score:.3f})")

    # Measure Gate Precision / Recall
    tp = sum(1 for q in knowledge_queries if router.classify(q).intent == "knowledge_query")
    fn = sum(1 for q in knowledge_queries if router.classify(q).intent != "knowledge_query")
    fp = sum(1 for q in chat_utterances if router.classify(q).intent == "knowledge_query")
    tn = sum(1 for q in chat_utterances if router.classify(q).intent != "knowledge_query")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    print(f"\nGATE METRICS: TP={tp}, FN={fn}, FP={fp}, TN={tn}")
    print(f"Gate Precision: {precision:.4f}, Gate Recall: {recall:.4f}")

if __name__ == "__main__":
    main()
