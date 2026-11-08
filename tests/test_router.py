"""Acceptance tests for the supervisor router (PRD FR-002, FR-004).

Offline: the router's LLM is a double returning a canned `RouteDecision`, so
these test the *router's* logic — validation, clamping, fallback, context window
— rather than gpt-4o-mini's judgement. Whether the model classifies correctly is
a different question, measured on the 40-query labelled set by
`scripts/eval_router.py`, which is the FR-002 gate.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from workflow.registry import AGENT_NAMES, DEFAULT_AGENT, MAX_AGENTS_PER_TURN
from workflow.router import RouteDecision, SupervisorRouter
from workflow.state import new_state


class FakeStructuredLLM:
    """Stands in for `llm.with_structured_output(RouteDecision)`."""

    def __init__(self, decision: Any = None, raises: Exception | None = None):
        self.decision = decision
        self.raises = raises
        self.prompts: list[Any] = []

    def invoke(self, messages: Any, *a: Any, **k: Any) -> Any:
        self.prompts.append(messages)
        if self.raises:
            raise self.raises
        return self.decision


def router(decision=None, raises=None) -> SupervisorRouter:
    if decision is None and raises is None:
        decision = RouteDecision(
            agents=["finance_qa"], standalone_question="What is a SIP?", reasoning="conceptual"
        )
    return SupervisorRouter(structured_llm=FakeStructuredLLM(decision, raises))


# ── the decision schema ────────────────────────────────────────────────────────


def test_the_schema_requires_agents_and_a_standalone_question():
    decision = RouteDecision(agents=["market_analysis"], standalone_question="TCS price?")
    assert decision.agents == ["market_analysis"]
    assert decision.standalone_question == "TCS price?"
    assert decision.reasoning == "", "reasoning is optional; it is for the trace, not control flow"


# ── the happy path ─────────────────────────────────────────────────────────────


def test_a_single_agent_route_is_written_to_state():
    update = router().route(new_state("What is a SIP?"))
    assert update["route"] == ["finance_qa"]


def test_the_standalone_question_is_written_to_state():
    update = router().route(new_state("What is a SIP?"))
    assert update["resolved_question"] == "What is a SIP?"


def test_a_two_agent_route_is_preserved_in_order():
    """FR-003: composition. The order is the execution order, so it matters."""
    decision = RouteDecision(
        agents=["portfolio_analysis", "goal_planning"],
        standalone_question="Does my portfolio fit my 10-year goal?",
    )
    update = router(decision).route(new_state("does my portfolio fit my goal?"))
    assert update["route"] == ["portfolio_analysis", "goal_planning"]


def test_the_reasoning_reaches_the_trace():
    decision = RouteDecision(
        agents=["market_analysis"], standalone_question="TCS?", reasoning="names a ticker"
    )
    update = router(decision).route(new_state("TCS?"))
    assert "names a ticker" in update["agent_trace"][0]["detail"]


def test_the_router_appends_exactly_one_trace_entry():
    update = router().route(new_state("What is a SIP?"))
    assert len(update["agent_trace"]) == 1
    assert update["agent_trace"][0]["agent"] == "supervisor"


def test_the_router_does_not_write_a_message():
    """The router decides; it does not answer. A message here would reach the
    user ahead of the agent's real answer."""
    assert "messages" not in router().route(new_state("What is a SIP?"))


# ── validating what the model returned ─────────────────────────────────────────


def test_an_unknown_agent_name_falls_back_to_the_default():
    """Structured output constrains the shape, not the values: a model can still
    return "tax_agent" or a hallucinated name."""
    decision = RouteDecision(agents=["crypto_advisor"], standalone_question="q")
    update = router(decision).route(new_state("q"))
    assert update["route"] == [DEFAULT_AGENT]


def test_a_partially_valid_route_keeps_the_valid_agents():
    decision = RouteDecision(
        agents=["market_analysis", "not_an_agent"], standalone_question="q"
    )
    update = router(decision).route(new_state("q"))
    assert update["route"] == ["market_analysis"]


def test_an_empty_route_falls_back_to_the_default():
    update = router(RouteDecision(agents=[], standalone_question="q")).route(new_state("q"))
    assert update["route"] == [DEFAULT_AGENT]


def test_duplicate_agents_are_collapsed():
    """Running the same agent twice in one turn doubles the cost and the answer."""
    decision = RouteDecision(agents=["finance_qa", "finance_qa"], standalone_question="q")
    update = router(decision).route(new_state("q"))
    assert update["route"] == ["finance_qa"]


def test_the_route_is_capped():
    decision = RouteDecision(agents=list(AGENT_NAMES), standalone_question="q")
    update = router(decision).route(new_state("q"))
    assert len(update["route"]) == MAX_AGENTS_PER_TURN


def test_an_empty_standalone_question_falls_back_to_the_users_words():
    decision = RouteDecision(agents=["finance_qa"], standalone_question="   ")
    update = router(decision).route(new_state("What is a SIP?"))
    assert update["resolved_question"] == "What is a SIP?"


# ── FR-005: the router itself failing ──────────────────────────────────────────


