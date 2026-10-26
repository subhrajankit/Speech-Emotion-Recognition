"""
Precision and Recall evaluation benchmark for IntentRouter Gate (Phase 7).
Evaluates 70 labelled utterances (35 chat, 35 knowledge_query) across English,
Hindi (Devanagari), and Hinglish (Latin-script).
"""

import pytest
from rag.eval_dataset import EVALUATION_DATASET
from rag.intent_router import IntentRouter
from rag.embeddings import MultilingualE5Embeddings

pytestmark = pytest.mark.model


def evaluate_gate():
    """
    Evaluates the Intent Router over the full labelled evaluation set.
    Returns precision, recall, f1, and detailed results.
    """
    embedder = MultilingualE5Embeddings()
    router = IntentRouter(embedder=embedder, similarity_threshold=0.75)

    # Positive class = 'knowledge_query', Negative class = 'chat'
    tp = 0  # True Positive (actual knowledge, pred knowledge)
    fp = 0  # False Positive (actual chat, pred knowledge)
    tn = 0  # True Negative (actual chat, pred chat)
    fn = 0  # False Negative (actual knowledge, pred chat)

    results = []

    for item in EVALUATION_DATASET:
        query = item["query"]
        expected = item["label"]
        res = router.classify(query)
        predicted = res.intent

        is_correct = (predicted == expected)
        if expected == "knowledge_query" and predicted == "knowledge_query":
            tp += 1
        elif expected == "chat" and predicted == "knowledge_query":
            fp += 1
        elif expected == "chat" and predicted == "chat":
            tn += 1
        elif expected == "knowledge_query" and predicted == "chat":
            fn += 1

        results.append({
            "id": item["id"],
            "language": item["language"],
            "query": query,
            "expected": expected,
            "predicted": predicted,
            "method": res.method,
            "score": res.score,
            "correct": is_correct,
        })

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(EVALUATION_DATASET)

    return {
        "total": len(EVALUATION_DATASET),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "results": results,
    }


def test_intent_gate_precision_recall():
    """
    Evaluates gate and asserts:
    - Precision >= 0.90
    - Recall >= 0.90
    """
    metrics = evaluate_gate()

    print("\n" + "=" * 60)
    print("INTENT ROUTER EVALUATION BENCHMARK")
    print("=" * 60)
    print(f"Total Evaluated Queries: {metrics['total']}")
    print(f"True Positives (Knowledge): {metrics['tp']}")
    print(f"False Positives (Chat marked as Knowledge): {metrics['fp']}")
    print(f"True Negatives (Chat): {metrics['tn']}")
    print(f"False Negatives (Knowledge missed): {metrics['fn']}")
    print("-" * 60)
    print(f"Accuracy:  {metrics['accuracy'] * 100:.2f}%")
    print(f"Precision: {metrics['precision'] * 100:.2f}%")
    print(f"Recall:    {metrics['recall'] * 100:.2f}%")
    print(f"F1 Score:  {metrics['f1'] * 100:.2f}%")
    print("=" * 60)

    # Show any mistakes
    mistakes = [r for r in metrics["results"] if not r["correct"]]
    if mistakes:
        print(f"\nMistakes ({len(mistakes)}):")
        for m in mistakes:
            safe_query = m["query"].encode("ascii", errors="replace").decode("ascii")
            print(f"  [ID {m['id']} - {m['language']}] '{safe_query}'")
            print(f"     Expected: {m['expected']}, Got: {m['predicted']} (method={m['method']}, score={m['score']})")

    assert metrics["precision"] >= 0.90, f"Precision {metrics['precision']} is below 0.90"
    assert metrics["recall"] >= 0.90, f"Recall {metrics['recall']} is below 0.90"
    assert metrics["accuracy"] >= 0.90, f"Accuracy {metrics['accuracy']} is below 0.90"


if __name__ == "__main__":
    test_intent_gate_precision_recall()
