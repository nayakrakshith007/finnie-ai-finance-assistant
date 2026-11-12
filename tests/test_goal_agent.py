"""Acceptance tests for the Goal Planning Agent (PRD FR-013).

Written before the implementation. Offline: `FakeListChatModel`, no network.

The agent itself does no arithmetic — that is `goals/projections.py`, checked
against longhand closed forms. What is tested here is the parsing of what a user
actually types ("10 lakh in 5 years"), which assumptions it applies, and what it
does when the goal is impossible or the question has no numbers in it.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from agents.goal import NEED_GOAL_REPLY, GoalPlanningAgent, parse_amount, parse_horizon_years
from core.llm import build_fake_llm
from workflow.state import new_state


def agent(responses: list[str] | None = None) -> GoalPlanningAgent:
    return GoalPlanningAgent(llm=build_fake_llm(responses or ["Here is your plan."]))


def state_with(question, profile=None, goal_params=None):
    state = new_state(question, profile=profile)
    if goal_params:
        state["goal_params"] = goal_params
    return state


# ── identity ───────────────────────────────────────────────────────────────────


def test_agent_declares_name_and_description():
    assert GoalPlanningAgent.name == "goal_planning"
    assert len(GoalPlanningAgent.description) > 40


# ── Indian amount notation ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 lakh", 1_000_000.0),
        ("10 lakhs", 1_000_000.0),
        ("2.5 lakh", 250_000.0),
        ("1 crore", 10_000_000.0),
        ("1.5 crore", 15_000_000.0),
        ("50k", 50_000.0),
        ("50 thousand", 50_000.0),
        ("₹5,00,000", 500_000.0),
        ("5,00,000", 500_000.0),
        ("rs 250000", 250_000.0),
        ("₹1,00,00,000", 10_000_000.0),
    ],
)
def test_amounts_are_parsed_the_way_indians_write_them(text, expected):
    """Lakh and crore, and the 2-2-3 digit grouping. A parser that only knows
    thousands-separators reads ₹5,00,000 as 500 and plans for five hundred rupees."""
    assert parse_amount(f"I want {text} saved up") == expected


def test_a_sentence_with_no_amount_yields_none():
    assert parse_amount("I want to retire comfortably") is None


def test_a_bare_year_is_not_mistaken_for_an_amount():
    """"in 5 years" must not parse 5 as the target amount."""
    assert parse_amount("I want to save in 5 years") is None


def test_the_amount_wins_over_the_horizon_in_one_sentence():
    assert parse_amount("I need 10 lakh in 5 years") == 1_000_000.0


# ── horizon ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("in 5 years", 5.0),
        ("in 1 year", 1.0),
        ("over 10 years", 10.0),
        ("in 18 months", 1.5),
        ("in 6 months", 0.5),
        ("within 3 yrs", 3.0),
        ("20-year goal", 20.0),
    ],
)
def test_horizons_are_parsed(text, expected):
    assert parse_horizon_years(f"I need 10 lakh {text}") == expected


def test_a_sentence_with_no_horizon_yields_none():
    assert parse_horizon_years("I need 10 lakh") is None


# ── the happy path ─────────────────────────────────────────────────────────────


def test_plan_is_written_to_state():
    update = agent().run(state_with("I need 10 lakh in 10 years"))
    plan = update["goal_params"]

    assert plan["target_amount"] == 1_000_000.0
    assert plan["horizon_years"] == 10.0
    assert plan["risk_appetite"] == "moderate", "the default when no profile is set"


def test_the_sip_is_calculated_on_the_inflation_adjusted_target():
    """The whole point of FR-013: ₹10 lakh in 2036 money, not today's.

    Sizing the SIP against the nominal target under-saves by the whole of
    inflation, which is the commonest planning error there is.
    """
    plan = agent().run(state_with("I need 10 lakh in 10 years"))["goal_params"]

    assert plan["inflation_adjusted_target"] == 1_790_847.70  # 10L x 1.06^10
    assert plan["required_monthly_sip"] > plan["required_monthly_sip_nominal"]


def test_both_sip_figures_are_reported():
    """Nominal and inflation-adjusted, because the gap is the lesson."""
    plan = agent().run(state_with("I need 10 lakh in 10 years"))["goal_params"]
    assert plan["required_monthly_sip_nominal"] > 0
    assert plan["required_monthly_sip"] > 0


def test_assumptions_are_recorded_not_implied():
    # moderate allocation: equity 50%, debt 35%, gold 10%, cash 5%
    # blended = 0.50*0.12 + 0.35*0.07 + 0.10*0.08 + 0.05*0.04 = 0.0945
    plan = agent().run(state_with("I need 10 lakh in 10 years"))["goal_params"]

    assert plan["assumed_return"] == 0.0945, "moderate blended from allocation"
    assert plan["assumed_inflation"] == 0.06
    assert plan["real_return"] == 0.0325  # round((1.0945/1.06) - 1, 4)


def test_risk_appetite_comes_from_the_user_profile():
    update = agent().run(
        state_with("I need 10 lakh in 10 years", profile={"risk_appetite": "aggressive"})
    )
    plan = update["goal_params"]

    assert plan["risk_appetite"] == "aggressive"
    # aggressive allocation: equity 75%, debt 15%, gold 5%, cash 5%
    # blended = 0.75*0.12 + 0.15*0.07 + 0.05*0.08 + 0.05*0.04 = 0.1065
    assert plan["assumed_return"] == 0.1065, "aggressive blended from allocation"


def test_a_higher_assumed_return_needs_a_smaller_sip():
    """FR-064's acceptance criterion: changing risk appetite changes the output."""
    conservative = agent().run(
        state_with("I need 10 lakh in 10 years", profile={"risk_appetite": "conservative"})
    )["goal_params"]
    aggressive = agent().run(
        state_with("I need 10 lakh in 10 years", profile={"risk_appetite": "aggressive"})
    )["goal_params"]

    assert aggressive["required_monthly_sip"] < conservative["required_monthly_sip"]


