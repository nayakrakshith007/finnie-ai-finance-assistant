"""Measure the supervisor router against the labelled query set (PRD FR-002).

    python scripts/eval_router.py            # all 40 queries
    python scripts/eval_router.py --limit 10 # a cheap smoke run
    python scripts/eval_router.py --strict   # exit 1 unless the gate is met

The gate is >= 90% accuracy on 40 labelled queries. Two numbers are reported and
both matter:

* **strict** — the route matches `expected` exactly, order included.
* **lenient** — it matches `expected` or one of `also_acceptable`.

Reporting only lenient accuracy would let a set with generous alternatives
flatter the router; reporting only strict would penalise it for picking a route
the label itself admits is defensible. The gate is on strict.

Cost: 40 `gpt-4o-mini` calls with a short prompt, which is a fraction of a cent.
`--limit` exists for iterating on the prompt without paying for the full set
each time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src"), str(Path(__file__).resolve().parents[1])]

from core.logging_setup import get_logger  # noqa: E402
from utils.console import ensure_utf8_stdout  # noqa: E402
from workflow.router import SupervisorRouter  # noqa: E402
from workflow.state import new_state  # noqa: E402

logger = get_logger(__name__)

QUERY_FILE = Path(__file__).resolve().parents[1] / "data" / "router_queries.json"
GATE = 0.90


def load_queries(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["queries"]


def evaluate(queries: list[dict[str, Any]]) -> dict[str, Any]:
    router = SupervisorRouter()
    rows: list[dict[str, Any]] = []

    for item in queries:
        update = router.route(new_state(item["query"]))
        actual = update["route"]
        expected = item["expected"]
        acceptable = [expected, *item.get("also_acceptable", [])]

        rows.append(
            {
                "id": item["id"],
                "query": item["query"],
                "expected": expected,
                "actual": actual,
                "strict": actual == expected,
                "lenient": actual in acceptable,
                "resolved": update.get("resolved_question", ""),
                "why": item.get("why", ""),
            }
        )

    total = len(rows) or 1
    return {
        "rows": rows,
        "total": len(rows),
        "strict_accuracy": sum(r["strict"] for r in rows) / total,
        "lenient_accuracy": sum(r["lenient"] for r in rows) / total,
    }


def report(result: dict[str, Any]) -> None:
    rows = result["rows"]
    print(f"\n{'id':<5} {'ok':<4} {'expected':<42} actual")
    print("-" * 100)
    for row in rows:
        mark = "OK" if row["strict"] else ("~" if row["lenient"] else "X")
        print(f"{row['id']:<5} {mark:<4} {','.join(row['expected']):<42} {','.join(row['actual'])}")

    misses = [r for r in rows if not r["strict"]]
    if misses:
        print("\nDisagreements, for review:")
        for row in misses:
            verdict = "acceptable alternative" if row["lenient"] else "MISS"
            print(f"\n  [{row['id']}] {verdict}: {row['query']!r}")
            print(f"      expected {row['expected']}, got {row['actual']}")
            print(f"      label reason: {row['why']}")

    print(
        f"\nstrict  {result['strict_accuracy']:.1%}  "
        f"({sum(r['strict'] for r in rows)}/{result['total']})"
    )
    print(
        f"lenient {result['lenient_accuracy']:.1%}  "
        f"({sum(r['lenient'] for r in rows)}/{result['total']})"
    )
    print(f"gate    {GATE:.0%} on strict — {'PASS' if result['strict_accuracy'] >= GATE else 'FAIL'}")


def main() -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="evaluate only the first N queries")
    parser.add_argument("--strict", action="store_true", help="exit 1 if the gate is not met")
    parser.add_argument("--json", type=Path, help="also write the full result here")
    args = parser.parse_args()

    queries = load_queries(QUERY_FILE)
    if args.limit:
        queries = queries[: args.limit]

    print(f"Routing {len(queries)} labelled queries through gpt-4o-mini…")
    result = evaluate(queries)
    report(result)

    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")

    if args.strict and result["strict_accuracy"] < GATE:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
