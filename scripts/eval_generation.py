"""Generation quality evaluation — Groundedness, Relevance, Completeness, ROUGE-L.

For each of the 25 positive queries in eval_queries.json:
  1. Retrieve top-k chunks using the MMR retriever
  2. Generate an answer using the LLM with retrieved context
  3. Score the generated answer on four metrics:

  Groundedness  — Is every claim in the answer supported by the retrieved chunks?
                  (LLM-as-judge, 1–5 scale)
  Relevance     — Does the answer actually address the question asked?
                  (LLM-as-judge, 1–5 scale)
  Completeness  — Does the answer cover the key facts the question expects?
                  (LLM-as-judge, 1–5 scale)
  ROUGE-L       — Longest-common-subsequence overlap with the reference answer.
                  (deterministic, no LLM call)

Why four metrics?
  - ROUGE-L is cheap and fast but punishes paraphrasing.
  - Groundedness catches hallucinations that ROUGE-L misses.
  - Relevance catches answers that are factual but off-topic.
  - Completeness catches answers that are grounded but incomplete.

Usage:
    python scripts/eval_generation.py
    python scripts/eval_generation.py --top-k 6
    python scripts/eval_generation.py --trace          # print full answer per query
    python scripts/eval_generation.py --output-json    # dump results to data/ folder
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from core.config import load_config  # noqa: E402
from core.llm import build_llm       # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from rag.retriever import FinnieRetriever  # noqa: E402
from rag.embedder import get_client as get_openai_client  # noqa: E402
from rag.vector_store import get_client, get_or_create_collection  # noqa: E402

QUERIES_FILE = PROJECT_ROOT / "data" / "eval_queries.json"

# ── ROUGE-L (deterministic) ───────────────────────────────────────────────────

def _lcs_length(a: list[str], b: list[str]) -> int:
    """Dynamic-programming LCS on token lists."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def rouge_l(hypothesis: str, reference: str) -> float:
    """ROUGE-L F1 between hypothesis and reference (token-level)."""
    hyp = hypothesis.lower().split()
    ref = reference.lower().split()
    if not hyp or not ref:
        return 0.0
    lcs = _lcs_length(hyp, ref)
    precision = lcs / len(hyp)
    recall    = lcs / len(ref)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


# ── LLM-as-judge helpers ──────────────────────────────────────────────────────

_JUDGE_SYSTEM = """\
You are a strict but fair evaluator of AI-generated answers.
Score on a scale of 1 to 5 where 1=very poor and 5=excellent.
Return ONLY a JSON object with one key "score" and an integer value, nothing else.
Example: {"score": 4}
"""

def _judge(llm, system_prompt: str, user_prompt: str) -> int:
    """Call the LLM judge and parse the integer score (1–5). Returns 0 on failure."""
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        text = response.content.strip()
        # Tolerate extra text around the JSON
        match = re.search(r'\{[^}]*"score"\s*:\s*(\d)[^}]*\}', text)
        if match:
            score = int(match.group(1))
            return max(1, min(5, score))
    except Exception:
        pass
    return 0


def score_groundedness(llm, question: str, context: str, answer: str) -> int:
    """Is every claim in the answer supported by the retrieved context?"""
    prompt = f"""\
Question: {question}

Retrieved context:
{context}

Generated answer:
{answer}

Score the answer's GROUNDEDNESS: how well every factual claim is supported by
the retrieved context above. A score of 5 means every claim is directly traceable
to the context. A score of 1 means the answer contains significant facts not
present in the context (hallucination).

Return JSON: {{"score": <integer 1-5>}}"""
    return _judge(llm, _JUDGE_SYSTEM, prompt)


def score_relevance(llm, question: str, answer: str) -> int:
    """Does the answer actually address the question?"""
    prompt = f"""\
Question: {question}

Generated answer:
{answer}

Score the answer's RELEVANCE: how directly and completely the answer addresses
the question. A score of 5 means the answer is entirely on-topic and answers
exactly what was asked. A score of 1 means the answer is off-topic or evasive.

Return JSON: {{"score": <integer 1-5>}}"""
    return _judge(llm, _JUDGE_SYSTEM, prompt)


def score_completeness(llm, question: str, answer: str, reference: str) -> int:
    """Does the answer cover the key facts the question expects?"""
    prompt = f"""\
Question: {question}

Reference answer (ground truth):
{reference}

Generated answer:
{answer}

Score the answer's COMPLETENESS: how many of the key facts from the reference
answer appear in the generated answer. A score of 5 means all important facts
are covered. A score of 1 means critical facts are missing.

Return JSON: {{"score": <integer 1-5>}}"""
    return _judge(llm, _JUDGE_SYSTEM, prompt)


# ── Generation ────────────────────────────────────────────────────────────────

_ANSWER_SYSTEM = """\
You are Finnie, an educational AI assistant for personal finance in India.
Answer the question using ONLY the provided context.
Be concise, factual, and accurate. Do not add information not in the context.
End every answer with: "Note: This is for educational purposes only and not financial advice."
"""

