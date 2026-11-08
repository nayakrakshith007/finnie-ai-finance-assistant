"""Acceptance tests for the LangGraph workflow (PRD FR-001 to FR-007).

Offline and deterministic: fake agents, a fake router, and no API key. The graph
is built with injected parts so that what is tested is the *wiring* — which node
runs after which, what reaches the user, and what happens when a piece fails.

The compliance node is the reason several of these exist. Until Day 4 the
disclaimer was appended in `app.py`, which meant FR-006's guarantee held only
because the UI happened to be the only caller. Now it is a terminal node, and
`test_no_path_reaches_the_end_without_compliance` is the test that says so.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core.config import load_config
from workflow.graph import COMPLIANCE_NODE, FALLBACK_NODE, build_graph, compliance_node
from workflow.registry import DEFAULT_AGENT
from workflow.state import TraceEntry, new_state

DISCLAIMER_MARK = "not financial advice"


# ── doubles ────────────────────────────────────────────────────────────────────


class FakeAgent:
    """Minimal stand-in: records that it ran, returns a canned answer."""

    def __init__(self, name: str, answer: str = "An answer.", raises: Exception | None = None):
        self.name = name
        self.answer = answer
        self.raises = raises
        self.calls = 0

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.raises:
            # Mimic BaseAgent's error boundary: a real agent never raises.
            return {
                "messages": [AIMessage(content="I ran into a problem working that out.")],
                "error": f"{self.name}: {type(self.raises).__name__}",
                "agent_trace": [
                    TraceEntry(agent=self.name, status="error", latency_ms=1.0, detail="failed")
                ],
            }
        return {
            "messages": [AIMessage(content=self.answer)],
            "agent_trace": [
                TraceEntry(agent=self.name, status="ok", latency_ms=1.0, detail="ran")
            ],
        }


class FakeRouter:
    def __init__(self, route: list[str], resolved: str = ""):
        self.route = route
        self.resolved = resolved
        self.calls = 0

    def route_node(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {
            "route": list(self.route),
            "resolved_question": self.resolved or "resolved",
            "agent_trace": [
                TraceEntry(agent="supervisor", status="ok", latency_ms=1.0, detail="routed")
            ],
        }


def graph_with(route, agents=None, resolved=""):
    """A compiled graph whose router and agents are doubles."""
    names = [
        "finance_qa",
        "market_analysis",
        "portfolio_analysis",
        "goal_planning",
        "news_synthesizer",
        "tax_education",
    ]
    fakes = agents or {n: FakeAgent(n, f"{n} answer") for n in names}
    router = FakeRouter(route, resolved)
    return build_graph(agents=fakes, router=router), fakes, router


def run(route, question="What is a SIP?", agents=None, state=None, resolved=""):
    graph, fakes, router = graph_with(route, agents, resolved)
    result = graph.invoke(state or new_state(question))
    return result, fakes, router


# ── FR-002: routing ────────────────────────────────────────────────────────────


def test_the_router_runs_first():
    _, _, router = run(["finance_qa"])
    assert router.calls == 1


def test_the_routed_agent_runs():
    _, fakes, _ = run(["market_analysis"])
    assert fakes["market_analysis"].calls == 1


def test_agents_not_on_the_route_do_not_run():
    _, fakes, _ = run(["market_analysis"])
    for name, agent in fakes.items():
        if name != "market_analysis":
            assert agent.calls == 0, f"{name} ran but was not routed"


def test_the_agents_answer_reaches_the_user():
    result, _, _ = run(["market_analysis"])
    assert "market_analysis answer" in result["messages"][-1].content


# ── FR-003: composition ────────────────────────────────────────────────────────


def test_a_two_agent_route_runs_both_in_order():
    """The FR-003 acceptance criterion: a two-agent chain inside one turn."""
    result, fakes, _ = run(["portfolio_analysis", "goal_planning"])

    assert fakes["portfolio_analysis"].calls == 1
    assert fakes["goal_planning"].calls == 1

    ran = [t["agent"] for t in result["agent_trace"]]
    assert ran == ["supervisor", "portfolio_analysis", "goal_planning", COMPLIANCE_NODE]


def test_state_hands_off_between_composed_agents():
    """The second agent must see what the first wrote."""
    seen: list[Any] = []

    class Watcher(FakeAgent):
        def run(self, state):
            seen.append(list(state.get("messages", [])))
            return super().run(state)

    agents = {
        "portfolio_analysis": FakeAgent("portfolio_analysis", "portfolio says 4 lakh"),
        "goal_planning": Watcher("goal_planning", "goal says 5000/mo"),
    }
    run(["portfolio_analysis", "goal_planning"], agents=agents)

    second_agents_view = " ".join(str(m.content) for m in seen[0])
    assert "portfolio says 4 lakh" in second_agents_view


def test_each_composed_agent_runs_exactly_once():
    """The next-node decision is derived from the trace, so an agent that has
    already run cannot be chosen again — this is what stops a routing loop."""
    result, fakes, _ = run(["portfolio_analysis", "goal_planning"])
    assert fakes["portfolio_analysis"].calls == 1
    assert fakes["goal_planning"].calls == 1


def test_one_turn_produces_exactly_one_answer():
    """Two agents, one question, one reply.

    Found live on 2026-11-08: a composed turn left two AI messages in state, and
    every consumer that reads "the answer" as `messages[-1]` — the Streamlit app,
    the MCP server, these tests — silently dropped the first agent's work. The
    portfolio analysis was computed, wrapped in nothing, and thrown away.

    The compliance node now merges the turn's answers before wrapping, so "one
    turn, one answer" is true for every consumer rather than something each one
    has to reassemble.
    """
    result, _, _ = run(["portfolio_analysis", "goal_planning"])
    answers = [m for m in result["messages"] if isinstance(m, AIMessage)]
    assert len(answers) == 1


def test_a_merged_answer_keeps_both_agents_contributions():
    result, _, _ = run(["portfolio_analysis", "goal_planning"])
    body = result["messages"][-1].content
    assert "portfolio_analysis answer" in body
    assert "goal_planning answer" in body


def test_both_answers_are_kept_in_the_transcript():
    result, _, _ = run(["portfolio_analysis", "goal_planning"])
    transcript = " ".join(str(m.content) for m in result["messages"])
    assert "portfolio_analysis answer" in transcript
    assert "goal_planning answer" in transcript


# ── FR-006: compliance is terminal and unskippable ─────────────────────────────


def test_every_answer_carries_the_disclaimer():
    result, _, _ = run(["finance_qa"])
    assert DISCLAIMER_MARK in result["messages"][-1].content.lower()


@pytest.mark.parametrize(
    "route",
    [
        ["finance_qa"],
        ["market_analysis"],
        ["portfolio_analysis", "goal_planning"],
        ["tax_education"],
        ["news_synthesizer"],
    ],
)
def test_no_path_reaches_the_end_without_compliance(route):
    """FR-006: no response can reach the UI without passing the guard.

    This is the test that makes the guarantee structural rather than a habit.
    Before Day 4 the disclaimer was appended in `app.py`, so the guarantee held
    only while the UI was the single caller — the MCP server would have bypassed
    it entirely (PRD section 7.5 / D1).
    """
    result, _, _ = run(route)

    assert DISCLAIMER_MARK in result["messages"][-1].content.lower()
    assert result["agent_trace"][-1]["agent"] == COMPLIANCE_NODE


def test_compliance_runs_once_even_for_a_composed_turn():
    """Two agents, one disclaimer. The node is terminal, not per-agent."""
    result, _, _ = run(["portfolio_analysis", "goal_planning"])
    body = result["messages"][-1].content.lower()
    assert body.count(DISCLAIMER_MARK) == 1


def test_the_merged_answer_carries_exactly_one_disclaimer():
    """One per turn, not one per agent — the merge happens before the wrap."""
    result, _, _ = run(["portfolio_analysis", "goal_planning"])
    bodies = [m.content.lower() for m in result["messages"] if isinstance(m, AIMessage)]
    assert sum(b.count(DISCLAIMER_MARK) for b in bodies) == 1


def test_a_banned_phrase_is_blocked_and_replaced():
    cfg = load_config()
    banned = cfg.compliance.banned_phrases[0]
    agents = {"finance_qa": FakeAgent("finance_qa", f"Honestly, {banned} TCS today.")}

    result, _, _ = run(["finance_qa"], agents=agents)
    body = result["messages"][-1].content.lower()

    assert banned.lower() not in body, "the banned phrase must not reach the user"
    assert DISCLAIMER_MARK in body


def test_a_blocked_response_is_recorded_in_the_trace():
    cfg = load_config()
    agents = {"finance_qa": FakeAgent("finance_qa", f"I think {cfg.compliance.banned_phrases[0]}.")}
    result, _, _ = run(["finance_qa"], agents=agents)

    compliance_entry = result["agent_trace"][-1]
    assert compliance_entry["agent"] == COMPLIANCE_NODE
    assert compliance_entry["status"] == "error"
    assert "blocked" in compliance_entry["detail"].lower()


def test_the_blocked_message_does_not_quote_the_banned_phrase_back():
    """An error message containing the phrase would defeat the point."""
    cfg = load_config()
    banned = cfg.compliance.banned_phrases[0]
    agents = {"finance_qa": FakeAgent("finance_qa", f"{banned} right now.")}
    result, _, _ = run(["finance_qa"], agents=agents)
    assert banned.lower() not in result["messages"][-1].content.lower()


# ── the compliance node in isolation ───────────────────────────────────────────


def test_compliance_node_is_idempotent():
    """Running it twice must not append two disclaimers.

    It strips any trailing disclaimer-shaped paragraph before appending, which is
    the fix for the double-disclaimer defect of 2026-11-08 — found live, because
    the model paraphrased the disclaimer and an exact-match check missed it.
    """
    state = new_state("q")
    state["messages"].append(AIMessage(content="An answer.", id="a1"))

    first = compliance_node(state)
    state["messages"] = [state["messages"][0], first["messages"][0]]
    second = compliance_node(state)

    assert second["messages"][0].content.lower().count(DISCLAIMER_MARK) == 1


def test_compliance_node_replaces_rather_than_appends():
    """It returns a message with the same id, so `add_messages` replaces it.

    Appending would leave the unwrapped answer in the transcript above the
    wrapped one, and the UI renders every message.
    """
    state = new_state("q")
    state["messages"].append(AIMessage(content="An answer.", id="abc"))
    update = compliance_node(state)
    assert update["messages"][0].id == "abc"


def test_compliance_node_with_no_answer_produces_a_fallback():
    """FR-005: a turn that produced nothing must still say something."""
    update = compliance_node(new_state("q"))
    assert update["messages"][0].content
    assert DISCLAIMER_MARK in update["messages"][0].content.lower()


def test_compliance_node_never_raises():
    """A raising node aborts the whole invocation, so even a broken guard must
    return something."""
    state = new_state("q")
    state["messages"].append(AIMessage(content="x" * 50_000, id="big"))
    compliance_node(state)  # must not raise


def test_compliance_node_ignores_a_trailing_human_message():
    """If the last message is the user's, there is no answer to wrap yet."""
    state = new_state("q")
    state["messages"].append(AIMessage(content="An answer.", id="a"))
    state["messages"].append(HumanMessage(content="follow-up"))
    update = compliance_node(state)
    assert DISCLAIMER_MARK in update["messages"][0].content.lower()


