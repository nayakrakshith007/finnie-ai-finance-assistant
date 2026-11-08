"""Goal Planning Agent — turns a goal into a monthly number (PRD FR-013).

What it does, in order: find the target amount and the horizon (from state if the
Goals tab supplied them, otherwise from the sentence), look up the return
assumption for the user's risk appetite, inflate the target to the money of the
goal year, solve for the SIP that reaches *that*, and narrate it.

The one thing this agent must never become
------------------------------------------
A forecaster. Every projection here is arithmetic on an assumption that comes
from `config.yaml` — 11% for a moderate profile is a plausible long-run Indian
equity-debt blend, not a claim about the next ten years. So the assumed return
and inflation are stated **in code**, appended to the answer, rather than left to
prompt rule 2: a projection shown without its assumption is indistinguishable
from a prediction, and that is the line compliance turns on.

Why the parsing is a regex and not an LLM call
----------------------------------------------
Same reasoning as the market agent's symbol extraction. "10 lakh in 5 years" is
answerable by a pattern, a pattern is free and instant, and a pattern is
testable: `test_amounts_are_parsed_the_way_indians_write_them` is a table of
eleven cases, which is a stronger guarantee than hoping a model keeps reading
₹5,00,000 as five lakh rather than five hundred.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base import BaseAgent
from core.config import load_config
from core.logging_setup import get_logger
from goals.projections import (
    allocation_template,
    equity_was_capped,
    inflation_adjusted_target,
    projection_series,
    real_return,
    required_monthly_sip,
)
from workflow.state import AgentState

logger = get_logger(__name__)

DEFAULT_RISK = "moderate"

# A horizon beyond this is a typo, not a plan. Rejecting it stops "500 years"
# from producing a ₹0.02 monthly SIP presented with a straight face.
MAX_HORIZON_YEARS = 50

NEED_GOAL_REPLY = (
    "Tell me two things and I can work out the monthly amount: **how much** you "
    "want and **by when**. For example, \"I need 25 lakh in 10 years\" or \"50 "
    "lakh for a house in 7 years\". You can also set them with the sliders in the "
    "Goals tab."
)

NEED_AMOUNT_REPLY = (
    "How much are you aiming for? Give me a figure — \"10 lakh\", \"₹25,00,000\", "
    "\"1 crore\" — and I will work out the monthly SIP for the horizon you gave."
)

NEED_HORIZON_REPLY = (
    "How long do you have? The horizon changes the answer more than anything else, "
    "because it decides how much of the work compounding does rather than you. "
    "Tell me the number of years and I will work out the monthly amount."
)

# Indian scale words. Ordered longest-first so "crore" is matched before any
# shorter token inside it could be.
_SCALES: tuple[tuple[str, float], ...] = (
    (r"crores?|cr\b", 1e7),
    (r"lakhs?|lacs?|lakhs\b", 1e5),
    (r"thousand|k\b", 1e3),
)

# A plain number only counts as an amount when it carries a currency marker, uses
# digit grouping, or is at least four digits long. Without that rule, "in 5
# years" plans for five rupees.
_PLAIN_AMOUNT = re.compile(
    r"(?:(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?))"  # marked: ₹5,00,000 / rs 250000
    r"|(?:\b(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?)\b)"  # grouped: 5,00,000
    r"|(?:\b(\d{4,}(?:\.\d+)?)\b)",  # four digits or more
    re.IGNORECASE,
)

# Years/months, including the "20-year goal" adjectival form.
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:years?|yrs?|y)\b", re.IGNORECASE)
_MONTHS = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:months?|mos?)\b", re.IGNORECASE)

# Units that mean the number before them is a duration, not a sum of money.
_DURATION_SUFFIX = re.compile(r"\s*(?:years?|yrs?|months?|mos?|y)\b", re.IGNORECASE)


def parse_amount(text: str) -> float | None:
    """Pull a rupee amount out of a sentence, Indian notation included.

    Handles lakh/crore/k and the 2-2-3 digit grouping (₹5,00,000). A parser that
    only knows Western thousands-separators reads ₹5,00,000 as 500 and quietly
    plans for five hundred rupees, which is the kind of wrong answer that looks
    like a working feature.

    Known limitation: a bare year such as "by 2036" parses as ₹2,036. The horizon
    parser then finds nothing and the agent asks for a horizon, so the turn
    degrades into a question rather than a wrong plan.
    """
    if not text:
        return None
    lowered = text.lower()

    for pattern, multiplier in _SCALES:
        match = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{pattern})", lowered)
        if match:
            return float(match.group(1)) * multiplier

    for match in _PLAIN_AMOUNT.finditer(lowered):
        raw = next(g for g in match.groups() if g)
        # Skip a number that a duration word follows: "in 5000 months" is a
        # horizon, however implausible, not a target.
        if _DURATION_SUFFIX.match(lowered[match.end() :]):
            continue
        return float(raw.replace(",", ""))
    return None


def parse_horizon_years(text: str) -> float | None:
    """Pull a horizon out of a sentence, in years. Months are converted."""
    if not text:
        return None
    years = _YEARS.search(text)
    if years:
        return float(years.group(1))
    months = _MONTHS.search(text)
    if months:
        return round(float(months.group(1)) / 12, 4)
    return None


GOAL_SYSTEM_PROMPT = """You are Finnie's goal planner, explaining a savings plan \
to a beginner.

