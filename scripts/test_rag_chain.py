"""End-to-end RAG chain test — retrieval + LLM answer in one shot.

Usage:
    python scripts/test_rag_chain.py
    python scripts/test_rag_chain.py --question "what is ELSS?" --category tax

Runs 3 built-in queries and prints:
  - the answer the LLM generated
  - which source chunks were used (from ask_with_sources)

This is different from test_retriever.py which only checks retrieval.
Here we verify the full pipeline: retrieve → prompt → LLM → answer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from rag.chain import build_rag_chain  # noqa: E402

SMOKE_QUERIES = [
    ("what is LTCG tax on equity mutual funds?", "tax"),
    ("how does a SIP work and why is it better than lump sum?", "mutual-funds"),
    ("what is loss aversion and how does it affect investors?", "behavioural"),
]


def print_result(question: str, result: dict) -> None:
    print(f"\n{'═' * 65}")
    print(f"QUESTION : {question}")
    print(f"{'─' * 65}")

    if result["sources"]:
        print("SOURCES USED:")
        for s in result["sources"]:
            dist = f"dist={s['distance']:.4f}" if s["distance"] else ""
            print(f"  • [{s['category']}] {s['section']}  {dist}")
    else:
        print("SOURCES  : (none — retriever returned nothing above threshold)")

    print(f"{'─' * 65}")
    print("ANSWER:")
    print(result["answer"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", help="Custom question to test")
    parser.add_argument("--category", help="Optional category filter")
    args = parser.parse_args()

    print("Building RAG chain …")
    chain = build_rag_chain()
    print("Ready.\n")

    if args.question:
        result = chain.ask_with_sources(args.question, category=args.category)
        print_result(args.question, result)
    else:
        print("Running 3 end-to-end queries …")
        for question, category in SMOKE_QUERIES:
            result = chain.ask_with_sources(question, category=category)
            print_result(question, result)

    print(f"\n{'═' * 65}")
    print("RAG chain test complete.")


if __name__ == "__main__":
    main()
