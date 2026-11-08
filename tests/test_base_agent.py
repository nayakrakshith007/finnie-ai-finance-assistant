"""Acceptance tests for the BaseAgent contract (PRD FR-016).

These are the specification for every agent built in Phases 5-9. Deterministic and
offline: no API key, no network, no real LLM.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.base import FALLBACK_MESSAGE, BaseAgent
from core.llm import build_fake_llm
from workflow.state import AgentState, new_state

# ── fixtures: minimal agents that exercise the contract ────────────────────────


class EchoAgent(BaseAgent):
    name = "echo"
    description = "Repeats the last human message. Test double."

    def handle(self, state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1].content
        return {"messages": [AIMessage(content=f"echo: {last}")]}


class ExplodingAgent(BaseAgent):
    name = "exploding"
    description = "Always raises. Exercises the error boundary."

    def handle(self, state: AgentState) -> dict[str, Any]:
        raise RuntimeError("kaboom")


class DocWritingAgent(BaseAgent):
    name = "doc_writer"
    description = "Writes retrieved_docs. Exercises trace_detail."

    def handle(self, state: AgentState) -> dict[str, Any]:
        return {"retrieved_docs": [{"title": "PPF Explained"}]}

    def trace_detail(self, update: dict[str, Any]) -> str:
        return f"{len(update['retrieved_docs'])} docs retrieved"


# ── subclass contract ──────────────────────────────────────────────────────────


def test_subclass_without_name_is_rejected_at_definition_time():
    with pytest.raises(TypeError, match="must define a non-empty 'name'"):

        class Nameless(BaseAgent):
            description = "has a description but no name"

            def handle(self, state: AgentState) -> dict[str, Any]:
                return {}


def test_subclass_without_description_is_rejected_at_definition_time():
    with pytest.raises(TypeError, match="must define a non-empty 'description'"):

        class Undescribed(BaseAgent):
            name = "undescribed"

            def handle(self, state: AgentState) -> dict[str, Any]:
                return {}


def test_base_agent_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseAgent()  # type: ignore[abstract]


# ── the happy path ─────────────────────────────────────────────────────────────


def test_run_returns_partial_update_with_one_trace_entry():
    update = EchoAgent().run(new_state("what is a SIP?"))

    assert update["messages"][0].content == "echo: what is a SIP?"
    assert len(update["agent_trace"]) == 1, "trace must be a single-element list; the reducer appends"

    entry = update["agent_trace"][0]
    assert entry["agent"] == "echo"
    assert entry["status"] == "ok"
    assert entry["latency_ms"] >= 0


def test_run_does_not_return_the_whole_state():
    update = EchoAgent().run(new_state("hello"))
    # user_profile was in the input state but unchanged, so it must not come back.
    assert "user_profile" not in update
    assert set(update) == {"messages", "agent_trace"}


def test_trace_detail_defaults_to_listing_written_keys():
    update = EchoAgent().run(new_state("hello"))
    assert update["agent_trace"][0]["detail"] == "wrote: messages"


def test_subclass_can_override_trace_detail():
    update = DocWritingAgent().run(new_state("tell me about PPF"))
    assert update["agent_trace"][0]["detail"] == "1 docs retrieved"


# ── the error boundary ─────────────────────────────────────────────────────────


def test_failing_agent_does_not_raise():
    # The whole point: a raising node would abort the entire LangGraph invocation.
    update = ExplodingAgent().run(new_state("anything"))
    assert update is not None


def test_failing_agent_returns_friendly_message_and_sets_error():
    update = ExplodingAgent().run(new_state("anything"))

    assert update["messages"][0].content == FALLBACK_MESSAGE
    assert "kaboom" in update["error"]
    assert update["error"].startswith("exploding:")


def test_failing_agent_message_leaks_no_internals():
    message = ExplodingAgent().run(new_state("anything"))["messages"][0].content
    for leak in ("Traceback", "RuntimeError", "kaboom", "src/", "line "):
        assert leak not in message


def test_failing_agent_records_error_status_in_trace():
    entry = ExplodingAgent().run(new_state("anything"))["agent_trace"][0]

    assert entry["status"] == "error"
    assert entry["agent"] == "exploding"
    assert "RuntimeError" in entry["detail"]


# ── LLM construction ───────────────────────────────────────────────────────────


def test_constructing_an_agent_builds_no_llm(monkeypatch):
    """Agents are built at graph startup and in tests without an API key."""

    def explode(*args, **kwargs):
        raise AssertionError("build_llm must not be called during __init__")

    monkeypatch.setattr("agents.base.build_llm", explode)
    EchoAgent()  # must not raise


def test_injected_llm_is_used_and_not_rebuilt(monkeypatch):
    monkeypatch.setattr(
        "agents.base.build_llm",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not build")),
    )
    fake = build_fake_llm(["a canned answer"])
    agent = EchoAgent(llm=fake)

    assert agent.llm is fake
    assert agent.llm is fake  # cached, still no build


def test_llm_is_built_lazily_on_first_access(monkeypatch):
    calls: list[str | None] = []
    sentinel = build_fake_llm(["x"])

    def fake_build(model=None, **kwargs):
        calls.append(model)
        return sentinel

    monkeypatch.setattr("agents.base.build_llm", fake_build)

    class PinnedModelAgent(EchoAgent):
        name = "pinned"
        description = "Pins a specific model."
        model = "gpt-4o-mini"

    agent = PinnedModelAgent()
    assert calls == []
    assert agent.llm is sentinel
    assert calls == ["gpt-4o-mini"], "the subclass's model must be passed through"
    _ = agent.llm
    assert len(calls) == 1, "built once, then cached"


# ── state helper ───────────────────────────────────────────────────────────────


def test_new_state_seeds_a_human_message_and_empty_trace():
    state = new_state("how much emergency fund do I need?")

    assert isinstance(state["messages"][0], HumanMessage)
    assert state["agent_trace"] == []
    assert state["route"] == []


def test_new_state_carries_the_user_profile():
    state = new_state("question", profile={"risk_appetite": "conservative", "horizon_years": 10})
    assert state["user_profile"]["risk_appetite"] == "conservative"
