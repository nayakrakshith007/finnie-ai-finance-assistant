"""Acceptance tests for the goal projection maths (PRD FR-013).

Every expectation here was evaluated from the closed form written out longhand,
independently of the implementation — not produced by running the code and
pasting the result. The formula each one comes from is named in the test, so a
reader can check the number without trusting either the code or me.

The three formulas:

    lump sum        FV = PV x (1 + r)^n
    SIP (due)       FV = P x [((1 + i)^n - 1) / i] x (1 + i),  i = annual/12
    required SIP    P  = target / ([((1 + i)^n - 1) / i] x (1 + i))

`i = annual/12` is simple division, not the effective monthly rate
`(1 + annual)^(1/12) - 1`. That matches every Indian SIP calculator a user will
have seen — AMFI's, Groww's, Zerodha's — and `test_monthly_rate_is_simple_division`
pins the choice so it cannot drift into the effective form unnoticed.
"""

from __future__ import annotations

import pytest

from goals.projections import (
    DEFAULT_ALLOCATIONS,
    allocation_template,
    future_value_lumpsum,
    inflation_adjusted_target,
    projection_series,
    real_return,
    required_monthly_sip,
    sip_future_value,
    years_to_target,
)

# ── lump sum compounding ───────────────────────────────────────────────────────


def test_lumpsum_compounds_annually():
    # 1,00,000 x 1.10^2 = 1,00,000 x 1.21 = 1,21,000
    assert future_value_lumpsum(100_000, 0.10, 2) == 121_000.00


def test_lumpsum_over_ten_years():
    # 1,00,000 x 1.12^10 = 3,10,584.82
    assert future_value_lumpsum(100_000, 0.12, 10) == 310_584.82


def test_lumpsum_at_zero_return_is_unchanged():
    assert future_value_lumpsum(100_000, 0.0, 10) == 100_000.00


def test_lumpsum_over_zero_years_is_unchanged():
    assert future_value_lumpsum(100_000, 0.12, 0) == 100_000.00


def test_lumpsum_rejects_a_negative_horizon():
    with pytest.raises(ValueError, match="negative"):
        future_value_lumpsum(100_000, 0.12, -1)


# ── SIP accumulation ───────────────────────────────────────────────────────────


def test_sip_future_value_over_one_year():
    """P=10,000, i=0.01, n=12:
        ((1.01^12 - 1) / 0.01) x 1.01 = 12.68250301 x 1.01 = 12.80932804
        x 10,000 = 1,28,093.28
    """
    assert sip_future_value(10_000, 0.12, 1) == 128_093.28


def test_sip_future_value_over_ten_years():
    assert sip_future_value(10_000, 0.12, 10) == 2_323_390.76


def test_sip_future_value_fifteen_years_at_eleven_percent():
    assert sip_future_value(5_000, 0.11, 15) == 2_294_287.81


def test_sip_is_an_annuity_due_not_an_ordinary_annuity():
    """Contributions are modelled at the *start* of each month.

    An ordinary annuity (end of month) gives 1,26,825.03 for the same inputs.
    The difference is ₹1,268 on one year of a ₹10,000 SIP — about 1%, which
    compounds into a real gap over a 20-year horizon. A SIP mandate debits on a
    chosen date and is invested at that NAV, so the money works for that month:
    annuity-due is the correct model, and this test states the ₹1,268 so the
    choice cannot be quietly reversed.
    """
    ordinary = 126_825.03
    assert sip_future_value(10_000, 0.12, 1) == 128_093.28
    assert round(sip_future_value(10_000, 0.12, 1) - ordinary, 2) == 1_268.25


def test_monthly_rate_is_simple_division_not_the_effective_rate():
    """annual/12, as Indian SIP calculators do it.

    The effective monthly rate (1.12^(1/12) - 1 = 0.9489%) would give a *lower*
    figure. Both are defensible; only one matches what the user has seen
    elsewhere, and an unexplained mismatch reads as a bug in Finnie.
    """
    effective_i = (1 + 0.12) ** (1 / 12) - 1
    effective_fv = 10_000 * (((1 + effective_i) ** 12 - 1) / effective_i) * (1 + effective_i)
    assert sip_future_value(10_000, 0.12, 1) > effective_fv


def test_sip_at_zero_return_is_just_the_contributions():
    # 10,000 x 12 x 3 = 3,60,000
    assert sip_future_value(10_000, 0.0, 3) == 360_000.00


def test_sip_over_zero_years_is_zero():
    assert sip_future_value(10_000, 0.12, 0) == 0.0


