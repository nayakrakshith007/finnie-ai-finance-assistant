"""Acceptance tests for the portfolio metric functions (PRD FR-012).

Every expected value here is calculated by hand in the test or its comment, never
by running the code and copying the output. That is the whole point: these are the
numbers a user will act on, and a test that asserts "whatever the function
returned last time" cannot catch a formula that was wrong from the start.

The reference portfolio, used throughout, totals a deliberately round ₹1,00,000:

    A  stock        ₹50,000   50%
    B  stock        ₹20,000   20%
    C  mutual_fund  ₹20,000   20%   expense ratio 1.2%
    D  cash         ₹10,000   10%

    HHI          = 0.50² + 0.20² + 0.20² + 0.10² = 0.25 + 0.04 + 0.04 + 0.01 = 0.34
    effective N  = 1 / 0.34                                            = 2.9412
    classes      = stock 70%, mutual_fund 20%, cash 10%
"""

from __future__ import annotations

import pytest

from portfolio.metrics import (
    annual_expense_cost,
    blended_expense_ratio,
    class_breakdown,
    concentration_flags,
    diversification_score,
    effective_holdings,
    fund_weighted_expense_ratio,
    hhi,
    risk_band,
    risk_score,
    total_value,
    unrealised_pnl,
    weights_pct,
)

VALUES = [50_000.0, 20_000.0, 20_000.0, 10_000.0]
CLASSES = ["stock", "stock", "mutual_fund", "cash"]
RISK_WEIGHTS = {"cash": 1, "bond": 2, "etf": 3, "mutual_fund": 3, "stock": 4, "crypto": 5}


# ── totals and weights ─────────────────────────────────────────────────────────


def test_total_value_sums_holdings():
    assert total_value(VALUES) == 100_000.0


def test_total_value_of_nothing_is_zero_not_an_error():
    """An empty portfolio is a legitimate state — a new user has one."""
    assert total_value([]) == 0.0


def test_weights_are_percentages_that_sum_to_one_hundred():
    assert weights_pct(VALUES) == [50.0, 20.0, 20.0, 10.0]
    assert sum(weights_pct(VALUES)) == 100.0


def test_weights_of_an_empty_portfolio_are_empty():
    assert weights_pct([]) == []


def test_weights_do_not_divide_by_zero():
    """Holdings can total zero — a cash account at ₹0, or quantities not yet filled."""
    assert weights_pct([0.0, 0.0]) == [0.0, 0.0]


def test_weights_are_rounded_to_two_places():
    # Three equal holdings: 100/3 = 33.333... -> 33.33 each.
    assert weights_pct([10.0, 10.0, 10.0]) == [33.33, 33.33, 33.33]


# ── asset-class breakdown ──────────────────────────────────────────────────────


def test_class_breakdown_aggregates_the_two_stocks():
    # stock 50,000 + 20,000 = 70,000 -> 70%; mutual_fund 20%; cash 10%.
    assert class_breakdown(CLASSES, VALUES) == {
        "stock": 70.0,
        "mutual_fund": 20.0,
        "cash": 10.0,
    }


def test_class_breakdown_is_ordered_largest_first():
    """The UI renders this directly; ordering it here keeps presentation logic out."""
    assert list(class_breakdown(CLASSES, VALUES)) == ["stock", "mutual_fund", "cash"]


def test_class_breakdown_of_an_empty_portfolio_is_empty():
    assert class_breakdown([], []) == {}


def test_class_breakdown_rejects_mismatched_inputs():
    """Silently zipping to the shorter list would drop a holding from the total."""
    with pytest.raises(ValueError, match="same length"):
        class_breakdown(["stock"], [1.0, 2.0])


# ── concentration: HHI ─────────────────────────────────────────────────────────


def test_hhi_of_the_reference_portfolio():
    # 0.5^2 + 0.2^2 + 0.2^2 + 0.1^2 = 0.34
    assert hhi([50.0, 20.0, 20.0, 10.0]) == 0.34


def test_hhi_of_a_single_holding_is_one():
    """One holding is maximum concentration by definition."""
    assert hhi([100.0]) == 1.0


def test_hhi_of_four_equal_holdings_is_one_over_four():
    # 4 x 0.25^2 = 0.25
    assert hhi([25.0, 25.0, 25.0, 25.0]) == 0.25


