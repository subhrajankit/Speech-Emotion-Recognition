"""
Evaluate Intent Router Gate precision, recall, and latency on labelled dataset.
Labelled dataset contains 70 queries (35 chat, 35 knowledge_query) across English, Hindi, and Hinglish.
"""

import time
from collections import defaultdict
from rag.eval_dataset import EVALUATION_DATASET
from rag.intent_router import IntentRouter
from rag.embeddings import MultilingualE5Embeddings

def main():
    print("=" * 60)
    print("INTENT ROUTER GATE EVALUATION (70 LABELLED EXAMPLES)")
    print("Dataset composition: 35 'chat', 35 'knowledge_query'")
    print("Languages: English (en), Hindi (hi), Hinglish (hi-Latn)")
    print("Note: This evaluation set is small and indicative only.")
    print("=" * 60)

    # Load embedder once
    t0 = time.perf_counter()
    embedder = MultilingualE5Embeddings()
    router = IntentRouter(embedder=embedder)
    # Pre-warm anchors
    router._ensure_anchor_embeddings()
    init_time = time.perf_counter() - t0
    print(f"Embedder and anchor embeddings loaded in {init_time:.2f}s\n")

    results = []
    latencies = []

    # Counters: true label -> predicted label
    confusion = defaultdict(lambda: defaultdict(int))
    lang_confusion = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for item in EVALUATION_DATASET:
        qid = item["id"]
        lang = item["language"]
        gold = item["label"]
        query = item["query"]

        t_start = time.perf_counter()
        pred_res = router.classify(query)
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000
        latencies.append(t_elapsed_ms)

        pred = pred_res.intent
        is_correct = (pred == gold)
        confusion[gold][pred] += 1
        lang_confusion[lang][gold][pred] += 1

        results.append({
            "id": qid,
            "lang": lang,
            "gold": gold,
            "pred": pred,
            "method": pred_res.method,
            "score": pred_res.score,
            "correct": is_correct,
            "query": query,
            "latency_ms": t_elapsed_ms,
        })

    # Print any misclassifications
    mismatches = [r for r in results if not r["correct"]]
    if mismatches:
        print(f"MISCLASSIFICATIONS ({len(mismatches)} / {len(results)}):")
        for m in mismatches:
            print(f"  [ID {m['id']}] ({m['lang']}) Gold: {m['gold']} | Pred: {m['pred']} ({m['method']}) Query: \"{m['query']}\"")
        print()
    else:
        print("All 70 examples correctly classified on this set.\n")

    # Metrics computation
    # Target class: knowledge_query
    # TP: gold=knowledge_query, pred=knowledge_query
    # FP: gold=chat, pred=knowledge_query
    # FN: gold=knowledge_query, pred=chat
    # TN: gold=chat, pred=chat
    tp = confusion["knowledge_query"]["knowledge_query"]
    fp = confusion["chat"]["knowledge_query"]
    fn = confusion["knowledge_query"]["chat"]
    tn = confusion["chat"]["chat"]

    prec_kq = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec_kq = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_kq = 2 * prec_kq * rec_kq / (prec_kq + rec_kq) if (prec_kq + rec_kq) > 0 else 0.0

    # Class: chat
    tp_c = tn
    fp_c = fn
    fn_c = fp
    tn_c = tp
    prec_chat = tp_c / (tp_c + fp_c) if (tp_c + fp_c) > 0 else 0.0
    rec_chat = tp_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0.0
    f1_chat = 2 * prec_chat * rec_chat / (prec_chat + rec_chat) if (prec_chat + rec_chat) > 0 else 0.0

    overall_acc = (tp + tn) / len(results)

    print("--- CONFUSION MATRIX ---")
    print(f"                         Predicted CHAT    Predicted KNOWLEDGE")
    print(f"Actual CHAT             : {tn:14d}    {fp:19d}")
    print(f"Actual KNOWLEDGE_QUERY  : {fn:14d}    {tp:19d}")
    print()

    print("--- OVERALL METRICS ---")
    print(f"Overall Accuracy         : {overall_acc:.4f} ({tp+tn}/{len(results)})")
    print(f"Knowledge Query Precision: {prec_kq:.4f}")
    print(f"Knowledge Query Recall   : {rec_kq:.4f}")
    print(f"Knowledge Query F1       : {f1_kq:.4f}")
    print(f"Chat Precision           : {prec_chat:.4f}")
    print(f"Chat Recall              : {rec_chat:.4f}")
    print(f"Chat F1                  : {f1_chat:.4f}")
    print()

    print("--- PER-LANGUAGE BREAKDOWN ---")
    for lang in ["en", "hi", "hi-Latn"]:
        l_tp = lang_confusion[lang]["knowledge_query"]["knowledge_query"]
        l_fp = lang_confusion[lang]["chat"]["knowledge_query"]
        l_fn = lang_confusion[lang]["knowledge_query"]["chat"]
        l_tn = lang_confusion[lang]["chat"]["chat"]
        l_total = l_tp + l_fp + l_fn + l_tn
        l_acc = (l_tp + l_tn) / l_total if l_total > 0 else 0.0
        l_prec = l_tp / (l_tp + l_fp) if (l_tp + l_fp) > 0 else 0.0
        l_rec = l_tp / (l_tp + l_fn) if (l_tp + l_fn) > 0 else 0.0
        print(f"Language: {lang:7s} | Count: {l_total:2d} | Acc: {l_acc:.4f} | KQ Prec: {l_prec:.4f} | KQ Rec: {l_rec:.4f}")
    print()

    avg_lat = sum(latencies) / len(latencies)
    p95_lat = sorted(latencies)[int(0.95 * len(latencies))]
    print(f"--- LATENCY (ms) ---")
    print(f"Mean: {avg_lat:.2f} ms | P95: {p95_lat:.2f} ms | Min: {min(latencies):.2f} ms | Max: {max(latencies):.2f} ms")
    print("=" * 60)

if __name__ == "__main__":
    main()