# ── required SIP ───────────────────────────────────────────────────────────────


def test_required_sip_for_ten_lakh_in_ten_years():
    # 10,00,000 / 232.339076 = 4,304.05
    assert required_monthly_sip(1_000_000, 0.12, 10) == 4_304.05


def test_required_sip_for_fifty_lakh_in_fifteen_years():
    assert required_monthly_sip(5_000_000, 0.11, 15) == 10_896.63


def _rounding_tolerance(target: float, sip: float) -> float:
    """How far a round-trip may legitimately miss, and why.

    `required_monthly_sip` rounds to paise, because a SIP mandate is set in
    rupees and paise rather than to fourteen decimal places. The annuity factor
    then amplifies that rounding: at 12% over 10 years the factor is 232.34, so
    half a paisa on the SIP becomes ₹1.16 on the maturity value. A flat ±₹1
    tolerance would therefore fail a formula that is exactly right.

    Bound: 0.005 x factor, where factor = target / sip. Plus a paisa for the
    rounding inside `sip_future_value` itself.
    """
    return 0.005 * (target / sip) + 0.01


def test_required_sip_round_trips_through_the_forward_formula():
    """The strongest check available: invest what it asks for, land on the target.

    This catches an inverted formula that happens to look plausible, which a
    single expected value cannot.
    """
    sip = required_monthly_sip(1_000_000, 0.12, 10)
    error = abs(sip_future_value(sip, 0.12, 10) - 1_000_000)
    assert error < _rounding_tolerance(1_000_000, sip)


@pytest.mark.parametrize(
    ("target", "rate", "years"),
    [(1_000_000, 0.12, 10), (5_000_000, 0.11, 15), (250_000, 0.07, 3), (10_000_000, 0.14, 25)],
)
def test_required_sip_round_trips_across_the_range(target, rate, years):
    sip = required_monthly_sip(target, rate, years)
    error = abs(sip_future_value(sip, rate, years) - target)
    assert error < _rounding_tolerance(target, sip)


def test_required_sip_at_zero_return_is_the_target_split_evenly():
    # 3,60,000 over 36 months with no growth = 10,000 a month
    assert required_monthly_sip(360_000, 0.0, 3) == 10_000.00


def test_required_sip_rejects_a_zero_horizon():
    """There is no monthly contribution that reaches a target in no time."""
    with pytest.raises(ValueError, match="horizon"):
        required_monthly_sip(1_000_000, 0.12, 0)


def test_required_sip_for_a_target_already_met_is_zero():
    assert required_monthly_sip(0, 0.12, 10) == 0.0


# ── inflation ──────────────────────────────────────────────────────────────────


def test_inflation_adjusted_target_over_ten_years():
    # 10,00,000 x 1.06^10 = 17,90,847.70
    assert inflation_adjusted_target(1_000_000, 0.06, 10) == 1_790_847.70


def test_inflation_adjusted_target_over_one_year():
    assert inflation_adjusted_target(1_000_000, 0.06, 1) == 1_060_000.00


def test_inflation_is_the_point_of_the_whole_feature():
    """A ₹10 lakh goal in 10 years needs ₹17.9 lakh of 2036 money.

    Planning for the nominal figure under-saves by 79%, which is the single
    biggest error a beginner makes here, so it has a test of its own.
    """
    nominal = 1_000_000
    adjusted = inflation_adjusted_target(nominal, 0.06, 10)
    assert adjusted / nominal > 1.75


def test_real_return_uses_the_fisher_relation():
    """(1 + 0.12) / (1 + 0.06) - 1 = 0.056604, i.e. 5.66%.

    Not the naive 12% - 6% = 6%. The difference is small here and large at high
    inflation, and the exact form is what a finance interviewer will ask for.
    """
    assert real_return(0.12, 0.06) == 0.0566


def test_real_return_can_be_near_zero():
    # (1.07 / 1.06) - 1 = 0.009434 -> 0.94%: an FD barely beating inflation.
    assert real_return(0.07, 0.06) == 0.0094


def test_real_return_can_be_negative():
    assert real_return(0.04, 0.06) < 0


# ── the projection series (feeds the FR-063 chart) ─────────────────────────────


def test_projection_series_has_one_point_per_year_plus_the_start():
    series = projection_series(10_000, 0.12, 3)
    assert len(series) == 4
    assert series[0]["year"] == 0
    assert series[0]["value"] == 0.0


def test_projection_series_matches_the_closed_form_each_year():
    series = projection_series(10_000, 0.12, 3)
    assert [p["value"] for p in series[1:]] == [128_093.28, 272_432.00, 435_076.47]


