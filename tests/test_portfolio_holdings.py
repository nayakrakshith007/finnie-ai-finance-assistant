"""Acceptance tests for holdings parsing and the analysis assembly (FR-012, FR-062).

Two layers, both pure:

* `holdings.py` turns untrusted user input (a CSV upload, a typed row) into
  validated `Holding` objects, and says *specifically* what was wrong with the
  rows it rejected. FR-062 requires a malformed CSV to produce a friendly,
  specific error, which means the parser has to collect problems rather than
  raise on the first one.
* `analysis.py` turns holdings plus a price map into the finished analysis. It
  takes prices as an argument instead of fetching them, so the whole assembly is
  testable offline and the agent is the only thing that touches the network.
"""

from __future__ import annotations

import pytest

from portfolio.analysis import analyse
from portfolio.holdings import (
    SAMPLE_PORTFOLIO,
    Holding,
    parse_holdings,
    parse_portfolio_csv,
)

CONFIG_RISK_WEIGHTS = {
    "cash": 1,
    "bond": 2,
    "etf": 3,
    "mutual_fund": 3,
    "stock": 4,
    "crypto": 5,
}


def holding(symbol="RELIANCE.NS", qty=10.0, asset_class="stock", **kw) -> Holding:
    return Holding(symbol=symbol, quantity=qty, asset_class=asset_class, **kw)


# ── parsing rows ───────────────────────────────────────────────────────────────


def test_a_valid_row_becomes_a_holding():
    holdings, errors = parse_holdings([
        {"symbol": "reliance.ns", "quantity": "10", "asset_class": "stock"}
    ])

    assert errors == []
    assert holdings[0].symbol == "RELIANCE.NS", "symbols are normalised on the way in"
    assert holdings[0].quantity == 10.0
    assert holdings[0].asset_class == "stock"


def test_optional_fields_are_parsed_when_present():
    holdings, errors = parse_holdings([
        {
            "symbol": "HDFCMF",
            "quantity": "100",
            "asset_class": "mutual_fund",
            "avg_cost": "95.5",
            "expense_ratio": "1.2",
            "name": "HDFC Flexi Cap",
        }
    ])

    assert errors == []
    assert holdings[0].avg_cost == 95.5
    assert holdings[0].expense_ratio == 1.2
    assert holdings[0].name == "HDFC Flexi Cap"


def test_missing_optional_fields_are_none_not_zero():
    """A holding with no cost basis is unknown, not free."""
    holdings, _ = parse_holdings([
        {"symbol": "TCS", "quantity": "5", "asset_class": "stock"}
    ])
    assert holdings[0].avg_cost is None
    assert holdings[0].expense_ratio is None


def test_asset_class_defaults_to_stock():
    """The commonest case, and the one a user is least likely to type."""
    holdings, errors = parse_holdings([{"symbol": "TCS", "quantity": "5"}])
    assert errors == []
    assert holdings[0].asset_class == "stock"


def test_asset_class_is_case_and_space_insensitive():
    holdings, _ = parse_holdings([
        {"symbol": "X", "quantity": "1", "asset_class": " Mutual Fund "}
    ])
    assert holdings[0].asset_class == "mutual_fund"


# ── rejecting bad rows, specifically (FR-062) ──────────────────────────────────


def test_a_missing_symbol_is_reported_with_its_row_number():
    _, errors = parse_holdings([{"quantity": "10", "asset_class": "stock"}])
    assert len(errors) == 1
    assert "row 1" in errors[0]
    assert "symbol" in errors[0]


def test_a_non_numeric_quantity_names_the_offending_value():
    """'ten' must come back as 'ten', not as a ValueError the user cannot read."""
    _, errors = parse_holdings([{"symbol": "TCS", "quantity": "ten"}])
    assert "ten" in errors[0]
    assert "quantity" in errors[0]


def test_a_negative_quantity_is_rejected():
    _, errors = parse_holdings([{"symbol": "TCS", "quantity": "-5"}])
    assert "negative" in errors[0].lower() or "positive" in errors[0].lower()


def test_a_zero_quantity_is_rejected():
    """A zero-quantity row is almost always a typo, and it contributes nothing."""
    _, errors = parse_holdings([{"symbol": "TCS", "quantity": "0"}])
    assert errors


