"""Goal planning maths — pure functions, no I/O, no LLM (PRD FR-013).

Same discipline as `portfolio/metrics.py`, for the same reason: a user decides
how much to save every month based on these numbers. Every one is checked in
`tests/test_goal_projections.py` against the closed form evaluated longhand.

The monthly rate convention
---------------------------
`i = annual / 12`, simple division. The mathematically tidier choice is the
effective monthly rate, `(1 + annual)^(1/12) - 1`, which is slightly smaller and
gives a slightly lower projection. Finnie uses simple division because every SIP
calculator an Indian user has already seen does — AMFI's, Groww's, Zerodha's — and
a figure that disagrees with the calculator on their broker's site reads as a bug
in Finnie, not as a more rigorous model. The convention is pinned by a test.

Contributions are modelled as an **annuity due**: invested at the start of each
month, because a SIP mandate debits on a chosen date and buys units at that day's
NAV. On one year of a ₹10,000 SIP that is worth ₹1,268 against the end-of-month
form — about 1%, which matters over twenty years.

Returns are assumptions, not forecasts
--------------------------------------
Every rate here comes from `config.yaml: goals.risk_profiles` and is a *stated
assumption*. Nothing in this module predicts a return, and the agent above it is
instructed to present projections as arithmetic on an assumption rather than as
an expectation. An 11% moderate return is a plausible long-run Indian equity-debt
blend; it is not what the next ten years will do.
"""

from __future__ import annotations

from typing import Any

MONTHS_PER_YEAR = 12

# Exposure classes for an allocation template. A different taxonomy from
# `portfolio.holdings.ASSET_CLASSES`, which names *instruments*: an equity mutual
# fund is instrument `mutual_fund` and exposure `equity`. Keeping them separate is
# what lets the Goal agent say "you hold 46% equity exposure" about a portfolio
# made entirely of funds.
ALLOCATION_CLASSES: tuple[str, ...] = ("equity", "debt", "gold", "cash")

# The bridge between the two taxonomies, used when the graph composes the
# Portfolio and Goal agents in one turn (FR-003). Every instrument class the
# portfolio agent accepts must appear here.
#
# `mutual_fund` and `etf` map to equity as the common case — most Indian retail
# SIPs are into equity funds and most retail ETFs track an equity index. It is an
# approximation, and the honest consequence is that a debt-fund-heavy portfolio
# reads as more equity-exposed than it is. Fixing that properly needs per-fund
# category data, which is a data problem rather than a maths one.
EXPOSURE_MAP: dict[str, str] = {
    "stock": "equity",
    "etf": "equity",
    "mutual_fund": "equity",
    "bond": "debt",
    "cash": "cash",
    "crypto": "equity",  # not equity in nature, but it is the risk bucket it belongs in
}

# Long-horizon templates by risk appetite. The keys match
# `UserProfile.risk_appetite` and `config.yaml: goals.risk_profiles`.
DEFAULT_ALLOCATIONS: dict[str, dict[str, float]] = {
    "conservative": {"equity": 20.0, "debt": 60.0, "gold": 10.0, "cash": 10.0},
    "moderate": {"equity": 50.0, "debt": 35.0, "gold": 10.0, "cash": 5.0},
    "aggressive": {"equity": 75.0, "debt": 15.0, "gold": 5.0, "cash": 5.0},
}

FALLBACK_RISK = "moderate"

# Horizon ceilings on equity. The one place the template overrides a stated risk
# appetite, because equity needs time and an appetite does not create any: over
# two years, sequence-of-returns risk dominates expected return. Under 3 years
# this is close to the standard advice to keep short-term goals out of equity
# entirely.
EQUITY_CAPS: tuple[tuple[int, float], ...] = ((3, 10.0), (5, 40.0))


# ── compounding ────────────────────────────────────────────────────────────────


def _check_years(years: float) -> None:
    if years < 0:
        raise ValueError("years cannot be negative")


def future_value_lumpsum(present_value: float, annual_rate: float, years: float) -> float:
    """FV = PV x (1 + r)^n, compounded annually."""
    _check_years(years)
    return round(present_value * (1 + annual_rate) ** years, 2)


def sip_future_value(monthly: float, annual_rate: float, years: float) -> float:
    """Future value of a monthly SIP, as an annuity due.

        FV = P x [((1 + i)^n - 1) / i] x (1 + i),  i = annual/12, n = years x 12

    The trailing `(1 + i)` is the annuity-due adjustment: each contribution earns
    one extra month. At a zero rate the formula degenerates, so that case returns
    the contributions themselves rather than dividing by zero.
    """
    _check_years(years)
    months = int(round(years * MONTHS_PER_YEAR))
    if months == 0:
        return 0.0
    if not annual_rate:
        return round(monthly * months, 2)

    i = annual_rate / MONTHS_PER_YEAR
    return round(monthly * (((1 + i) ** months - 1) / i) * (1 + i), 2)