def test_projection_series_separates_contributions_from_growth():
    """A beginner's most useful realisation: how much of the total is not theirs.

    Year 3: 3,60,000 contributed, 4,35,076.47 total -> 75,076.47 is growth.
    """
    final = projection_series(10_000, 0.12, 3)[-1]
    assert final["contributed"] == 360_000.00
    assert final["growth"] == 75_076.47
    assert round(final["contributed"] + final["growth"], 2) == final["value"]


def test_projection_series_is_json_able():
    import json

    json.dumps(projection_series(10_000, 0.12, 5))


# ── years to target ────────────────────────────────────────────────────────────


def test_years_to_target_inverts_the_sip_formula():
    # A 4,304.05 SIP at 12% reaches 10 lakh in 10 years.
    assert years_to_target(4_304.05, 0.12, 1_000_000) == 10.0


def test_years_to_target_at_zero_return():
    # 10,000 x 12 = 1,20,000 a year; 3,60,000 / 1,20,000 = 3 years
    assert years_to_target(10_000, 0.0, 360_000) == 3.0


def test_years_to_target_is_none_when_the_sip_is_zero():
    """Contributing nothing never arrives; None says so rather than returning inf."""
    assert years_to_target(0, 0.12, 1_000_000) is None


# ── allocation template ────────────────────────────────────────────────────────


@pytest.mark.parametrize("risk", ["conservative", "moderate", "aggressive"])
def test_every_allocation_sums_to_one_hundred(risk):
    for horizon in (1, 2, 3, 4, 5, 7, 10, 25):
        allocation = allocation_template(risk, horizon)
        assert round(sum(allocation.values()), 2) == 100.0, f"{risk}/{horizon}y"


def test_allocation_follows_risk_appetite_at_a_long_horizon():
    assert allocation_template("aggressive", 20)["equity"] > (
        allocation_template("moderate", 20)["equity"]
    )
    assert allocation_template("moderate", 20)["equity"] > (
        allocation_template("conservative", 20)["equity"]
    )


def test_a_short_horizon_caps_equity_whatever_the_appetite():
    """Equity needs time, and a stated risk appetite does not create time.

    Someone aggressive saving for a goal two years out still should not see a 75%
    equity template: the sequence-of-returns risk over two years is the point,
    and this is the one place the template overrides what the user asked for.
    """
    aggressive_short = allocation_template("aggressive", 2)
    assert aggressive_short["equity"] <= 10
    assert aggressive_short["equity"] < allocation_template("aggressive", 20)["equity"]


def test_a_medium_horizon_caps_equity_moderately():
    assert allocation_template("aggressive", 4)["equity"] <= 40


def test_the_cap_never_raises_a_conservative_allocation():
    """The cap is a ceiling, not a target: it must not push equity *up*."""
    long_term = allocation_template("conservative", 20)["equity"]
    assert allocation_template("conservative", 2)["equity"] <= long_term


def test_an_unknown_risk_appetite_falls_back_to_moderate():
    assert allocation_template("reckless", 10) == allocation_template("moderate", 10)


def test_allocation_uses_exposure_classes_not_instrument_classes():
    """These are two different taxonomies, deliberately.

    An allocation template talks about *exposure* — equity, debt, gold, cash. A
    portfolio holding talks about *instrument* — stock, mutual_fund, etf, bond.
    An equity mutual fund is instrument `mutual_fund` and exposure `equity`, so
    collapsing the two would make the Goal agent unable to say "you hold 46%
    equity exposure" about a portfolio of funds.
    """
    from goals.projections import ALLOCATION_CLASSES

    assert ALLOCATION_CLASSES == ("equity", "debt", "gold", "cash")
    for risk in DEFAULT_ALLOCATIONS:
        assert set(allocation_template(risk, 10)) == set(ALLOCATION_CLASSES)


def test_every_instrument_class_maps_to_an_exposure_class():
    """The bridge between the two taxonomies, needed when the graph composes the
    Portfolio and Goal agents in one turn (FR-003). Every instrument the portfolio
    agent accepts must have a declared exposure, or that comparison silently
    drops holdings."""
    from goals.projections import EXPOSURE_MAP
    from portfolio.holdings import ASSET_CLASSES

    for instrument in ASSET_CLASSES:
        assert instrument in EXPOSURE_MAP, f"{instrument} has no declared exposure"
        assert EXPOSURE_MAP[instrument] in ALLOCATION_CLASSES_FOR_TEST


ALLOCATION_CLASSES_FOR_TEST = ("equity", "debt", "gold", "cash")
