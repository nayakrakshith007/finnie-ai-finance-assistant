"""Smoke test — verify the retriever returns sensible results.

Usage:
    python scripts/test_retriever.py
    python scripts/test_retriever.py --query "what is SIP" --category mutual-funds

Runs 5 built-in test queries and prints the top result for each.
Use --query to test your own question interactively.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from rag.retriever import build_retriever  # noqa: E402

SMOKE_QUERIES = [
    ("what is LTCG tax on equity", "tax"),
    ("how does SIP work", "mutual-funds"),
    ("what is loss aversion", "behavioural"),
    ("difference between ETF and mutual fund", None),
    ("what is PPF and how much can I invest", "retirement"),
]


def print_result(query: str, category: str | None, docs: list) -> None:
    print(f"\n{'─' * 60}")
    print(f"QUERY    : {query}")
    print(f"CATEGORY : {category or 'all'}")
    print(f"RESULTS  : {len(docs)} chunk(s) passed threshold")
    if docs:
        top = docs[0]
        print(f"TOP HIT  : {top.metadata.get('title', '?')} — {top.metadata.get('section', '?')}")
        print(f"SOURCE   : {top.metadata.get('source', '?')}")
        print(f"DISTANCE : {top.metadata.get('distance', '?')}")
        print(f"PREVIEW  : {top.page_content[:200].replace(chr(10), ' ')} …")
    else:
        print("TOP HIT  : (none — all results below relevance threshold)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", help="Custom query to test")
    parser.add_argument("--category", help="Optional category filter")
    args = parser.parse_args()

    print("Building retriever …")
    retriever = build_retriever()
    print("Ready.\n")

    if args.query:
        docs = retriever.get_relevant_documents(args.query, category=args.category)
        print_result(args.query, args.category, docs)
    else:
        print("Running 5 smoke queries …")
        for query, category in SMOKE_QUERIES:
            docs = retriever.get_relevant_documents(query, category=category)
            print_result(query, category, docs)

    print(f"\n{'─' * 60}")
    print("Smoke test complete.")


if __name__ == "__main__":
    main()