# ── FR-005: fallback ───────────────────────────────────────────────────────────


def test_an_agent_error_still_yields_a_compliant_answer():
    agents = {"finance_qa": FakeAgent("finance_qa", raises=ConnectionError("chroma down"))}
    result, _, _ = run(["finance_qa"], agents=agents)

    body = result["messages"][-1].content
    assert DISCLAIMER_MARK in body.lower()
    assert "chroma" not in body.lower(), "no internals reach the user"
    assert result["error"]


def test_an_empty_route_reaches_the_fallback_node():
    """The router guarantees a non-empty route, so this is defence in depth — the
    graph must not deadlock if that guarantee ever breaks."""
    result, _, _ = run([])

    ran = [t["agent"] for t in result["agent_trace"]]
    assert FALLBACK_NODE in ran
    assert DISCLAIMER_MARK in result["messages"][-1].content.lower()


def test_an_unknown_agent_in_the_route_does_not_deadlock():
    result, _, _ = run(["no_such_agent"])
    assert result["messages"][-1].content
    assert DISCLAIMER_MARK in result["messages"][-1].content.lower()


# ── FR-004: memory ─────────────────────────────────────────────────────────────


def test_the_conversation_accumulates_across_turns():
    graph, _, _ = graph_with(["finance_qa"])

    state = graph.invoke(new_state("First question"))
    state["messages"].append(HumanMessage(content="Second question"))
    state = graph.invoke(state)

    texts = [str(m.content) for m in state["messages"]]
    assert "First question" in texts
    assert "Second question" in texts