def test_hhi_of_an_empty_portfolio_is_zero():
    assert hhi([]) == 0.0


def test_effective_holdings_is_the_reciprocal_of_hhi():
    # 1 / 0.34 = 2.9412
    assert effective_holdings(0.34) == 2.94


def test_effective_holdings_of_ten_equal_positions_is_ten():
    assert effective_holdings(hhi([10.0] * 10)) == 10.0


def test_effective_holdings_of_an_empty_portfolio_is_zero():
    assert effective_holdings(0.0) == 0.0


def test_two_portfolios_with_the_same_count_can_differ_in_effective_holdings():
    """Why HHI and not a count: both have 4 holdings, only one is diversified."""
    even = effective_holdings(hhi([25.0, 25.0, 25.0, 25.0]))
    lopsided = effective_holdings(hhi([97.0, 1.0, 1.0, 1.0]))
    assert even == 4.0
    assert lopsided < 1.1, "a 97% position is effectively one holding"


# ── concentration flags ────────────────────────────────────────────────────────


def test_holding_above_the_threshold_is_flagged():
    flagged = concentration_flags(["A", "B", "C", "D"], [50.0, 20.0, 20.0, 10.0], 25.0)
    assert flagged == [("A", 50.0)]


def test_the_threshold_is_exclusive():
    """At exactly the threshold nothing is wrong yet; above it, something is."""
    assert concentration_flags(["A", "B"], [25.0, 75.0], 25.0) == [("B", 75.0)]


def test_a_spread_portfolio_raises_no_flag():
    assert concentration_flags(["A", "B", "C", "D", "E"], [20.0] * 5, 25.0) == []


def test_flags_are_ordered_largest_first():
    flagged = concentration_flags(["A", "B"], [30.0, 70.0], 25.0)
    assert [name for name, _ in flagged] == ["B", "A"]


# ── diversification score ──────────────────────────────────────────────────────


def test_diversification_score_of_the_reference_portfolio():
    """Hand calculation of the documented composite.

        evenness:     normalised HHI = (0.34 - 1/4) / (1 - 1/4) = 0.09 / 0.75 = 0.12
                      -> 1 - 0.12                                            = 0.88
        breadth:      effective N / 12 = 2.9412 / 12                         = 0.2451
        class spread: 3 distinct classes / 4                                 = 0.75

        score = 100 x (0.4 x 0.88 + 0.4 x 0.2451 + 0.2 x 0.75)
              = 100 x (0.352 + 0.09804 + 0.15)
              = 60.0
    """
    assert diversification_score([50.0, 20.0, 20.0, 10.0], n_classes=3) == 60


def test_a_single_holding_scores_near_zero():
    """One stock in one class.

        evenness:     undefined for n = 1 (the normalisation divides by 1 - 1/n),
                      so it is defined as 0 -- a single holding has nothing to
                      spread evenly                                       = 0
        breadth:      effective N / 12 = 1 / 12                           = 0.0833
        class spread: 1 / 4                                               = 0.25

        score = 100 x (0.4 x 0 + 0.4 x 0.0833 + 0.2 x 0.25)
              = 100 x (0.03333 + 0.05)
              = 8.33 -> 8
    """
    assert diversification_score([100.0], n_classes=1) == 8


def test_twelve_equal_holdings_across_four_classes_scores_one_hundred():
    """The documented ceiling: evenness 1.0, breadth 12/12, spread 4/4."""
    assert diversification_score([100 / 12] * 12, n_classes=4) == 100


def test_score_is_bounded_even_for_an_enormous_portfolio():
    """Breadth and class spread are capped, so 50 holdings cannot score 140."""
    assert diversification_score([2.0] * 50, n_classes=8) == 100


def test_evenness_alone_does_not_earn_a_high_score():
    """Three equally-weighted stocks are even but not diversified.

    This is the case a naive 1-HHI score gets wrong: it would return 100.
    """
    assert diversification_score([33.33, 33.33, 33.33], n_classes=1) < 60


def test_an_empty_portfolio_scores_zero():
    assert diversification_score([], n_classes=0) == 0


# ── risk band ──────────────────────────────────────────────────────────────────


