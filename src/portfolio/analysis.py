"""Assemble the finished portfolio analysis (PRD FR-012).

`analyse()` takes holdings and a price map and returns the whole analysis as a
plain JSON-able dict. It does not fetch prices — the agent above it does that and
passes them in. Three things fall out of that choice:

* the entire assembly, including the degraded-price paths, is testable offline;
* `portfolio` in `AgentState` can be serialised for checkpointing without
  needing Finnie's classes to unpickle (FR-001);
* the Streamlit tab can render the dict directly without re-deriving anything,
  which keeps the percentages on screen identical to the ones in the narration.

The policy numbers — risk weights, the concentration threshold — are required
arguments rather than defaults read in here. A default buried in the maths is a
second source of truth competing with `config.yaml`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.logging_setup import get_logger
from portfolio.holdings import Holding
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

logger = get_logger(__name__)

# Price sources that mean "this number is not current". Mirrors
# `Quote.is_degraded`; kept as a literal set because this module must not import
# the market layer just to name two strings.
DEGRADED_SOURCES = frozenset({"stale_cache", "mock"})


def _empty_analysis() -> dict[str, Any]:
    """A new user has no holdings. That is a state to render, not an error."""
    return {
        "total_value": 0.0,
        "total_cost": None,
        "holding_count": 0,
        "currency": "INR",
        "holdings": [],
        "class_breakdown": {},
        "hhi": 0.0,
        "effective_holdings": 0.0,
        "diversification_score": 0,
        "concentration_flags": [],
        "risk_score": 0.0,
        "risk_band": "unknown",
        "annual_expense_cost": 0.0,
        "blended_expense_ratio": 0.0,
        "fund_weighted_expense_ratio": 0.0,
        "unrealised_pnl": None,
        "unrealised_pnl_pct": None,
        "cost_basis_complete": False,
        "unpriced": [],
        "sources": [],
        "is_degraded": False,
    }


def analyse(
    holdings: Sequence[Holding],
    prices: Mapping[str, tuple[float, str]],
    *,
    risk_weights: Mapping[str, int],
    concentration_pct: float,
    currency: str = "INR",
) -> dict[str, Any]:
    """Value the holdings and compute every FR-012 metric.

    Args:
        holdings: validated positions.
        prices: symbol -> (price, source), where source is a `QuoteSource` value.
            A symbol absent from this map could not be priced.
        risk_weights: `config.yaml: portfolio.risk_weights`.
        concentration_pct: `config.yaml: portfolio.concentration_warning_pct`.
        currency: for display; Finnie is INR-only (PRD non-goal 11).

    A holding with no price is **excluded from the totals and listed in
    `unpriced`**, never valued at zero. Zero is itself a price, and a portfolio
    silently worth less than it is would be the most damaging quiet failure in
    this whole system — the user would read a real number that happened to be
    wrong, with nothing on screen suggesting so.
    """
    priced = [h for h in holdings if h.symbol in prices]
    unpriced = [h.symbol for h in holdings if h.symbol not in prices]
    if unpriced:
        logger.warning("No price for %s; excluded from portfolio totals", ", ".join(unpriced))

    if not priced:
        result = _empty_analysis()
        result["unpriced"] = unpriced
        result["currency"] = currency
        return result

    values = [h.quantity * prices[h.symbol][0] for h in priced]
    sources = [prices[h.symbol][1] for h in priced]
    weights = weights_pct(values)
    grand_total = total_value(values)

    rows: list[dict[str, Any]] = []
    for holding, value, weight, source in zip(priced, values, weights, sources, strict=True):
        pnl = unrealised_pnl(value, holding.cost_basis)
        rows.append(
            {
                "symbol": holding.symbol,
                "name": holding.name or holding.symbol,
                "asset_class": holding.asset_class,
                "quantity": holding.quantity,
                "price": round(prices[holding.symbol][0], 2),
                "value": round(value, 2),
                "weight_pct": weight,
                "avg_cost": holding.avg_cost,
                "cost_basis": holding.cost_basis,
                "expense_ratio": holding.expense_ratio,
                "source": source,
                "is_degraded": source in DEGRADED_SOURCES,
                "unrealised_pnl": pnl[0] if pnl else None,
                "unrealised_pnl_pct": pnl[1] if pnl else None,
            }
        )

    breakdown = class_breakdown([h.asset_class for h in priced], values)
    concentration = hhi(weights)
    score = risk_score(breakdown, risk_weights)
    expense_pairs = [(v, h.expense_ratio) for h, v in zip(priced, values, strict=True)]

    # Portfolio-level P&L is reported only when every priced holding has a cost
    # basis. Summing the known ones and dividing by the whole portfolio would
    # understate the return on the part that is actually documented.
    costs = [h.cost_basis for h in priced]
    cost_basis_complete = all(c is not None for c in costs)
    total_cost = round(sum(c for c in costs if c is not None), 2) if any(costs) else None
    portfolio_pnl = (
        unrealised_pnl(grand_total, total_cost) if cost_basis_complete and total_cost else None
    )

    return {
        "total_value": grand_total,
        "total_cost": total_cost,
        "holding_count": len(priced),
        "currency": currency,
        "holdings": rows,
        "class_breakdown": breakdown,
        "hhi": concentration,
        "effective_holdings": effective_holdings(concentration),
        "diversification_score": diversification_score(weights, n_classes=len(breakdown)),
        "concentration_flags": [
            {"symbol": symbol, "weight_pct": weight}
            for symbol, weight in concentration_flags(
                [h.symbol for h in priced], weights, concentration_pct
            )
        ],
        "risk_score": score,
        "risk_band": risk_band(score),
        "annual_expense_cost": annual_expense_cost(expense_pairs),
        "blended_expense_ratio": blended_expense_ratio(expense_pairs),
        "fund_weighted_expense_ratio": fund_weighted_expense_ratio(expense_pairs),
        "unrealised_pnl": portfolio_pnl[0] if portfolio_pnl else None,
        "unrealised_pnl_pct": portfolio_pnl[1] if portfolio_pnl else None,
        "cost_basis_complete": cost_basis_complete,
        "unpriced": unpriced,
        "sources": sorted(set(sources)),
        "is_degraded": any(s in DEGRADED_SOURCES for s in sources),
    }