def test_a_five_turn_conversation_keeps_every_turn():
    """FR-004's acceptance criterion: a 5-turn test passes."""
    graph, _, _ = graph_with(["finance_qa"])
    state = new_state("turn 1")
    for turn in range(2, 6):
        state = graph.invoke(state)
        state["messages"].append(HumanMessage(content=f"turn {turn}"))

    human = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    assert len(human) == 5


def test_the_user_profile_survives_the_turn():
    graph, _, _ = graph_with(["finance_qa"])
    result = graph.invoke(new_state("q", profile={"risk_appetite": "aggressive"}))
    assert result["user_profile"]["risk_appetite"] == "aggressive"


def test_the_resolved_question_reaches_the_agent():
    """The supervisor's rewrite is what makes follow-ups work for every agent."""
    seen: list[str] = []

    class Watcher(FakeAgent):
        def run(self, state):
            seen.append(state.get("resolved_question", ""))
            return super().run(state)

    agents = {"finance_qa": Watcher("finance_qa")}
    run(["finance_qa"], agents=agents, resolved="What is the TCS price?")
    assert seen == ["What is the TCS price?"]


# ── FR-007: the trace ──────────────────────────────────────────────────────────


def test_the_trace_records_the_whole_path_in_order():
    result, _, _ = run(["market_analysis"])
    assert [t["agent"] for t in result["agent_trace"]] == [
        "supervisor",
        "market_analysis",
        COMPLIANCE_NODE,
    ]