Every figure below has already been calculated. Use those numbers exactly as \
given and do no arithmetic of your own.

Rules:
1. These are projections from a stated assumption, NOT predictions. Say so. The \
assumed return is an assumption about a long-run average, and real returns vary \
year to year; a projection is what the arithmetic says *if* the assumption holds. \
Never say the user will have a particular amount, and never guarantee a return.
2. Never invent a number. Every figure in your answer must appear in the data.
3. Lead with the required monthly amount, and make clear it is sized against the \
inflation-adjusted target rather than today's figure. Explain in one sentence why \
₹10 lakh ten years out needs more than ₹10 lakh of saving.
4. The allocation is a commonly used starting template for this horizon and risk \
appetite, not a recommendation of what to hold. Present it that way.
5. The data states whether equity was capped by the horizon. If it was, explain \
that a short horizon leaves no time to recover from a bad run. If the data says \
equity was NOT capped, do not mention capping and do not call the horizon short.
6. Do NOT write a disclaimer or closing caveat. One is appended automatically.
7. Six sentences at most. Plain English. Indian rupee figures in lakh/crore where \
that is clearer.

Goal data:
{data}"""

GOAL_USER_TEMPLATE = "{question}"


class GoalPlanningAgent(BaseAgent):
    """Works out the monthly SIP a goal needs, and what it assumes to get there."""

    name = "goal_planning"
    description = (
        "Works out how much to invest monthly to reach a financial goal: the "
        "required SIP, the inflation-adjusted target, a year-by-year projection "
        "and a starting allocation template. Use this when the user names an "
        "amount and a timeframe — a house deposit, a child's education, "
        "retirement, 'how much should I save for X' — or asks whether their "
        "current saving is enough. Do NOT use it for what an instrument is "
        "(finance Q&A) or for valuing what they already hold (portfolio analysis)."
    )

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        super().__init__(llm=llm)

    # ── the work ──────────────────────────────────────────────────────────────

    def handle(self, state: AgentState) -> dict[str, Any]:
        question = self._question(state)
        existing = dict(state.get("goal_params") or {})

        # Typed values win over state: a follow-up saying "actually make it 50
        # lakh" must override what the sliders were set to last turn.
        target = parse_amount(question) or existing.get("target_amount")
        horizon = parse_horizon_years(question) or existing.get("horizon_years")

        if not target and not horizon:
            logger.info("No goal parameters found; asking for them")
            return {"messages": [AIMessage(content=NEED_GOAL_REPLY)]}
        if not target:
            return {"messages": [AIMessage(content=NEED_AMOUNT_REPLY)]}
        if not horizon:
            return {"messages": [AIMessage(content=NEED_HORIZON_REPLY)]}

        if horizon > MAX_HORIZON_YEARS:
            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"A horizon of {horizon:g} years is longer than I plan for. "
                            f"Give me up to {MAX_HORIZON_YEARS} years and I will work "
                            "out the monthly amount."
                        )
                    )
                ]
            }
        if horizon * 12 < 1:
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "That horizon is under a month, which is too short for a "
                            "SIP to do anything. For a goal that close, the question "
                            "is where to park the money rather than how to grow it."
                        )
                    )
                ]
            }

        cfg = load_config()
        risk = (state.get("user_profile") or {}).get("risk_appetite") or DEFAULT_RISK
        profile = cfg.goals.risk_profiles.get(risk) or cfg.goals.risk_profiles[DEFAULT_RISK]
        rate = profile.expected_return
        inflation = cfg.goals.inflation_rate

        adjusted = inflation_adjusted_target(target, inflation, horizon)
        plan = {
            **existing,
            "target_amount": target,
            "horizon_years": horizon,
            "risk_appetite": risk,
            "assumed_return": rate,
            "assumed_inflation": inflation,
            "real_return": real_return(rate, inflation),
            "inflation_adjusted_target": adjusted,
            # The headline number is sized against the inflated target; the
            # nominal one is kept so the narration can show the gap, which is
            # the lesson rather than a footnote.
            "required_monthly_sip": required_monthly_sip(adjusted, rate, horizon),
            "required_monthly_sip_nominal": required_monthly_sip(target, rate, horizon),
            "allocation": allocation_template(risk, horizon),
            "equity_capped": equity_was_capped(risk, horizon),
            "projection": projection_series(
                required_monthly_sip(adjusted, rate, horizon), rate, horizon
            ),
        }

        messages = [
            SystemMessage(content=GOAL_SYSTEM_PROMPT.format(data=self._for_prompt(plan))),
            HumanMessage(content=GOAL_USER_TEMPLATE.format(question=question)),
        ]
        body = str(self.llm.invoke(messages).content).rstrip()
        body += f"\n\n{self._assumptions_note(plan)}"

        return {"messages": [AIMessage(content=body)], "goal_params": plan}

    def trace_detail(self, update: dict[str, Any]) -> str:
        plan = update.get("goal_params")
        if not plan or "required_monthly_sip" not in plan:
            return "goal parameters incomplete; asked the user for them"
        return (
            f"target {plan['target_amount']:,.0f} over {plan['horizon_years']:g}y, "
            f"{plan['risk_appetite']} at {plan['assumed_return']:.0%}, "
            f"SIP {plan['required_monthly_sip']:,.0f}/mo"
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _question(state: AgentState) -> str:
        """The user's words, or a default when the Goals tab invoked this directly."""
        try:
            return BaseAgent._latest_question(state)
        except ValueError:
            return "Work out what I need to save."

    @staticmethod
    def _assumptions_note(plan: dict[str, Any]) -> str:
        """Stated in code, not requested in the prompt.

        A projection without its assumption reads as a forecast. This is the
        same reasoning as the market agent appending its freshness label: the
        thing that must not be omitted is not left to the model's discretion.
        """
        return (
            f"_Assumes a {plan['assumed_return']:.0%} average annual return "
            f"({plan['risk_appetite']} profile) and {plan['assumed_inflation']:.0%} "
            f"inflation — a real return of {plan['real_return']:.2%}. These are "
            "assumptions for the arithmetic, not predictions; actual returns vary "
            "year to year and may be negative._"
        )

    @staticmethod
    def _for_prompt(plan: dict[str, Any]) -> str:
        """The data block the model sees. Finished numbers, assumptions labelled."""
        final = plan["projection"][-1] if plan["projection"] else None
        lines = [
            f"Target: INR {plan['target_amount']:,.2f} in {plan['horizon_years']:g} years",
            f"Inflation-adjusted target: INR {plan['inflation_adjusted_target']:,.2f} "
            f"(the same purchasing power in {plan['horizon_years']:g} years' time, at "
            f"{plan['assumed_inflation']:.0%} inflation)",
            f"Required monthly SIP: INR {plan['required_monthly_sip']:,.2f} "
            "(sized against the inflation-adjusted target)",
            f"Required monthly SIP if inflation were ignored: INR "
            f"{plan['required_monthly_sip_nominal']:,.2f} — the difference is what "
            "inflation costs this plan",
            f"ASSUMED annual return: {plan['assumed_return']:.0%} "
            f"({plan['risk_appetite']} profile, from configuration) — an assumption, "
            "not a forecast",
            f"Real return after inflation: {plan['real_return']:.2%}",
            "Starting allocation template: "
            + ", ".join(f"{k} {v:.0f}%" for k, v in plan["allocation"].items()),
            # Stated either way, because a conditional prompt rule gets applied
            # unconditionally. Told only "the template caps equity on short
            # horizons", gpt-4o explained a 12-year plan as "equity is capped at
            # 50% because the horizon is relatively short" -- neither half true.
            (
                f"Equity WAS capped below the {plan['risk_appetite']} template "
                "because the horizon is short: explain that there is no time to "
                "recover from a bad run"
                if plan.get("equity_capped")
                else "No horizon constraint applies: this horizon is long enough "
                f"for the full {plan['risk_appetite']} template. Do NOT say the "
                "horizon is short, do NOT say equity was reduced or capped, and "
                "do NOT mention capping at all — the reader does not know what "
                "would have been capped"
            ),
        ]
        if final:
            lines.append(
                f"At year {final['year']}: INR {final['value']:,.2f} total, of which "
                f"INR {final['contributed']:,.2f} contributed and INR "
                f"{final['growth']:,.2f} growth"
            )
        return "\n".join(lines)
