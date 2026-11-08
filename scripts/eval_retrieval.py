"""Retrieval quality evaluation — Precision@k, Recall@k, F1@k, MRR, Hit Rate.

Relevance criterion (Option 2 — keyword-based):
  A retrieved chunk is "relevant" if its text contains at least one of the
  query's expected_keywords.  This is more robust than category matching because:
  - Category labels are a folder convention, not a semantic guarantee.
  - The same concept (e.g. SIP) can appear in multiple folders.
  - Keywords are set from the reference_answer and directly test content recall.

NO category_filter is passed to the retriever — if we filter by category and then
check if results match that category, we always get Precision = 1.0 (tautology).
Real evaluation means: "without telling the system which category, does it still
find the right content?"

Metrics:
  Precision@k  = relevant_retrieved / k
                 "Of the k chunks we fetched, what fraction were actually useful?"
  Recall@k     = 1 if any relevant chunk in top-k, else 0
                 Simplified: we can't count ALL relevant docs in the index, so we
                 use binary recall — did we surface at least one correct chunk?
  F1@k         = 2 * P * R / (P + R)   harmonic mean, 0 when either P or R = 0
  MRR          = 1 / rank_of_first_relevant_chunk
                 "How many irrelevant results did we scroll past before the first good one?"
  Hit Rate@k   = same as Recall@k (included for naming clarity in reports)

Comparison: runs vector-only (use_mmr=False) vs MMR (use_mmr=True) on the same
queries and prints a side-by-side table so you can see whether MMR helps or hurts.

Usage:
    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --top-k 6
    python scripts/eval_retrieval.py --trace          # show retrieved chunks per query
    python scripts/eval_retrieval.py --output-json    # dump full trace to JSON file
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from core.config import load_config  # noqa: E402
from rag.embedder import get_client as get_openai_client  # noqa: E402
from rag.retriever import FinnieRetriever  # noqa: E402
from rag.vector_store import get_client, get_or_create_collection  # noqa: E402
from utils.console import ensure_utf8_stdout  # noqa: E402

QUERIES_FILE = PROJECT_ROOT / "data" / "eval_queries.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def load_positive_queries() -> list[dict]:
    """Return only the 'positive' queries — those with a known expected_category."""
    data = json.loads(QUERIES_FILE.read_text(encoding="utf-8"))
    return [q for q in data["queries"] if q["type"] == "positive"]


def build_retriever_pair(top_k: int) -> tuple[FinnieRetriever, FinnieRetriever]:
    """Build two retrievers sharing the same Chroma client: vector-only and MMR."""
    cfg = load_config()
    chroma = get_client(cfg.resolve(cfg.rag.index_dir))
    collection = get_or_create_collection(chroma)
    openai = get_openai_client()

    common = dict(
        collection=collection,
        openai_client=openai,
        top_k=top_k,
        relevance_threshold=cfg.rag.relevance_threshold,
    )
    vector_only = FinnieRetriever(**common, use_mmr=False)
    mmr         = FinnieRetriever(**common, use_mmr=True)
    return vector_only, mmr


# ── per-query metrics ────────────────────────────────────────────────────────

def evaluate_query(
    retriever: FinnieRetriever,
    query: dict,
    top_k: int,
) -> dict:
    """Run one query and return its metric scores + full retrieved chunk trace."""
    expected_cat = query["expected_category"]

    # NO category_filter — retriever must find the right content on its own
    docs = retriever.get_relevant_documents(query["question"])

    # Keyword-based relevance: a chunk is relevant if its text contains any
    # expected keyword (case-insensitive). Falls back to category match if no
    # keywords are defined on the query (backward-compatible).
    keywords = [kw.lower() for kw in query.get("expected_keywords", [])]

    # Build a detailed trace of every retrieved chunk
    retrieved_chunks = []
    for rank, doc in enumerate(docs, start=1):
        text_lower = doc.page_content.lower()
        if keywords:
            is_relevant = any(kw in text_lower for kw in keywords)
            matched_kws = [kw for kw in keywords if kw in text_lower]
        else:
            # Fallback: use category match when no keywords defined
            is_relevant = doc.metadata.get("category", "") == expected_cat
            matched_kws = []
        retrieved_chunks.append({
            "rank": rank,
            "category": doc.metadata.get("category", ""),
            "section": doc.metadata.get("section", ""),
            "source": doc.metadata.get("source", ""),
            "distance": round(doc.metadata.get("distance", -1.0), 4),
            "text_preview": doc.page_content[:150].replace("\n", " ") + (
                "…" if len(doc.page_content) > 150 else ""
            ),
            "relevant": is_relevant,
            "matched_keywords": matched_kws,
        })

    retrieved_cats = [c["category"] for c in retrieved_chunks]
    relevant_flags = [c["relevant"] for c in retrieved_chunks]

    n_relevant = sum(relevant_flags)
    k = len(docs)  # may be < top_k if retriever returned fewer

    precision = n_relevant / k if k > 0 else 0.0
    recall    = 1.0 if n_relevant > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)
    hit_rate  = recall

    mrr = 0.0
    for rank, flag in enumerate(relevant_flags, start=1):
        if flag:
            mrr = 1.0 / rank
            break

    return {
        "id": query["id"],
        "type": query.get("type", "positive"),
        "difficulty": query.get("difficulty", ""),
        "question": query["question"],
        "question_short": query["question"][:60] + "…" if len(query["question"]) > 60 else query["question"],
        "expected_category": expected_cat,
        "retrieved_categories": retrieved_cats,
        "retrieved_chunks": retrieved_chunks,
        "n_retrieved": k,
        "n_relevant": n_relevant,
        "precision": round(precision, 3),
        "recall":    round(recall, 3),
        "f1":        round(f1, 3),
        "mrr":       round(mrr, 3),
        "hit_rate":  round(hit_rate, 3),
    }


# ── aggregate + print ────────────────────────────────────────────────────────

def aggregate(results: list[dict]) -> dict:
    keys = ["precision", "recall", "f1", "mrr", "hit_rate"]
    return {k: round(mean(r[k] for r in results), 3) for k in keys}


def aggregate_by_difficulty(results: list[dict]) -> dict:
    """Break down mean metrics by difficulty level.

    "realistic" is deliberately its own bucket rather than being folded into
    easy/medium/hard. Those three were written against Varsity chapters already in
    the index, which flatters the score -- they measure "can it find the chunk I was
    thinking of". The realistic set was written from the beginner persona's actual
    phrasing, with no reference to what the corpus contains, so it is the honest
    number and must stay visible instead of being averaged away.
    """
    breakdown = {}
    for diff in ["easy", "medium", "hard", "realistic"]:
        subset = [r for r in results if r.get("difficulty") == diff]
        if subset:
            breakdown[diff] = aggregate(subset)
    return breakdown


def print_results(label: str, results: list[dict], agg: dict) -> None:
    print(f"\n{'═' * 90}")
    print(f"  {label}")
    print(f"{'─' * 90}")
    print(f"  {'ID':<6} {'Diff':<8} {'P@k':>6} {'R@k':>6} {'F1@k':>6} {'MRR':>6} {'Hit':>6}  Question")
    print(f"{'─' * 90}")
    for r in results:
        print(
            f"  {r['id']:<6} "
            f"{r.get('difficulty', ''):<8} "
            f"{r['precision']:>6.3f} "
            f"{r['recall']:>6.3f} "
            f"{r['f1']:>6.3f} "
            f"{r['mrr']:>6.3f} "
            f"{r['hit_rate']:>6.3f}  "
            f"{r['question_short']}"
        )
    print(f"{'─' * 90}")
    print(
        f"  {'MEAN':<6} {'':8} "
        f"{agg['precision']:>6.3f} "
        f"{agg['recall']:>6.3f} "
        f"{agg['f1']:>6.3f} "
        f"{agg['mrr']:>6.3f} "
        f"{agg['hit_rate']:>6.3f}"
    )


def print_difficulty_breakdown(label: str, breakdown: dict) -> None:
    print(f"\n  {label} — by difficulty:")
    print(f"  {'Level':<8} {'P@k':>6} {'R@k':>6} {'F1@k':>6} {'MRR':>6} {'Hit':>6}")
    print(f"  {'─' * 46}")
    for diff, agg in breakdown.items():
        print(
            f"  {diff:<8} "
            f"{agg['precision']:>6.3f} "
            f"{agg['recall']:>6.3f} "
            f"{agg['f1']:>6.3f} "
            f"{agg['mrr']:>6.3f} "
            f"{agg['hit_rate']:>6.3f}"
        )


def print_comparison(agg_vec: dict, agg_mmr: dict) -> None:
    print(f"\n{'═' * 55}")
    print("  VECTOR-ONLY vs MMR — aggregate comparison")
    print(f"{'─' * 55}")
    print(f"  {'Metric':<12} {'Vector-only':>12} {'MMR':>12} {'Δ':>10}")
    print(f"{'─' * 55}")
    for key in ["precision", "recall", "f1", "mrr", "hit_rate"]:
        delta = agg_mmr[key] - agg_vec[key]
        sign  = "+" if delta >= 0 else ""
        print(f"  {key:<12} {agg_vec[key]:>12.3f} {agg_mmr[key]:>12.3f} {sign}{delta:>9.3f}")
    print(f"{'═' * 55}")


def print_trace(results: list[dict], label: str) -> None:
    """Print full retrieved chunk trace for each query."""
    print(f"\n{'═' * 90}")
    print(f"  RETRIEVED CHUNK TRACE — {label}")
    print(f"{'═' * 90}")
    for r in results:
        verdict = "✓ HIT" if r["recall"] > 0 else "✗ MISS"
        print(f"\n  [{r['id']}] [{r.get('difficulty','').upper()}] {verdict}  expected={r['expected_category']}")
        print(f"  Q: {r['question']}")
        print(f"  Metrics: P={r['precision']:.3f}  R={r['recall']:.3f}  F1={r['f1']:.3f}  MRR={r['mrr']:.3f}")
        print(f"  {'─' * 85}")
        if not r["retrieved_chunks"]:
            print("  (no chunks retrieved)")
        for c in r["retrieved_chunks"]:
            relevant_flag = "✓" if c.get("relevant", False) else "✗"
            kw_hit = f" kw={c['matched_keywords']}" if c.get("matched_keywords") else ""
            print(
                f"  [{c['rank']}] {relevant_flag} "
                f"cat={c['category']:<12} "
                f"dist={c['distance']:.4f}  "
                f"{c['text_preview']}"
                f"{kw_hit}"
            )


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality.")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks to retrieve")
    parser.add_argument("--trace", action="store_true", help="Print full chunk trace per query")
    parser.add_argument("--output-json", action="store_true", help="Dump full results to JSON")
    args = parser.parse_args()

    queries = load_positive_queries()
    print(f"Loaded {len(queries)} positive queries from {QUERIES_FILE.name}")
    print(f"Building retrievers (top_k={args.top_k}) …")
    print("Note: NO category_filter used — retriever must find content on its own.")

    retriever_vec, retriever_mmr = build_retriever_pair(top_k=args.top_k)

    print("Running vector-only retrieval …")
    results_vec = [evaluate_query(retriever_vec, q, args.top_k) for q in queries]
    agg_vec     = aggregate(results_vec)
    diff_vec    = aggregate_by_difficulty(results_vec)

    print("Running MMR retrieval …")
    results_mmr = [evaluate_query(retriever_mmr, q, args.top_k) for q in queries]
    agg_mmr     = aggregate(results_mmr)
    diff_mmr    = aggregate_by_difficulty(results_mmr)

    print_results(f"VECTOR-ONLY  (top_k={args.top_k})", results_vec, agg_vec)
    print_difficulty_breakdown("Vector-only", diff_vec)

    print_results(f"MMR          (top_k={args.top_k}, λ=0.5)", results_mmr, agg_mmr)
    print_difficulty_breakdown("MMR", diff_mmr)

    print_comparison(agg_vec, agg_mmr)

    if args.trace:
        print_trace(results_vec, f"VECTOR-ONLY (top_k={args.top_k})")
        print_trace(results_mmr, f"MMR (top_k={args.top_k})")

    if args.output_json:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = PROJECT_ROOT / "data" / f"eval_retrieval_results_{ts}.json"
        payload = {
            "run_at": ts,
            "top_k": args.top_k,
            "n_queries": len(queries),
            "vector_only": {
                "aggregate": agg_vec,
                "by_difficulty": diff_vec,
                "per_query": results_vec,
            },
            "mmr": {
                "aggregate": agg_mmr,
                "by_difficulty": diff_mmr,
                "per_query": results_mmr,
            },
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    main()
