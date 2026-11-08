"""Structural tests for the accepted router query set (PRD FR-002).

These do **not** call an LLM. Routing accuracy is measured by
`scripts/eval_router.py`, which costs 40 `gpt-4o-mini` calls and therefore has no
business in a suite that must run offline for a grader with no API key.

What these guard instead is the *integrity of the gate itself*. The labels were
reviewed and accepted by the author on 2026-11-08 and are frozen: if a change to
the router drops accuracy below 90%, the fix is in the router, not in the labels.
A frozen artefact with nothing checking it drifts, so:

* every `expected` agent must be one that actually exists, or the gate silently
  becomes unmeetable;
* the set must stay balanced, or "95%" stops meaning what it meant at acceptance;
* the count must stay at 40, because the FR says 40.

A query may of course be *added* — but these tests will then fail, which is the
point: the gate's baseline has to be re-measured and the file's `status` updated
to say so, rather than the number quietly changing meaning.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from workflow.registry import AGENT_NAMES, MAX_AGENTS_PER_TURN

QUERY_FILE = Path(__file__).resolve().parents[1] / "data" / "router_queries.json"

EXPECTED_TOTAL = 40
PER_AGENT = 5
COMPOUND = 6
EDGE_CASES = 4


@pytest.fixture(scope="module")
def document() -> dict:
    return json.loads(QUERY_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def queries(document) -> list[dict]:
    return document["queries"]


# ── the acceptance record ──────────────────────────────────────────────────────


def test_the_set_records_that_it_was_accepted():
    """The gate is only a gate because a human agreed to it. That has to be
    written down somewhere durable, or in three weeks nobody knows whether the
    labels were reviewed or just generated."""
    about = json.loads(QUERY_FILE.read_text(encoding="utf-8"))["_about"]
    assert "ACCEPTED" in about["status"]
    assert "2026-11-08" in about["status"]


def test_the_baseline_at_acceptance_is_recorded():
    """So a later run can be compared against what was actually agreed, rather
    than against a remembered number."""
    about = json.loads(QUERY_FILE.read_text(encoding="utf-8"))["_about"]
    assert "baseline_at_acceptance" in about
    assert "95" in about["baseline_at_acceptance"]


# ── structure ──────────────────────────────────────────────────────────────────


def test_the_set_has_exactly_forty_queries(queries):
    assert len(queries) == EXPECTED_TOTAL


def test_ids_are_unique(queries):
    ids = [q["id"] for q in queries]
    assert len(set(ids)) == len(ids)


def test_every_query_has_a_label_and_a_reason(queries):
    for item in queries:
        assert item["query"].strip(), f"{item['id']} has an empty query"
        assert item["expected"], f"{item['id']} has no expected route"
        assert len(item.get("why", "")) > 20, f"{item['id']} has no stated reason"


def test_every_expected_agent_exists(queries):
    """The failure this prevents: renaming an agent makes the gate unmeetable,
    because the router can never return a name that is no longer registered."""
    for item in queries:
        for name in item["expected"]:
            assert name in AGENT_NAMES, f"{item['id']} expects unknown agent {name!r}"


def test_every_acceptable_alternative_exists(queries):
    for item in queries:
        for route in item.get("also_acceptable", []):
            for name in route:
                assert name in AGENT_NAMES, f"{item['id']} allows unknown agent {name!r}"


def test_no_expected_route_exceeds_the_cap(queries):
    """A label the router is structurally incapable of producing would be an
    automatic, permanent miss."""
    for item in queries:
        assert len(item["expected"]) <= MAX_AGENTS_PER_TURN, f"{item['id']} exceeds the cap"


def test_no_expected_route_repeats_an_agent(queries):
    """The router collapses duplicates, so a label containing one could never match."""
    for item in queries:
        assert len(set(item["expected"])) == len(item["expected"])


def test_an_alternative_never_duplicates_the_expected_route(queries):
    """A redundant alternative inflates lenient accuracy without adding meaning."""
    for item in queries:
        for route in item.get("also_acceptable", []):
            assert route != item["expected"], f"{item['id']} lists its own label as an alternative"


# ── balance ────────────────────────────────────────────────────────────────────


def test_each_agent_is_the_sole_label_for_five_queries(queries):
    """Balance is what stops the headline number being dominated by one agent.

    A set with twenty finance_qa queries would score well on a router that always
    answered finance_qa, which is exactly the failure mode worth excluding.
    """
    single = Counter(q["expected"][0] for q in queries if len(q["expected"]) == 1)
    for name in AGENT_NAMES:
        assert single[name] >= PER_AGENT, f"{name} has only {single[name]} single-agent queries"


def test_there_are_enough_compound_queries(queries):
    """FR-003 is the hardest thing the router does; it needs real coverage."""
    compound = [q for q in queries if len(q["expected"]) == 2]
    assert len(compound) >= COMPOUND


def test_compound_queries_cover_several_different_pairs(queries):
    """Six copies of portfolio+goal would test one edge six times."""
    pairs = {tuple(q["expected"]) for q in queries if len(q["expected"]) == 2}
    assert len(pairs) >= 4


def test_the_ambiguous_cases_are_marked_as_such(queries):
    """The honest part of the set: where more than one route is defensible, the
    label says so, and lenient accuracy is reported separately so the strict
    number is never quietly inflated."""
    with_alternatives = [q for q in queries if q.get("also_acceptable")]
    assert len(with_alternatives) >= 3


def test_out_of_scope_and_greeting_cases_are_present(queries):
    """FR-002's unknown-intent rule needs something that exercises it."""
    text = " ".join(q["query"].lower() for q in queries)
    assert "capital of france" in text, "an out-of-scope query"
    assert any(q["query"].strip().lower() == "hi" for q in queries), "a no-intent query"


# ── the saved baseline result ──────────────────────────────────────────────────


def test_the_recorded_baseline_run_met_the_gate():
    """The committed result file is the evidence behind the PRD's '95%' claim.

    Without this, the number in the PRD is a sentence someone typed.
    """
    results = QUERY_FILE.parent / "router_eval_results.json"
    if not results.exists():
        pytest.skip("no saved eval run; run scripts/eval_router.py --json")

    data = json.loads(results.read_text(encoding="utf-8"))
    assert data["total"] == EXPECTED_TOTAL
    assert data["strict_accuracy"] >= 0.90
    assert data["lenient_accuracy"] >= data["strict_accuracy"]


def test_the_saved_run_covers_the_same_queries(queries):
    """A stale result file next to an edited query set is worse than no file."""
    results = QUERY_FILE.parent / "router_eval_results.json"
    if not results.exists():
        pytest.skip("no saved eval run")

    saved_ids = {row["id"] for row in json.loads(results.read_text(encoding="utf-8"))["rows"]}
    assert saved_ids == {q["id"] for q in queries}, "re-run the eval; the set has changed"