def test_the_allocation_template_is_included():
    plan = agent().run(state_with("I need 10 lakh in 10 years"))["goal_params"]
    assert round(sum(plan["allocation"].values()), 2) == 100.0
    assert plan["allocation"]["equity"] == 50.0


def test_a_short_horizon_caps_equity_in_the_plan():
    plan = agent().run(
        state_with("I need 5 lakh in 2 years", profile={"risk_appetite": "aggressive"})
    )["goal_params"]
    assert plan["allocation"]["equity"] <= 10


def test_the_projection_series_is_included_for_the_chart():
    plan = agent().run(state_with("I need 10 lakh in 10 years"))["goal_params"]
    series = plan["projection"]

    assert len(series) == 11  # year 0 plus ten years
    assert series[-1]["growth"] > 0


def test_plan_output_is_json_able():
    import json

    json.dumps(agent().run(state_with("I need 10 lakh in 10 years"))["goal_params"])


def test_an_answer_is_returned_as_an_ai_message():
    update = agent().run(state_with("I need 10 lakh in 10 years"))
    assert isinstance(update["messages"][0], AIMessage)


# ── parameters supplied by the UI rather than typed ───────────────────────────


def test_state_goal_params_are_used_when_present():
    """The Goals tab supplies these from sliders; there may be no sentence to parse."""
    update = agent().run(
        state_with("Work it out", goal_params={"target_amount": 2_500_000, "horizon_years": 15})
    )
    plan = update["goal_params"]
    assert plan["target_amount"] == 2_500_000
    assert plan["horizon_years"] == 15


def test_typed_values_override_stale_state():
    """A follow-up naming new numbers must win over last turn's parameters."""
    update = agent().run(
        state_with(
            "Actually make it 50 lakh in 20 years",
            goal_params={"target_amount": 1_000_000, "horizon_years": 10},
        )
    )
    assert update["goal_params"]["target_amount"] == 5_000_000.0
    assert update["goal_params"]["horizon_years"] == 20.0


# ── missing parameters ─────────────────────────────────────────────────────────


