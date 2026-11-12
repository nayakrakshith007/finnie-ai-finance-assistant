"""Acceptance tests for the Tax Education Agent (PRD FR-015).

The agent is a specialisation of `FinanceQAAgent`, not a new mechanism: the same
retrieve-then-generate pipeline over the `tax` category, with a prompt that adds
the assessment year and forbids computing anyone's liability. These tests cover
what the specialisation adds — inheriting the Q&A behaviour is already covered by
`test_qa_agent.py`, and re-testing it here would be duplication rather than
assurance.
"""

from __future__ import annotations

from datetime import date

import pytest
from langchain_core.documents import Document

from agents.qa import FinanceQAAgent
from agents.tax import TaxEducationAgent, current_assessment_year, current_financial_year
from core.llm import build_fake_llm
from workflow.state import new_state


class FakeRetriever:
    def __init__(self, docs=None):
        self.docs = docs if docs is not None else [
            Document(
                page_content="LTCG on listed equity is 12.5% above ₹1.25 lakh.",
                metadata={
                    "title": "Capital Gains on Shares",
                    "category": "tax",
                    "section": "Equity",
                    "source": "Income Tax Department",
                    "url": "https://www.incometax.gov.in/",
                    "distance": 0.24,
                },
            )
        ]
        self.calls = []

    def get_relevant_documents(self, query, category=None):
        self.calls.append({"query": query, "category": category})
        return self.docs


def agent(responses=None, docs=None) -> TaxEducationAgent:
    return TaxEducationAgent(
        llm=build_fake_llm(responses or ["LTCG is 12.5% above ₹1.25 lakh."]),
        retriever=FakeRetriever(docs),
    )


# ── the Indian financial year ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("today", "fy", "ay"),
    [
        # The Indian financial year runs 1 April to 31 March. The assessment year
        # is the one after it: income earned in FY 2026-27 is assessed in AY 2027-28.
        (date(2026, 11, 8), "2026-27", "2027-28"),
        (date(2027, 3, 31), "2026-27", "2027-28"),  # last day of the FY
        (date(2027, 4, 1), "2027-28", "2028-29"),  # first day of the next
        (date(2026, 1, 15), "2025-26", "2026-27"),  # January is late in the FY
        (date(2026, 4, 1), "2026-27", "2027-28"),
        (date(2026, 12, 31), "2026-27", "2027-28"),
    ],
)
def test_the_financial_and_assessment_years_are_derived_from_the_date(today, fy, ay):
    """Derived, never hardcoded.

    A hardcoded "AY 2026-27" is correct for five months and wrong for the rest of
    the project's life, and a tax answer stamped with the wrong year is worse than
    one with no year at all.
    """
    assert current_financial_year(today) == fy
    assert current_assessment_year(today) == ay


def test_the_year_helpers_default_to_today():
    assert current_financial_year().count("-") == 1
    assert current_assessment_year().count("-") == 1


def test_the_assessment_year_is_always_one_after_the_financial_year():
    for month in range(1, 13):
        today = date(2026, month, 15)
        fy_start = int(current_financial_year(today).split("-")[0])
        ay_start = int(current_assessment_year(today).split("-")[0])
        assert ay_start == fy_start + 1


# ── identity and specialisation ────────────────────────────────────────────────


def test_agent_declares_name_and_description():
    assert TaxEducationAgent.name == "tax_education"
    assert len(TaxEducationAgent.description) > 40


def test_it_is_a_finance_qa_agent():
    """Specialisation, not duplication: the retrieve-then-generate machinery,
    the empty-context refusal and the error boundary are all inherited."""
    assert issubclass(TaxEducationAgent, FinanceQAAgent)


def test_it_filters_retrieval_to_the_tax_category():
    """The one case where a hard category filter is right: a question about 80C
    has no business retrieving a chapter on technical analysis."""
    retriever = FakeRetriever()
    TaxEducationAgent(llm=build_fake_llm(["x"]), retriever=retriever).run(
        new_state("What is 80C?")
    )
    assert retriever.calls[0]["category"] == "tax"