def test_an_unknown_asset_class_lists_the_valid_ones():
    _, errors = parse_holdings([
        {"symbol": "TCS", "quantity": "1", "asset_class": "derivatives"}
    ])
    assert "derivatives" in errors[0]
    assert "stock" in errors[0], "the error must say what IS allowed"


def test_one_bad_row_does_not_discard_the_good_ones():
    """Collecting errors rather than raising: a 20-line CSV with one typo should
    still value the other 19 lines."""
    holdings, errors = parse_holdings([
        {"symbol": "TCS", "quantity": "5"},
        {"symbol": "", "quantity": "5"},
        {"symbol": "INFY", "quantity": "3"},
    ])

    assert [h.symbol for h in holdings] == ["TCS.NS", "INFY.NS"]
    assert len(errors) == 1
    assert "row 2" in errors[0]


def test_no_rows_yields_nothing_and_no_error():
    assert parse_holdings([]) == ([], [])


# ── duplicate symbols ──────────────────────────────────────────────────────────


def test_duplicate_symbols_are_merged_with_a_weighted_average_cost():
    """Buying the same stock twice is normal, not an error.

    10 @ ₹1,000 and 10 @ ₹1,200 is 20 units at ₹1,100 average -- the weighted
    mean, not the arithmetic mean of the two prices (which here coincide, so the
    second case below uses unequal quantities to prove the weighting).
    """
    holdings, errors = parse_holdings([
        {"symbol": "TCS", "quantity": "10", "avg_cost": "1000"},
        {"symbol": "TCS", "quantity": "30", "avg_cost": "1200"},
    ])

    assert errors == []
    assert len(holdings) == 1
    assert holdings[0].quantity == 40.0
    # (10 x 1000 + 30 x 1200) / 40 = (10,000 + 36,000) / 40 = 1,150
    assert holdings[0].avg_cost == 1150.0


def test_merging_a_known_cost_with_an_unknown_one_keeps_the_known_one():
    holdings, _ = parse_holdings([
        {"symbol": "TCS", "quantity": "10", "avg_cost": "1000"},
        {"symbol": "TCS", "quantity": "10"},
    ])
    assert holdings[0].quantity == 20.0
    assert holdings[0].avg_cost == 1000.0


# ── CSV (FR-062) ───────────────────────────────────────────────────────────────


def test_csv_with_a_header_is_parsed():
    csv = "symbol,quantity,asset_class\nRELIANCE,10,stock\nTCS,5,stock\n"
    holdings, errors = parse_portfolio_csv(csv)

    assert errors == []
    assert [h.symbol for h in holdings] == ["RELIANCE.NS", "TCS.NS"]


def test_csv_headers_are_normalised():
    """Users export from brokers, who capitalise and space headers as they like."""
    csv = "Symbol, Quantity , Asset Class\nTCS,5,stock\n"
    holdings, errors = parse_portfolio_csv(csv)
    assert errors == []
    assert holdings[0].symbol == "TCS.NS"


def test_a_csv_missing_the_required_columns_says_which():
    csv = "ticker,units\nTCS,5\n"
    holdings, errors = parse_portfolio_csv(csv)

    assert holdings == []
    assert "symbol" in errors[0] and "quantity" in errors[0]


def test_an_empty_csv_is_a_friendly_error_not_a_crash():
    holdings, errors = parse_portfolio_csv("")
    assert holdings == []
    assert errors and "empty" in errors[0].lower()


def test_a_header_only_csv_reports_no_rows():
    holdings, errors = parse_portfolio_csv("symbol,quantity\n")
    assert holdings == []
    assert errors and "no holdings" in errors[0].lower()


def test_blank_lines_in_a_csv_are_skipped_not_reported():
    """Trailing newlines are an artefact of every spreadsheet export."""
    csv = "symbol,quantity\nTCS,5\n\n\n"
    holdings, errors = parse_portfolio_csv(csv)
    assert len(holdings) == 1
    assert errors == []