def test_no_amount_asks_for_one_without_calling_the_llm():
    class ExplodingLLM:
        def invoke(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("nothing to plan, nothing to pay for")

    update = GoalPlanningAgent(llm=ExplodingLLM()).run(state_with("Help me plan for retirement"))

    assert update["messages"][0].content == NEED_GOAL_REPLY
    assert update["agent_trace"][0]["status"] == "ok"


def test_an_amount_with_no_horizon_asks_for_the_horizon():
    update = agent().run(state_with("I want 10 lakh"))
    body = update["messages"][0].content
    assert "how long" in body.lower() or "horizon" in body.lower() or "years" in body.lower()


def test_a_horizon_with_no_amount_asks_for_the_amount():
    update = agent().run(state_with("I want to invest for 10 years"))
    assert "how much" in update["messages"][0].content.lower()


# ── guard rails ────────────────────────────────────────────────────────────────


def test_an_absurd_horizon_is_rejected_politely():
    """A typo like '500 years' should not produce a ₹0.02 SIP presented seriously."""
    update = agent().run(state_with("I need 10 lakh in 500 years"))
    assert "horizon" in update["messages"][0].content.lower()


def test_a_sub_monthly_horizon_is_rejected():
    update = agent().run(state_with("I need 10 lakh in 0 years"))
    assert update["messages"][0].content != ""
    assert update["agent_trace"][0]["status"] == "ok", "a bad input is not a crash"


def test_prompt_presents_projections_as_assumptions_not_forecasts():
    from agents.goal import GOAL_SYSTEM_PROMPT

    lowered = GOAL_SYSTEM_PROMPT.lower()
    assert "assumption" in lowered or "assumed" in lowered
    assert "guarantee" in lowered or "not a prediction" in lowered or "predict" in lowered


def test_agent_does_not_append_the_disclaimer():
    update = agent(responses=["Plain answer."]).run(state_with("I need 10 lakh in 10 years"))
    assert update["messages"][0].content.startswith("Plain answer.")
    assert "not financial advice" not in update["messages"][0].content.lower()


def test_the_assumed_return_is_stated_to_the_user_by_code():
    """Not left to the prompt: a projection shown without its assumption is a
    forecast, and that is the one thing this agent must never produce."""
    update = agent(responses=["Plain answer."]).run(state_with("I need 10 lakh in 10 years"))
    body = update["messages"][0].content
    assert "9" in body and "6" in body, "blended return (~9.45%) and inflation (6%) both stated"


# ── trace ──────────────────────────────────────────────────────────────────────


def test_trace_summarises_the_plan():
    detail = agent().run(state_with("I need 10 lakh in 10 years"))["agent_trace"][0]["detail"]
    assert "10" in detail
    assert "moderate" in detail


# ── the error boundary ─────────────────────────────────────────────────────────


def test_a_failure_degrades_instead_of_raising(monkeypatch):
    def explode(*a: Any, **k: Any):
        raise RuntimeError("projection blew up")

    monkeypatch.setattr("agents.goal.required_monthly_sip", explode)
    update = agent().run(state_with("I need 10 lakh in 10 years"))

    assert update["agent_trace"][0]["status"] == "error"
    assert "projection blew up" not in update["messages"][0].content


# ── the prompt must not hand the model numbers to copy (found live 2026-11-08) ─


def test_the_prompt_contains_no_example_amounts():
    """gpt-4o told a user with a ₹1 crore goal that "₹10 lakh today won't have
    the same purchasing power" — it had copied the figures out of the prompt's
    own illustrative example. A rule that demonstrates with numbers invites the
    model to reuse them, so the rule now points at the data instead.
    """
    import re

    from agents.goal import GOAL_SYSTEM_PROMPT

    # The placeholder is the only brace-delimited token that should remain.
    body = GOAL_SYSTEM_PROMPT.replace("{data}", "")
    amounts = re.findall(r"₹\s?[\d,.]+|\b\d+\s*(?:lakh|crore)\b", body, re.IGNORECASE)
    assert amounts == [], f"the prompt offers numbers to copy: {amounts}"


def test_the_prompt_tells_the_model_to_use_only_the_data():
    from agents.goal import GOAL_SYSTEM_PROMPT

    assert "Do not reuse any number that appears in these instructions" in GOAL_SYSTEM_PROMPT