def required_monthly_sip(target: float, annual_rate: float, years: float) -> float:
    """The SIP that lands on `target`: the inverse of `sip_future_value`.

    `test_required_sip_round_trips_through_the_forward_formula` checks the pair
    against each other rather than against one expected value, which is what
    catches an inverted formula that still looks plausible.
    """
    _check_years(years)
    months = int(round(years * MONTHS_PER_YEAR))
    if months == 0:
        raise ValueError("a goal needs a horizon of at least one month")
    if target <= 0:
        return 0.0
    if not annual_rate:
        return round(target / months, 2)

    i = annual_rate / MONTHS_PER_YEAR
    factor = (((1 + i) ** months - 1) / i) * (1 + i)
    return round(target / factor, 2)


def years_to_target(monthly: float, annual_rate: float, target: float) -> float | None:
    """How long a given SIP takes to reach a target, or None if it never does.

    None rather than infinity for a zero contribution: "never" is the honest
    answer and `inf` would propagate into the narration as a number.
    """
    if monthly <= 0 or target <= 0:
        return None
    if not annual_rate:
        return round(target / (monthly * MONTHS_PER_YEAR), 1)

    from math import log

    i = annual_rate / MONTHS_PER_YEAR
    # Invert FV = P x [((1+i)^n - 1)/i] x (1+i) for n.
    months = log(1 + target * i / (monthly * (1 + i))) / log(1 + i)
    return round(months / MONTHS_PER_YEAR, 1)


# ── inflation ──────────────────────────────────────────────────────────────────


def inflation_adjusted_target(target: float, inflation_rate: float, years: float) -> float:
    """What today's `target` must become to buy the same thing in `years`.

    The single biggest error a beginner makes here: planning for ₹10 lakh in ten
    years when ₹10 lakh of today's money is ₹17.9 lakh of 2036 money at 6%.
    Under-saving by 79% because the number looked big enough.
    """
    _check_years(years)
    return round(target * (1 + inflation_rate) ** years, 2)


def real_return(nominal_rate: float, inflation_rate: float) -> float:
    """The Fisher relation: (1 + nominal) / (1 + inflation) - 1.

    Not `nominal - inflation`. The difference is small at Indian inflation and
    large at high inflation, and the exact form is what an interviewer asks for.
    12% nominal at 6% inflation is 5.66% real, not 6%.
    """
    return round((1 + nominal_rate) / (1 + inflation_rate) - 1, 4)


# ── the projection series ──────────────────────────────────────────────────────


def projection_series(monthly: float, annual_rate: float, years: float) -> list[dict[str, Any]]:
    """Year-by-year balances for the goal projection chart (FR-063).

    Each point splits the balance into what was contributed and what was growth.
    That split is the most useful thing a beginner can see here: at year 3 of a
    ₹10,000 SIP at 12%, ₹75,076 of the ₹4,35,076 was never theirs to begin with,
    and the gap widens visibly over a long horizon.
    """
    _check_years(years)
    points: list[dict[str, Any]] = [
        {"year": 0, "value": 0.0, "contributed": 0.0, "growth": 0.0}
    ]
    for year in range(1, int(years) + 1):
        value = sip_future_value(monthly, annual_rate, year)
        contributed = round(monthly * MONTHS_PER_YEAR * year, 2)
        points.append(
            {
                "year": year,
                "value": value,
                "contributed": contributed,
                "growth": round(value - contributed, 2),
            }
        )
    return points


# ── allocation template ────────────────────────────────────────────────────────


def equity_was_capped(risk_appetite: str, horizon_years: float) -> bool:
    """Whether the horizon cap actually reduced equity below the appetite's template.

    Exists because the model cannot be trusted to infer it. Told only "the
    template caps equity on short horizons", gpt-4o explained a 12-year plan as
    "equity is capped at 50% because the horizon is relatively short" -- the cap
    had not fired and 12 years is not short, but the rule was in the prompt so it
    got applied. Found live on 2026-11-08.
    """
    base = DEFAULT_ALLOCATIONS.get(risk_appetite) or DEFAULT_ALLOCATIONS[FALLBACK_RISK]
    return allocation_template(risk_appetite, horizon_years)["equity"] < base["equity"]


def allocation_template(risk_appetite: str, horizon_years: float) -> dict[str, float]:
    """A starting allocation by exposure class, capped for a short horizon.

    **A template, not a recommendation.** The agent presents it as "a commonly
    used starting point for this horizon and appetite", never as what the user
    should hold — the distinction compliance turns on.

    An unknown appetite falls back to moderate rather than raising: the profile
    comes from a UI control and a typo should not take down a turn.
    """
    base = DEFAULT_ALLOCATIONS.get(risk_appetite) or DEFAULT_ALLOCATIONS[FALLBACK_RISK]
    allocation = dict(base)

    for max_years, cap in EQUITY_CAPS:
        if horizon_years < max_years and allocation["equity"] > cap:
            # Whatever equity is given up moves to debt, the next rung down the
            # risk ladder -- not to cash, which would overcorrect into a
            # guaranteed real-terms loss over several years.
            freed = allocation["equity"] - cap
            allocation["equity"] = cap
            allocation["debt"] = round(allocation["debt"] + freed, 2)
            break

    return allocation
