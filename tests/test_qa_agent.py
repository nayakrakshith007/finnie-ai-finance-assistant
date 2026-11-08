"""Acceptance tests for the Finance Q&A Agent (PRD FR-010).

Specification, not description: these were written before the implementation.
Deterministic and offline — a fake retriever and `FakeListChatModel`, no API key.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from agents.qa import NO_CONTEXT_REPLY, FinanceQAAgent
from core.llm import build_fake_llm
from workflow.state import new_state

# ── test doubles ───────────────────────────────────────────────────────────────


class FakeRetriever:
    """Returns canned documents and records how it was called."""

    def __init__(self, docs: list[Document] | None = None) -> None:
        self.docs = docs if docs is not None else []
        self.calls: list[dict[str, Any]] = []

    def get_relevant_documents(self, query: str, category: str | None = None) -> list[Document]:
        self.calls.append({"query": query, "category": category})
        return self.docs


def doc(title: str, distance: float, category: str = "tax", text: str = "body text") -> Document:
    return Document(
        page_content=text,
        metadata={
            "title": title,
            "category": category,
            "section": "A section",
            "source": "Income Tax Department",
            "url": "https://www.incometax.gov.in/",
            "distance": distance,
        },
    )


def agent_with(docs: list[Document], responses: list[str] | None = None) -> FinanceQAAgent:
    return FinanceQAAgent(
        llm=build_fake_llm(responses or ["A grounded answer about LTCG."]),
        retriever=FakeRetriever(docs),
    )


# ── identity ───────────────────────────────────────────────────────────────────


def test_agent_declares_name_and_description():
    assert FinanceQAAgent.name == "finance_qa"
    # The description is router prompt text, so it must actually describe routing.
    assert len(FinanceQAAgent.description) > 40


# ── the happy path ─────────────────────────────────────────────────────────────


def test_answers_from_the_last_human_message():
    retriever = FakeRetriever([doc("LTCG Explained", 0.31)])
    agent = FinanceQAAgent(llm=build_fake_llm(["LTCG is 12.5% above ₹1.25 lakh."]), retriever=retriever)

    update = agent.run(new_state("What is LTCG?"))

    assert retriever.calls[0]["query"] == "What is LTCG?"
    assert isinstance(update["messages"][0], AIMessage)
    assert "12.5%" in update["messages"][0].content


def test_retrieved_docs_are_written_to_state():
    update = agent_with([doc("LTCG Explained", 0.31), doc("STCG Explained", 0.44)]).run(
        new_state("tax on shares?")
    )

    docs = update["retrieved_docs"]
    assert len(docs) == 2
    assert docs[0]["title"] == "LTCG Explained"
    assert docs[0]["url"] == "https://www.incometax.gov.in/"
    assert docs[0]["distance"] == 0.31


def test_sources_carry_the_fields_a_citation_needs():
    update = agent_with([doc("PPF Explained", 0.22, category="fixed-income")]).run(new_state("ppf?"))
    source = update["retrieved_docs"][0]
    for field in ("title", "section", "category", "source", "url", "distance"):
        assert field in source, f"citation needs {field}"


def test_uses_the_most_recent_question_in_a_multi_turn_state():
    retriever = FakeRetriever([doc("ELSS", 0.3)])
    agent = FinanceQAAgent(llm=build_fake_llm(["About ELSS."]), retriever=retriever)

    state = new_state("What is PPF?")
    state["messages"].append(AIMessage(content="PPF is a 15-year scheme."))
    state["messages"].append(HumanMessage(content="And ELSS?"))

    agent.run(state)
    assert retriever.calls[0]["query"] == "And ELSS?"


# ── the empty-context path ─────────────────────────────────────────────────────


def test_refuses_when_nothing_is_retrieved():
    update = agent_with([]).run(new_state("What is the capital of France?"))
    assert update["messages"][0].content == NO_CONTEXT_REPLY


def test_refusal_does_not_call_the_llm():
    """Paying gpt-4o to answer from empty context is both wrong and billable."""

    class ExplodingLLM:
        def invoke(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("the LLM must not be called with no context")

    agent = FinanceQAAgent(llm=ExplodingLLM(), retriever=FakeRetriever([]))
    update = agent.run(new_state("something off-topic"))

    assert update["messages"][0].content == NO_CONTEXT_REPLY
    assert update["agent_trace"][0]["status"] == "ok", "a refusal is correct behaviour, not an error"


def test_refusal_still_records_empty_retrieved_docs():
    update = agent_with([]).run(new_state("off topic"))
    assert update["retrieved_docs"] == []


# ── trace ──────────────────────────────────────────────────────────────────────


def test_trace_reports_document_count_and_best_distance():
    update = agent_with([doc("A", 0.21), doc("B", 0.55)]).run(new_state("q"))
    detail = update["agent_trace"][0]["detail"]
    assert "2" in detail
    assert "0.21" in detail


def test_trace_says_so_when_nothing_was_retrieved():
    detail = agent_with([]).run(new_state("q"))["agent_trace"][0]["detail"]
    assert "no" in detail.lower()


# ── the error boundary, inherited from BaseAgent ───────────────────────────────


def test_retriever_failure_degrades_instead_of_raising():
    class BrokenRetriever:
        def get_relevant_documents(self, *args: Any, **kwargs: Any) -> list[Document]:
            raise ConnectionError("chroma is down")

    update = FinanceQAAgent(llm=build_fake_llm(["x"]), retriever=BrokenRetriever()).run(
        new_state("anything")
    )

    assert update["agent_trace"][0]["status"] == "error"
    assert "ConnectionError" in update["error"]
    assert "chroma" not in update["messages"][0].content.lower(), "no internals leak to the user"


# ── compliance belongs to the graph, not here ──────────────────────────────────


def test_agent_does_not_append_the_disclaimer():
    """The compliance node is terminal and runs once (PRD FR-006).

    Applying it here too would double-inject it — the exact defect found on
    2026-11-08 when the prompt and the guard both added one.
    """
    update = agent_with([doc("A", 0.3)], responses=["Plain answer."]).run(new_state("q"))
    assert update["messages"][0].content == "Plain answer."


# ── laziness ───────────────────────────────────────────────────────────────────


def test_constructing_the_agent_builds_no_retriever(monkeypatch):
    def explode(*args: Any, **kwargs: Any):
        raise AssertionError("build_retriever must not run during __init__")

    monkeypatch.setattr("agents.qa.build_retriever", explode)
    FinanceQAAgent()  # must not raise


@pytest.mark.parametrize("category", [None, "tax"])
def test_category_filter_is_passed_through(category):
    retriever = FakeRetriever([doc("A", 0.3)])
    agent = FinanceQAAgent(llm=build_fake_llm(["ok"]), retriever=retriever, category=category)
    agent.run(new_state("q"))
    assert retriever.calls[0]["category"] == category