def test_a_router_failure_degrades_to_the_default_agent():
    """A routing outage must not end the turn. Everything Finnie can answer, it
    can answer through the Q&A agent, so that is where a failed route goes."""
    update = router(raises=ConnectionError("openai down")).route(new_state("What is a SIP?"))

    assert update["route"] == [DEFAULT_AGENT]
    assert update["agent_trace"][0]["status"] == "error"
    assert "ConnectionError" in update["agent_trace"][0]["detail"]


def test_a_router_failure_still_sets_a_resolved_question():
    update = router(raises=TimeoutError("slow")).route(new_state("What is a SIP?"))
    assert update["resolved_question"] == "What is a SIP?"


def test_a_router_failure_does_not_raise():
    """A node that raises aborts the whole LangGraph invocation."""
    router(raises=RuntimeError("boom")).route(new_state("q"))  # must not raise


def test_a_none_decision_is_handled():
    """`with_structured_output` can return None when parsing fails."""
    update = router(decision=None).route(new_state("q"))
    assert update["route"] == [DEFAULT_AGENT]


# ── FR-004: conversation context ───────────────────────────────────────────────


def test_the_router_sees_recent_history_not_just_the_last_turn():
    """"What about the second one?" is unroutable without the turn before it."""
    fake = FakeStructuredLLM(
        RouteDecision(agents=["market_analysis"], standalone_question="What is the TCS price?")
    )
    r = SupervisorRouter(structured_llm=fake)

    state = new_state("Compare RELIANCE and TCS")
    state["messages"].append(AIMessage(content="Reliance is 1,324 and TCS is 2,498."))
    state["messages"].append(HumanMessage(content="What about the second one?"))
    r.route(state)

    prompt = " ".join(str(m.content) for m in fake.prompts[0])
    assert "Compare RELIANCE and TCS" in prompt
    assert "What about the second one?" in prompt


def test_history_is_trimmed_to_the_configured_window():
    """Unbounded history is an unbounded prompt, and the router runs every turn."""
    fake = FakeStructuredLLM(RouteDecision(agents=["finance_qa"], standalone_question="q"))
    r = SupervisorRouter(structured_llm=fake)

    state = new_state("turn 0")
    for i in range(1, 40):
        state["messages"].append(AIMessage(content=f"answer {i}"))
        state["messages"].append(HumanMessage(content=f"turn {i}"))
    r.route(state)

    prompt = " ".join(str(m.content) for m in fake.prompts[0])
    assert "turn 39" in prompt
    assert "turn 0" not in prompt, "the oldest turns must fall out of the window"


def test_the_user_profile_is_given_to_the_router():
    """A beginner asking "is this risky?" may route differently from an expert."""
    fake = FakeStructuredLLM(RouteDecision(agents=["finance_qa"], standalone_question="q"))
    r = SupervisorRouter(structured_llm=fake)
    r.route(new_state("is this risky?", profile={"knowledge_level": "beginner"}))

    prompt = " ".join(str(m.content) for m in fake.prompts[0])
    assert "beginner" in prompt


def test_the_catalogue_is_in_the_prompt():
    """The router chooses from the agents' own descriptions, so they must be there."""
    fake = FakeStructuredLLM(RouteDecision(agents=["finance_qa"], standalone_question="q"))
    SupervisorRouter(structured_llm=fake).route(new_state("q"))

    prompt = " ".join(str(m.content) for m in fake.prompts[0])
    for name in AGENT_NAMES:
        assert name in prompt


def test_the_router_handles_a_state_with_no_human_message():
    """The Portfolio tab can invoke the graph from a button."""
    state = new_state("placeholder")
    state["messages"] = []
    update = router().route(state)
    assert update["route"]


# ── the cheap model ────────────────────────────────────────────────────────────


def test_the_router_uses_the_router_model(monkeypatch):
    """FR-002 and the cost argument: routing runs on every single turn, so it runs
    on gpt-4o-mini. Using gpt-4o here would be the most expensive line in the app."""
    captured: list[Any] = []

    class FakeLLM:
        def with_structured_output(self, schema, **kw):
            captured.append(schema)
            return FakeStructuredLLM(RouteDecision(agents=["finance_qa"], standalone_question="q"))

    monkeypatch.setattr("workflow.router.build_router_llm", lambda: FakeLLM())
    SupervisorRouter().route(new_state("q"))
    assert captured == [RouteDecision]


def test_constructing_the_router_builds_no_llm(monkeypatch):
    def explode(*a: Any, **k: Any):
        raise AssertionError("build_router_llm must not run during __init__")

    monkeypatch.setattr("workflow.router.build_router_llm", explode)
    SupervisorRouter()


# ── the registry ───────────────────────────────────────────────────────────────


def test_every_agent_has_a_router_description():
    from workflow.registry import AGENT_CLASSES, agent_catalogue

    catalogue = agent_catalogue()
    for cls in AGENT_CLASSES:
        assert cls.name in catalogue
        assert len(cls.description) > 40, f"{cls.name} needs a usable description"


def test_all_six_agents_are_registered():
    assert len(AGENT_NAMES) == 6
    assert len(set(AGENT_NAMES)) == 6, "names must be unique; they are the routing keys"


def test_building_the_agents_needs_no_api_key_or_index():
    from workflow.registry import build_agents

    agents = build_agents()
    assert set(agents) == set(AGENT_NAMES)


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_each_registered_agent_can_be_looked_up_by_its_routing_name(name):
    from workflow.registry import build_agents

    assert build_agents()[name].name == name