def test_it_uses_its_own_prompt_not_the_general_one():
    from agents.qa import RAG_SYSTEM_PROMPT

    assert TaxEducationAgent.system_prompt != RAG_SYSTEM_PROMPT


# ── FR-015: the prompt's obligations ───────────────────────────────────────────


def test_the_prompt_states_the_assessment_year():
    assert current_assessment_year() in TaxEducationAgent.system_prompt


def test_the_prompt_frames_computation_as_education():
    """Computation is a worked example, not final tax advice (FR-015).

    The prompt was updated to invite users to share their numbers so the agent
    can walk through the calculation as an educational example with explicit
    caveats — rather than refusing to do maths at all. The test checks that
    the educational framing and caveat requirement are present.
    """
    lowered = TaxEducationAgent.system_prompt.lower()
    assert "worked example" in lowered or "step by step" in lowered
    assert "caveat" in lowered or "note:" in lowered or "does not account" in lowered


def test_the_prompt_names_the_post_2024_capital_gains_rules():
    """The rates changed on 23 July 2024. The old 10%/15% figures are the single
    likeliest thing for a model to recite from memory, so the prompt pins them."""
    prompt = TaxEducationAgent.system_prompt
    assert "12.5" in prompt
    assert "20" in prompt
    assert "1.25" in prompt or "1,25,000" in prompt


def test_the_prompt_covers_the_fr015_topics():
    lowered = TaxEducationAgent.system_prompt.lower()
    for topic in ("80c", "elss", "nps", "indexation", "regime"):
        assert topic in lowered, f"FR-015 names {topic}"


def test_the_prompt_does_not_ask_for_a_disclaimer():
    """Constraint 4: the compliance node appends exactly one."""
    assert "disclaimer" in TaxEducationAgent.system_prompt.lower()
    assert "do not write" in TaxEducationAgent.system_prompt.lower()


# ── behaviour inherited, verified once ─────────────────────────────────────────


def test_it_answers_from_the_knowledge_base():
    update = agent().run(new_state("What is LTCG?"))
    assert "12.5%" in update["messages"][0].content


def test_it_still_refuses_with_no_context():
    from agents.qa import NO_CONTEXT_REPLY

    update = agent(docs=[]).run(new_state("What is the capital of France?"))
    assert update["messages"][0].content == NO_CONTEXT_REPLY


def test_it_records_sources_for_citation():
    update = agent().run(new_state("What is LTCG?"))
    assert update["retrieved_docs"][0]["url"] == "https://www.incometax.gov.in/"


def test_it_does_not_append_the_disclaimer():
    """Constraint 4 again: the year footer is this agent's, the disclaimer is the
    compliance node's, and only one of them belongs here."""
    update = agent(responses=["Plain answer."]).run(new_state("80C?"))
    assert update["messages"][0].content.startswith("Plain answer.")
    assert "not financial advice" not in update["messages"][0].content.lower()


def test_the_assessment_year_is_stated_to_the_user_by_code():
    """FR-015 requires the assessment year to be stated, so it is appended rather
    than requested.

    A tax answer whose year the reader has to guess is unusable — rates changed
    on 23 July 2024, and "12.5%" with no year attached is indistinguishable from
    a half-remembered figure. Prompt rules are requests to the model; this one
    has to be a fact about the output.
    """
    update = agent(responses=["Plain answer."]).run(new_state("80C?"))
    body = update["messages"][0].content

    assert body.startswith("Plain answer.")
    assert current_assessment_year() in body


def test_the_refusal_carries_no_year_footer():
    """"I do not know" needs no assessment year; stamping one on it would imply
    the refusal was itself a tax position."""
    from agents.qa import NO_CONTEXT_REPLY

    update = agent(docs=[]).run(new_state("What is the capital of France?"))
    assert update["messages"][0].content == NO_CONTEXT_REPLY


def test_trace_records_the_assessment_year():
    detail = agent().run(new_state("80C?"))["agent_trace"][0]["detail"]
    assert current_assessment_year() in detail