def test_the_sample_portfolio_is_valid_and_indian():
    """FR-062's one-click sample: it must parse cleanly and demo every class."""
    holdings, errors = parse_holdings(SAMPLE_PORTFOLIO)

    assert errors == []
    assert len(holdings) >= 4
    assert {h.asset_class for h in holdings} >= {"stock", "mutual_fund"}
    assert all(h.symbol.endswith((".NS", ".BO")) or h.asset_class != "stock" for h in holdings)


# ── the analysis assembly ──────────────────────────────────────────────────────

# The reference portfolio from test_portfolio_metrics, expressed as holdings and
# prices so the assembled totals can be checked against the same hand numbers:
#     A 50 x 1,000 = 50,000 stock       B 20 x 1,000 = 20,000 stock
#     C 20 x 1,000 = 20,000 mutual_fund D 10 x 1,000 = 10,000 cash
REFERENCE = [
    Holding("A.NS", 50.0, "stock"),
    Holding("B.NS", 20.0, "stock"),
    Holding("C.NS", 20.0, "mutual_fund", expense_ratio=1.2),
    Holding("D.NS", 10.0, "cash"),
]
PRICES = {s: (1000.0, "live") for s in ("A.NS", "B.NS", "C.NS", "D.NS")}


def analysis_of(holdings=None, prices=None, **kw):
    return analyse(
        holdings if holdings is not None else REFERENCE,
        prices if prices is not None else PRICES,
        risk_weights=CONFIG_RISK_WEIGHTS,
        concentration_pct=25.0,
        **kw,
    )


def test_analysis_totals_match_the_hand_calculations():
    result = analysis_of()

    assert result["total_value"] == 100_000.0
    assert result["holding_count"] == 4
    assert result["hhi"] == 0.34
    assert result["effective_holdings"] == 2.94
    assert result["diversification_score"] == 60
    assert result["risk_score"] == 3.5
    assert result["risk_band"] == "moderate"


def test_analysis_carries_per_holding_allocation():
    rows = analysis_of()["holdings"]
    assert [r["symbol"] for r in rows] == ["A.NS", "B.NS", "C.NS", "D.NS"]
    assert [r["weight_pct"] for r in rows] == [50.0, 20.0, 20.0, 10.0]
    assert rows[0]["value"] == 50_000.0


def test_analysis_flags_the_concentrated_holding():
    assert analysis_of()["concentration_flags"] == [{"symbol": "A.NS", "weight_pct": 50.0}]


def test_analysis_reports_both_expense_figures():
    result = analysis_of()
    assert result["annual_expense_cost"] == 240.0
    assert result["blended_expense_ratio"] == 0.24
    assert result["fund_weighted_expense_ratio"] == 1.2


def test_analysis_breaks_down_by_asset_class():
    assert analysis_of()["class_breakdown"] == {
        "stock": 70.0,
        "mutual_fund": 20.0,
        "cash": 10.0,
    }


def test_unpriced_holdings_are_excluded_and_counted():
    """A holding nobody could price must not be valued at zero and averaged in.

    Zero is a *price*, and a portfolio quietly worth less than it is would be the
    most damaging possible silent failure here.
    """
    prices = {"A.NS": (1000.0, "live"), "B.NS": (1000.0, "live"), "C.NS": (1000.0, "live")}
    result = analysis_of(prices=prices)

    assert result["total_value"] == 90_000.0
    assert result["unpriced"] == ["D.NS"]
    assert result["holding_count"] == 3


def test_provenance_is_carried_per_holding_and_summarised():
    prices = {
        "A.NS": (1000.0, "live"),
        "B.NS": (1000.0, "stale_cache"),
        "C.NS": (1000.0, "live"),
        "D.NS": (1000.0, "mock"),
    }
    result = analysis_of(prices=prices)

    assert result["holdings"][1]["source"] == "stale_cache"
    assert result["is_degraded"] is True
    assert set(result["sources"]) == {"live", "stale_cache", "mock"}


def test_a_fully_live_portfolio_is_not_degraded():
    assert analysis_of()["is_degraded"] is False


def test_profit_and_loss_when_a_cost_basis_is_given():
    holdings = [Holding("A.NS", 50.0, "stock", avg_cost=800.0)]
    result = analysis_of(holdings=holdings, prices={"A.NS": (1000.0, "live")})

    # 50 x 800 = 40,000 cost; 50 x 1,000 = 50,000 value -> +10,000, +25%.
    assert result["total_cost"] == 40_000.0
    assert result["unrealised_pnl"] == 10_000.0
    assert result["unrealised_pnl_pct"] == 25.0


