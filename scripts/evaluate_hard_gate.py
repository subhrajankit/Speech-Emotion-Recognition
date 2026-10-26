"""
VoiceSense AI — Hard Intent Router Gate Evaluation Script.
Evaluates the Intent Router on rag/hard_eval_dataset.py.
Computes metrics and lists every misclassified example.

Label: "authored by the same agent, indicative only"
"""

import sys
import time
from pathlib import Path
from collections import defaultdict

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from rag.hard_eval_dataset import HARD_EVALUATION_DATASET
from rag.intent_router import IntentRouter
from rag.embeddings import MultilingualE5Embeddings


def evaluate():
    print("=" * 70)
    print("HARD INTENT ROUTER GATE EVALUATION (50 LABELLED EXAMPLES)")
    print("Dataset composition: 25 'chat', 25 'knowledge_query'")
    print("Categories: Distractor policy/warranty words in chat, short follow-ups,")
    print("            general knowledge out-of-scope, subtle implicit doc queries.")
    print("NOTICE: Authored by the same agent, indicative only.")
    print("=" * 70)

    t0 = time.perf_counter()
    embedder = MultilingualE5Embeddings()
    router = IntentRouter(embedder=embedder)
    router._ensure_anchor_embeddings()
    print(f"Router loaded in {time.perf_counter() - t0:.2f}s\n")

    results = []
    latencies = []
    confusion = defaultdict(lambda: defaultdict(int))
    category_confusion = defaultdict(lambda: {"total": 0, "correct": 0})
    misclassified = []

    for item in HARD_EVALUATION_DATASET:
        qid = item["id"]
        lang = item["language"]
        gold = item["label"]
        category = item["category"]
        query = item["query"]

        t_start = time.perf_counter()
        pred_res = router.classify(query)
        latency_ms = (time.perf_counter() - t_start) * 1000
        latencies.append(latency_ms)

        pred = pred_res.intent
        is_correct = (pred == gold)
        confusion[gold][pred] += 1
        category_confusion[category]["total"] += 1
        if is_correct:
            category_confusion[category]["correct"] += 1
        else:
            misclassified.append({
                "id": qid,
                "category": category,
                "language": lang,
                "query": query,
                "gold": gold,
                "predicted": pred,
                "method": pred_res.method,
                "score": pred_res.score,
            })

        results.append({
            "id": qid,
            "category": category,
            "gold": gold,
            "pred": pred,
            "method": pred_res.method,
            "score": pred_res.score,
            "correct": is_correct,
            "query": query,
        })

    total = len(HARD_EVALUATION_DATASET)
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total

    # Precision, recall, F1 for knowledge_query
    tp = confusion["knowledge_query"]["knowledge_query"]
    fp = confusion["chat"]["knowledge_query"]
    fn = confusion["knowledge_query"]["chat"]
    tn = confusion["chat"]["chat"]

    precision_k = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall_k = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_k = (2 * precision_k * recall_k / (precision_k + recall_k)) if (precision_k + recall_k) > 0 else 0.0

    # Precision, recall, F1 for chat
    precision_c = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    recall_c = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1_c = (2 * precision_c * recall_c / (precision_c + recall_c)) if (precision_c + recall_c) > 0 else 0.0

    print(f"Overall Accuracy: {correct}/{total} ({accuracy * 100:.1f}%)")
    print(f"Latency: Mean = {sum(latencies)/len(latencies):.2f} ms (Min = {min(latencies):.2f} ms, Max = {max(latencies):.2f} ms)")
    print("\nConfusion Matrix:")
    print(f"                Predicted CHAT  Predicted KNOWLEDGE")
    print(f"  Actual CHAT:        {tn:2d}              {fp:2d}")
    print(f"  Actual KNOWLEDGE:   {fn:2d}              {tp:2d}")

    print("\nMetrics Breakdown:")
    print(f"  Knowledge Query: Precision = {precision_k:.3f}, Recall = {recall_k:.3f}, F1 = {f1_k:.3f}")
    print(f"  Conversational Chat: Precision = {precision_c:.3f}, Recall = {recall_c:.3f}, F1 = {f1_c:.3f}")

    print(f"\nMisclassified Examples Count: {len(misclassified)}")
    if misclassified:
        print("-" * 70)
        for m in misclassified:
            print(f"[{m['id']}] Category: {m['category']} | Lang: {m['language']}")
            print(f"  Query: \"{m['query']}\"")
            print(f"  Expected: {m['gold']} | Predicted: {m['predicted']} (via {m['method']}, score={m['score']})")
        print("-" * 70)


if __name__ == "__main__":
    evaluate()