def generate_answer(llm, question: str, docs: list) -> str:
    """Generate an answer from the question and retrieved documents."""
    if not docs:
        return "I don't have enough information in my knowledge base to answer this question."

    context = "\n\n---\n\n".join(
        f"[Source: {d.metadata.get('title', 'unknown')}]\n{d.page_content}"
        for d in docs
    )
    prompt = f"Context:\n{context}\n\nQuestion: {question}"
    response = llm.invoke([
        SystemMessage(content=_ANSWER_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()


# ── Per-query evaluation ──────────────────────────────────────────────────────

def evaluate_query(
    retriever: FinnieRetriever,
    llm,
    judge_llm,
    query: dict,
    trace: bool = False,
) -> dict:
    """Retrieve → generate → score one query. Returns a result dict."""
    question  = query["question"]
    reference = query.get("reference_answer", "")

    # Step 1: retrieve
    docs = retriever.get_relevant_documents(question)

    # Step 2: generate
    answer = generate_answer(llm, question, docs)

    # Step 3: build context string for judge
    context = "\n\n".join(d.page_content for d in docs)

    # Step 4: score
    rl     = rouge_l(answer, reference)
    ground = score_groundedness(judge_llm, question, context, answer)
    relev  = score_relevance(judge_llm, question, answer)
    compl  = score_completeness(judge_llm, question, answer, reference)

    if trace:
        print(f"\n  Q: {question}")
        print(f"  A: {answer[:300]}{'…' if len(answer) > 300 else ''}")
        print(f"  Scores → Groundedness={ground}  Relevance={relev}  Completeness={compl}  ROUGE-L={rl:.3f}")

    return {
        "id":           query["id"],
        "difficulty":   query.get("difficulty", ""),
        "question":     question,
        "question_short": question[:60] + "…" if len(question) > 60 else question,
        "generated_answer": answer,
        "reference_answer": reference,
        "n_docs_retrieved": len(docs),
        "groundedness": ground,
        "relevance":    relev,
        "completeness": compl,
        "rouge_l":      rl,
    }


# ── Aggregation + printing ────────────────────────────────────────────────────

def aggregate(results: list[dict]) -> dict:
    keys = ["groundedness", "relevance", "completeness", "rouge_l"]
    return {k: round(mean(r[k] for r in results if r[k] > 0), 3) for k in keys}


def aggregate_by_difficulty(results: list[dict]) -> dict:
    breakdown = {}
    for diff in ["easy", "medium", "hard"]:
        subset = [r for r in results if r.get("difficulty") == diff]
        if subset:
            breakdown[diff] = aggregate(subset)
    return breakdown


def print_results(results: list[dict], agg: dict) -> None:
    print(f"\n{'═' * 100}")
    print("  GENERATION EVAL RESULTS")
    print(f"{'─' * 100}")
    print(f"  {'ID':<6} {'Diff':<8} {'Ground':>8} {'Relev':>7} {'Compl':>7} {'ROUGE-L':>8}  Question")
    print(f"{'─' * 100}")
    for r in results:
        print(
            f"  {r['id']:<6} "
            f"{r['difficulty']:<8} "
            f"{r['groundedness']:>8} "
            f"{r['relevance']:>7} "
            f"{r['completeness']:>7} "
            f"{r['rouge_l']:>8.3f}  "
            f"{r['question_short']}"
        )
    print(f"{'─' * 100}")
    print(
        f"  {'MEAN':<6} {'':8} "
        f"{agg['groundedness']:>8.3f} "
        f"{agg['relevance']:>7.3f} "
        f"{agg['completeness']:>7.3f} "
        f"{agg['rouge_l']:>8.3f}"
    )
    print(f"{'═' * 100}")


def print_difficulty_breakdown(breakdown: dict) -> None:
    print("\n  By difficulty:")
    print(f"  {'Level':<8} {'Ground':>8} {'Relev':>7} {'Compl':>7} {'ROUGE-L':>8}")
    print(f"  {'─' * 46}")
    for diff, agg in breakdown.items():
        print(
            f"  {diff:<8} "
            f"{agg['groundedness']:>8.3f} "
            f"{agg['relevance']:>7.3f} "
            f"{agg['completeness']:>7.3f} "
            f"{agg['rouge_l']:>8.3f}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate generation quality.")
    parser.add_argument("--top-k",      type=int, default=4)
    parser.add_argument("--trace",      action="store_true", help="Print answer per query")
    parser.add_argument("--output-json", action="store_true", help="Dump results to JSON")
    args = parser.parse_args()

    # Load queries
    data = json.loads(QUERIES_FILE.read_text(encoding="utf-8"))
    queries = [q for q in data["queries"] if q["type"] == "positive"]
    print(f"Loaded {len(queries)} positive queries")

    # Build retriever (MMR)
    cfg = load_config()
    chroma = get_client(cfg.rag.index_dir)
    collection = get_or_create_collection(chroma)
    openai = get_openai_client()
    retriever = FinnieRetriever(
        collection=collection,
        openai_client=openai,
        top_k=args.top_k,
        relevance_threshold=cfg.rag.relevance_threshold,
        use_mmr=True,
    )

    # Build LLMs — gpt-4o for generation, gpt-4o-mini for judging (cheaper)
    llm       = build_llm(model="gpt-4o")
    judge_llm = build_llm(model="gpt-4o-mini")
    print(f"Generator: gpt-4o   Judge: gpt-4o-mini   top_k={args.top_k}")
    print("Running generation eval (this makes ~4 LLM calls per query) …\n")

    results = []
    for i, q in enumerate(queries, start=1):
        print(f"  [{i:02d}/{len(queries)}] {q['id']} …", end=" ", flush=True)
        result = evaluate_query(retriever, llm, judge_llm, q, trace=args.trace)
        results.append(result)
        print(f"G={result['groundedness']} R={result['relevance']} C={result['completeness']} ROUGE={result['rouge_l']:.3f}")

    agg = aggregate(results)
    diff = aggregate_by_difficulty(results)

    print_results(results, agg)
    print_difficulty_breakdown(diff)

    if args.output_json:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = PROJECT_ROOT / "data" / f"eval_generation_results_{ts}.json"
        payload = {
            "run_at": ts,
            "top_k": args.top_k,
            "n_queries": len(queries),
            "aggregate": agg,
            "by_difficulty": diff,
            "per_query": results,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    main()