def test_no_cost_basis_means_no_profit_and_loss():
    result = analysis_of()
    assert result["unrealised_pnl"] is None
    assert result["unrealised_pnl_pct"] is None


def test_partial_cost_basis_is_reported_as_partial():
    """Mixing known and unknown costs would otherwise understate the gain."""
    holdings = [
        Holding("A.NS", 50.0, "stock", avg_cost=800.0),
        Holding("B.NS", 20.0, "stock"),
    ]
    result = analysis_of(holdings=holdings, prices=PRICES)
    assert result["cost_basis_complete"] is False


def test_an_empty_portfolio_analyses_to_zeros_not_an_exception():
    result = analysis_of(holdings=[], prices={})

    assert result["total_value"] == 0.0
    assert result["holding_count"] == 0
    assert result["risk_band"] == "unknown"
    assert result["diversification_score"] == 0
    assert result["concentration_flags"] == []


def test_analysis_output_is_json_able():
    """`portfolio` is state (FR-001) and must survive checkpoint serialisation."""
    import json

    json.dumps(analysis_of())


@pytest.mark.parametrize("missing", ["risk_weights", "concentration_pct"])
def test_analysis_requires_its_policy_arguments(missing):
    """Thresholds come from config, never a default buried in the maths."""
    kwargs = {"risk_weights": CONFIG_RISK_WEIGHTS, "concentration_pct": 25.0}
    del kwargs[missing]
    with pytest.raises(TypeError):
        analyse(REFERENCE, PRICES, **kwargs)


# ── symbols only get an exchange suffix if they trade on one ───────────────────


def test_a_stock_symbol_gets_the_nse_suffix():
    holdings, _ = parse_holdings([{"symbol": "reliance", "quantity": "1", "asset_class": "stock"}])
    assert holdings[0].symbol == "RELIANCE.NS"


def test_an_etf_symbol_gets_the_nse_suffix():
    holdings, _ = parse_holdings([{"symbol": "niftybees", "quantity": "1", "asset_class": "etf"}])
    assert holdings[0].symbol == "NIFTYBEES.NS"


@pytest.mark.parametrize("asset_class", ["mutual_fund", "bond", "cash", "crypto"])
def test_a_non_traded_holding_keeps_its_plain_label(asset_class):
    """A fund or a bank balance has no ticker.

    Suffixing "HDFCFLEXI" to "HDFCFLEXI.NS" would send yfinance after a listing
    that does not exist, the lookup would fail, and the holding would drop
    silently out of the user's total via `unpriced`.
    """
    holdings, errors = parse_holdings([
        {"symbol": "hdfcflexi", "quantity": "1", "asset_class": asset_class}
    ])
    assert errors == []
    assert holdings[0].symbol == "HDFCFLEXI"


def test_a_user_supplied_price_is_parsed():
    holdings, errors = parse_holdings([
        {"symbol": "HDFCFLEXI", "quantity": "400", "asset_class": "mutual_fund", "price": "168.4"}
    ])
    assert errors == []
    assert holdings[0].price == 168.4


def test_a_holding_without_a_price_has_none():
    holdings, _ = parse_holdings([{"symbol": "TCS", "quantity": "5"}])
    assert holdings[0].price is None


def test_the_sample_portfolio_prices_everything_it_cannot_look_up():
    """Every non-traded sample holding must carry its own NAV, or the one-click
    demo would show a total missing its funds, bonds and cash."""
    from portfolio.holdings import MARKET_TRADED_CLASSES

    holdings, errors = parse_holdings(SAMPLE_PORTFOLIO)
    assert errors == []
    for h in holdings:
        if h.asset_class not in MARKET_TRADED_CLASSES:
            assert h.price is not None, f"{h.symbol} has no ticker and no price"


def test_cost_basis_multiplies_out():
    assert holding(qty=25.0, avg_cost=1180.0).cost_basis == 29_500.0


def test_cost_basis_is_none_without_an_average_cost():
    assert holding().cost_basis is None
