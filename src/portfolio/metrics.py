"""Portfolio metrics — pure functions, no I/O, no LLM (PRD FR-012).

Why these are plain functions taking plain numbers
--------------------------------------------------
Every number here is one a user will act on, so every number here is checked
against a hand calculation in `tests/test_portfolio_metrics.py`. That is only
possible because nothing in this module fetches, caches, logs or prompts: given
the same floats it returns the same floats, forever. The agent above it does the
fetching; this layer does the arithmetic.

It also means the maths is reviewable without reading the agent, which matters
because the agent is the part most likely to be rewritten.

A note on what is standard and what is a judgement call
------------------------------------------------------
`hhi`, `effective_holdings`, the expense figures and the P&L are standard
definitions — an interviewer can check them against a textbook.
`diversification_score` and `risk_band` are **Finnie's own heuristics**: the
weights and thresholds are defensible but chosen, not derived. They are
documented as such on each function, because presenting a house heuristic as a
standard measure is the kind of thing that does not survive a follow-up question.
"""

from __future__ import annotations

from collections.abc import Sequence

# Rule-of-thumb ceiling for "broad enough": around a dozen uncorrelated positions
# is where adding more stops materially reducing single-name risk. A cap, not a
# target — 40 holdings is not three times better than 12.
BREADTH_TARGET = 12

# Four classes is treated as full spread: equity, debt, cash and one of
# gold/international. Indian retail portfolios rarely need more to be balanced.
CLASS_SPREAD_TARGET = 4

# Composite weights for `diversification_score`. Evenness and breadth matter most
# and equally; class spread is the tie-breaker, because holding three asset
# classes badly is worse than holding two well.
W_EVENNESS, W_BREADTH, W_CLASS = 0.4, 0.4, 0.2

# Risk-band cut points on the 1-5 asset-class risk scale, inclusive upper bounds.
CONSERVATIVE_MAX = 2.0
MODERATE_MAX = 3.5

# Used when an asset class has no configured risk weight. Deliberately the
# maximum: an unknown instrument failing safe as "risky" is a wrong answer in the
# harmless direction, whereas defaulting to 0 would let any class Finnie has not
# met yet make a portfolio look riskless.
UNKNOWN_CLASS_RISK = 5


# ── totals and weights ─────────────────────────────────────────────────────────


def total_value(values: Sequence[float]) -> float:
    """Sum of holding values. An empty portfolio is worth 0, not an error."""
    return round(sum(values), 2)


def weights_pct(values: Sequence[float]) -> list[float]:
    """Each holding's share of the portfolio, as a percentage.

    Returns zeros rather than raising when the total is zero: a portfolio of
    not-yet-priced holdings is a real state, and a ZeroDivisionError in the middle
    of an agent is a worse answer than "0%".
    """
    total = sum(values)
    if not total:
        return [0.0 for _ in values]
    return [round(v / total * 100, 2) for v in values]


def class_breakdown(classes: Sequence[str], values: Sequence[float]) -> dict[str, float]:
    """Percentage of the portfolio in each asset class, largest first.

    Raises on mismatched lengths rather than zipping to the shorter sequence,
    which would quietly drop a holding and still return percentages summing
    to 100 — a wrong answer that looks right.
    """
    if len(classes) != len(values):
        raise ValueError("classes and values must be the same length")
    if not values:
        return {}

    totals: dict[str, float] = {}
    for asset_class, value in zip(classes, values, strict=True):
        totals[asset_class] = totals.get(asset_class, 0.0) + value

    grand = sum(totals.values())
    if not grand:
        return dict.fromkeys(totals, 0.0)

    ordered = sorted(totals.items(), key=lambda kv: -kv[1])
    return {name: round(value / grand * 100, 2) for name, value in ordered}


# ── concentration ──────────────────────────────────────────────────────────────


def _hhi_raw(weights: Sequence[float]) -> float:
    """Unrounded HHI, for internal use where rounding would compound.

    `diversification_score` needs full precision: rounding HHI to two places
    turns twelve equal holdings into an effective count of 12.5.
    """
    total = sum(weights)
    if not total:
        return 0.0
    return sum((w / total) ** 2 for w in weights)


def hhi(weights: Sequence[float]) -> float:
    """Herfindahl-Hirschman Index of concentration, 0 to 1.

    The sum of squared portfolio shares. 1.0 is everything in one holding; 1/n is
    n equal holdings. Normalised by the actual total, so it is correct whether the
    weights are percentages that sum to 100 or raw rupee values.

    Why this and not "how many holdings do you have": a portfolio of four, one of
    which is 97%, has the same count as four equal holdings and almost none of the
    diversification. HHI is sensitive to that; a count is blind to it. It is also
    the measure competition regulators use for market concentration, so it is
    citable rather than invented here.
    """
    return round(_hhi_raw(weights), 4)


def effective_holdings(hhi_value: float) -> float:
    """The reciprocal of HHI: how many equally-weighted holdings this behaves like.

    The number that makes HHI explainable to a beginner. "Your HHI is 0.34" means
    nothing; "you hold four things but it behaves like holding three" lands.
    """
    if not hhi_value:
        return 0.0
    return round(1 / hhi_value, 2)