def test_every_trace_entry_has_the_four_declared_fields():
    result, _, _ = run(["portfolio_analysis", "goal_planning"])
    for entry in result["agent_trace"]:
        assert set(entry) >= {"agent", "status", "latency_ms", "detail"}
        assert isinstance(entry["latency_ms"], (int, float))


def test_the_trace_is_json_able():
    """It is rendered in a UI expander and written to the log (FR-007)."""
    import json

    result, _, _ = run(["finance_qa"])
    json.dumps(result["agent_trace"])


# ── the real graph compiles ────────────────────────────────────────────────────


def test_the_production_graph_compiles_without_an_api_key():
    """Every agent is lazy, so building the real graph touches no network. If this
    breaks, the Streamlit app cannot start and neither can the tests."""
    graph = build_graph()
    assert graph is not None


def test_the_production_graph_has_a_node_per_agent_plus_the_machinery():
    from workflow.registry import AGENT_NAMES

    nodes = set(build_graph().get_graph().nodes)
    for name in AGENT_NAMES:
        assert name in nodes, f"{name} has no node"
    assert {"supervisor", COMPLIANCE_NODE, FALLBACK_NODE} <= nodes


def test_the_graph_can_be_drawn_as_mermaid():
    """Day 6 needs a diagram in DESIGN.md, and a drawable graph is also the
    evidence that the wiring is a real state machine rather than a call chain."""
    mermaid = build_graph().get_graph().draw_mermaid()
    assert "supervisor" in mermaid
    assert COMPLIANCE_NODE in mermaid


def test_the_default_agent_is_registered():
    assert DEFAULT_AGENT in set(build_graph().get_graph().nodes)


# ── D1: the UI must not apply compliance itself ───────────────────────────────


def test_the_streamlit_app_does_not_call_the_compliance_guard():
    """PRD section 7.5 / D1, made structural rather than a one-time cleanup.

    `check_and_wrap` lives in the terminal graph node now. If a future change
    calls it in the UI as well, every answer gets two disclaimers — the exact
    defect found live on 2026-11-08 — and the guarantee goes back to depending on
    each caller remembering. The docstring mentioning the move is allowed; a call
    is not.
    """
    for path, code in _ui_sources():
        assert "check_and_wrap(" not in code, f"{path.name} must not apply compliance itself"
        assert "from core.compliance import" not in code, f"{path.name} imports the guard"


def test_the_ui_goes_through_the_graph():
    """The other half of D1: the UI must use the workflow, not the raw RAG chain.

    Calling `build_rag_chain()` directly would skip the router, every agent but
    one, and the compliance node. Exactly one place in the UI may build the
    graph — `web_app/session.py` — so there is one cached instance and one way
    for a tab to ask a question.
    """

    builders = [path.name for path, code in _ui_sources() if "build_production_graph" in code]
    assert builders == ["session.py"], f"the graph is built in {builders}"

    for path, code in _ui_sources():
        assert "build_rag_chain" not in code, f"{path.name} bypasses the graph"


def test_every_tab_asks_through_the_one_shared_helper():
    """Four tabs assembling their own state updates would be four chances to
    forget to clear last turn's market data or to drop the profile — and the bug
    would show in one tab only, which is the hardest kind to notice."""
    from pathlib import Path

    tabs = Path(__file__).resolve().parents[1] / "src" / "web_app" / "tabs"
    for path in tabs.glob("*.py"):
        code = path.read_text(encoding="utf-8")
        if ".invoke(" in code:
            raise AssertionError(f"{path.name} invokes the graph directly; use session.run_turn")


def _ui_sources() -> list[tuple[object, str]]:
    """Every file in the UI layer, with comment lines and docstring prose dropped.

    The UI is no longer one file: `app.py` is a shell and the work is in
    `src/web_app/`. A guard that checks only `app.py` would pass while a tab
    quietly applied the disclaimer a second time.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    paths = [root / "app.py", *sorted((root / "src" / "web_app").rglob("*.py"))]

    sources = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lines = [
            line
            for line in text.splitlines()
            # Crude but sufficient: drop comments and sentence-shaped prose lines.
            if not line.lstrip().startswith("#") and not re.match(r"^\s{0,8}\S.*\.$", line)
        ]
        sources.append((path, "\n".join(lines)))
    return sources