def test_risk_score_is_weighted_by_asset_class():
    # 0.70 x 4 (stock) + 0.20 x 3 (mutual_fund) + 0.10 x 1 (cash) = 3.5
    breakdown = {"stock": 70.0, "mutual_fund": 20.0, "cash": 10.0}
    assert risk_score(breakdown, RISK_WEIGHTS) == 3.5


def test_all_cash_scores_the_floor():
    assert risk_score({"cash": 100.0}, RISK_WEIGHTS) == 1.0


def test_all_crypto_scores_the_ceiling():
    assert risk_score({"crypto": 100.0}, RISK_WEIGHTS) == 5.0


def test_an_unconfigured_asset_class_is_treated_as_the_highest_risk():
    """Unknown should fail safe. Scoring it 0 would let any new class look riskless."""
    assert risk_score({"mystery": 100.0}, RISK_WEIGHTS) == 5.0


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (1.0, "conservative"),
        (2.0, "conservative"),
        (2.01, "moderate"),
        (3.5, "moderate"),
        (3.51, "aggressive"),
        (5.0, "aggressive"),
    ],
)
def test_risk_bands_at_their_boundaries(score, band):
    assert risk_band(score) == band


def test_the_reference_portfolio_lands_on_the_moderate_boundary():
    """3.5 is the inclusive top of moderate — 70% equity is not yet aggressive."""
    breakdown = {"stock": 70.0, "mutual_fund": 20.0, "cash": 10.0}
    assert risk_band(risk_score(breakdown, RISK_WEIGHTS)) == "moderate"


def test_an_empty_portfolio_has_no_risk_band():
    assert risk_score({}, RISK_WEIGHTS) == 0.0
    assert risk_band(0.0) == "unknown"


# ── expenses ───────────────────────────────────────────────────────────────────


def test_annual_expense_cost_in_rupees():
    # Only C carries a ratio: 20,000 x 1.2% = ₹240.
    pairs = [(50_000.0, None), (20_000.0, None), (20_000.0, 1.2), (10_000.0, None)]
    assert annual_expense_cost(pairs) == 240.0


def test_blended_ratio_spreads_the_cost_over_the_whole_portfolio():
    # ₹240 of cost on ₹1,00,000 invested = 0.24%.
    pairs = [(50_000.0, None), (20_000.0, None), (20_000.0, 1.2), (10_000.0, None)]
    assert blended_expense_ratio(pairs) == 0.24


def test_fund_weighted_ratio_describes_only_the_funds():
    """1.2% is what the *fund* charges; 0.24% is what the *portfolio* pays.

    Reporting only the blended number makes an expensive fund look cheap;
    reporting only the fund number overstates the drag. Both are kept.
    """
    pairs = [(50_000.0, None), (20_000.0, None), (20_000.0, 1.2), (10_000.0, None)]
    assert fund_weighted_expense_ratio(pairs) == 1.2


def test_fund_weighted_ratio_across_two_funds():
    # (30,000 x 0.5 + 10,000 x 1.5) / 40,000 = (15,000 + 15,000) / 40,000 = 0.75
    assert fund_weighted_expense_ratio([(30_000.0, 0.5), (10_000.0, 1.5)]) == 0.75


def test_no_funds_means_no_expense_figures():
    pairs = [(50_000.0, None), (20_000.0, None)]
    assert annual_expense_cost(pairs) == 0.0
    assert blended_expense_ratio(pairs) == 0.0
    assert fund_weighted_expense_ratio(pairs) == 0.0


# ── unrealised profit and loss ─────────────────────────────────────────────────


def test_unrealised_gain():
    # Cost 10 x ₹1,000 = ₹10,000; now worth ₹13,000 -> +₹3,000, +30%.
    assert unrealised_pnl(value=13_000.0, cost=10_000.0) == (3_000.0, 30.0)


def test_unrealised_loss_is_negative():
    assert unrealised_pnl(value=8_000.0, cost=10_000.0) == (-2_000.0, -20.0)


def test_unrealised_pnl_without_a_cost_basis_is_none():
    """A user who did not enter purchase prices gets no P&L, not a fake zero."""
    assert unrealised_pnl(value=13_000.0, cost=None) is None


def test_unrealised_pnl_does_not_divide_by_zero():
    assert unrealised_pnl(value=100.0, cost=0.0) == (100.0, 0.0)