def concentration_flags(
    names: Sequence[str], weights: Sequence[float], threshold_pct: float
) -> list[tuple[str, float]]:
    """Holdings above the threshold, largest first.

    The comparison is strictly greater than: a holding sitting exactly on the
    configured limit has not breached it. Threshold comes from
    `config.yaml: portfolio.concentration_warning_pct` — never hardcoded here,
    so changing the policy does not mean changing the maths.
    """
    if len(names) != len(weights):
        raise ValueError("names and weights must be the same length")
    flagged = [
        (name, weight)
        for name, weight in zip(names, weights, strict=True)
        if weight > threshold_pct
    ]
    return sorted(flagged, key=lambda nw: -nw[1])


def diversification_score(weights: Sequence[float], n_classes: int) -> int:
    """A 0-100 composite of three things, because no single one of them is enough.

    **Finnie's own heuristic, not a standard measure.** The components:

    * **Evenness** — normalised HHI, `(H - 1/n) / (1 - 1/n)`, inverted. This asks
      "given that you hold n things, how equally are they weighted?" Undefined at
      n = 1, where it is defined as 0.
    * **Breadth** — effective holdings against `BREADTH_TARGET`, capped at 1.
    * **Class spread** — distinct asset classes against `CLASS_SPREAD_TARGET`,
      capped at 1.

    Evenness alone is the trap worth knowing about: three equally-weighted IT
    stocks are perfectly even and not remotely diversified, and a naive `1 - HHI`
    score hands them 100. Breadth and class spread are what stop that, and
    `test_evenness_alone_does_not_earn_a_high_score` pins it.
    """
    n = len(weights)
    if n == 0 or not sum(weights):
        return 0

    h = _hhi_raw(weights)
    if n > 1:
        floor = 1 / n
        evenness = 1 - (h - floor) / (1 - floor)
    else:
        evenness = 0.0

    breadth = min(1.0, (1 / h if h else 0.0) / BREADTH_TARGET)
    class_spread = min(1.0, n_classes / CLASS_SPREAD_TARGET)

    composite = W_EVENNESS * evenness + W_BREADTH * breadth + W_CLASS * class_spread
    return round(max(0.0, min(1.0, composite)) * 100)


# ── risk ───────────────────────────────────────────────────────────────────────


def risk_score(class_weights: dict[str, float], risk_weights: dict[str, int]) -> float:
    """Weighted average asset-class risk, on the 1-5 scale from `config.yaml`.

    Risk here is *structural*, derived from what the portfolio holds — not from
    realised volatility. That is a deliberate limitation with two good reasons:
    it needs no price history, so it works on the first turn for a portfolio
    typed in by hand; and it is explainable in one sentence, which a beta or a
    standard deviation is not, to the beginner persona this is built for.

    What it therefore cannot see: that two stocks in the same sector are riskier
    together than apart. `diversification_score` is the partial answer to that.
    """
    total = sum(class_weights.values())
    if not total:
        return 0.0
    weighted = sum(
        weight * risk_weights.get(name, UNKNOWN_CLASS_RISK)
        for name, weight in class_weights.items()
    )
    return round(weighted / total, 2)


def risk_band(score: float) -> str:
    """Turn the 1-5 score into the vocabulary the rest of Finnie uses.

    The bands match `UserProfile.risk_appetite` and the `goals.risk_profiles`
    keys in `config.yaml` on purpose: the Goal agent can then compare a user's
    stated appetite with what they actually hold, which is a more interesting
    thing to say than either number alone.
    """
    if score <= 0:
        return "unknown"
    if score <= CONSERVATIVE_MAX:
        return "conservative"
    if score <= MODERATE_MAX:
        return "moderate"
    return "aggressive"


# ── expenses ───────────────────────────────────────────────────────────────────


def annual_expense_cost(pairs: Sequence[tuple[float, float | None]]) -> float:
    """Rupees per year lost to expense ratios, given (value, ratio_pct) pairs.

    The rupee figure leads because it is the one that means something. "Your
    expense ratio is 1.2%" is abstract; "these funds cost you ₹240 a year" is not,
    and it is the same fact.
    """
    return round(sum(value * ratio / 100 for value, ratio in pairs if ratio), 2)


def blended_expense_ratio(pairs: Sequence[tuple[float, float | None]]) -> float:
    """Total expense cost as a percentage of the *whole* portfolio."""
    total = sum(value for value, _ in pairs)
    if not total:
        return 0.0
    return round(annual_expense_cost(pairs) / total * 100, 2)


def fund_weighted_expense_ratio(pairs: Sequence[tuple[float, float | None]]) -> float:
    """Value-weighted expense ratio across only the holdings that charge one.

    Both this and `blended_expense_ratio` are reported, because each alone
    misleads: the blended figure makes an expensive fund look cheap when it is a
    small slice of the portfolio, and the fund-weighted figure overstates the drag
    on the portfolio as a whole. 1.2% is what the fund charges; 0.24% is what the
    portfolio pays.
    """
    charged = [(value, ratio) for value, ratio in pairs if ratio]
    invested = sum(value for value, _ in charged)
    if not invested:
        return 0.0
    return round(sum(value * ratio for value, ratio in charged) / invested, 2)


# ── profit and loss ────────────────────────────────────────────────────────────


def unrealised_pnl(value: float, cost: float | None) -> tuple[float, float] | None:
    """(absolute, percentage) gain or loss, or None without a cost basis.

    None rather than 0.0 when `cost` is absent: a user who did not enter purchase
    prices has an *unknown* P&L, and rendering that as "₹0 (0.00%)" would tell
    them they had broken even.
    """
    if cost is None:
        return None
    absolute = round(value - cost, 2)
    if not cost:
        return absolute, 0.0
    return absolute, round(absolute / cost * 100, 2)
