"""Holdings: the model, and turning untrusted input into it (PRD FR-012, FR-062).

Why the parser collects errors instead of raising
-------------------------------------------------
A broker CSV export is twenty lines with one typo in it. Raising on the first bad
row means the user fixes one typo, re-uploads, and discovers the next — which is
the worst possible version of this interaction. So `parse_holdings` returns
`(holdings, errors)`: everything it could understand, plus a specific, numbered
complaint about everything it could not. FR-062 asks for a *specific, friendly*
error, and "row 3: quantity 'ten' is not a number" is both; `ValueError: could
not convert string to float: 'ten'` is neither.

Symbols are normalised here, at the boundary, using the same function the market
data layer uses. Doing it once on the way in means nothing downstream has to
remember whether it is holding `reliance` or `RELIANCE.NS`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from core.logging_setup import get_logger
from data.market import OutOfScopeError, normalise_symbol

logger = get_logger(__name__)

# The asset classes Finnie understands. These are exactly the keys of
# `portfolio.risk_weights` in config.yaml -- adding one here without adding it
# there would make it score as UNKNOWN_CLASS_RISK, so the two lists are one list.
#
# Indian instruments map onto them as follows: SGBs and PPF/EPF balances are
# `bond` (sovereign, fixed return), index and gold ETFs are `etf`, SIPs are
# `mutual_fund`, and an emergency fund or liquid-fund balance is `cash`.
ASSET_CLASSES: tuple[str, ...] = ("cash", "bond", "etf", "mutual_fund", "stock", "crypto")

DEFAULT_ASSET_CLASS = "stock"

REQUIRED_COLUMNS = ("symbol", "quantity")

# Only these classes are looked up on an exchange, so only these get a `.NS`
# suffix. A mutual fund, an SGB holding or a bank balance has no ticker, and
# normalising "HDFCFLEXI" to "HDFCFLEXI.NS" would send yfinance looking for a
# listing that does not exist -- the holding would then land in `unpriced` and
# silently drop out of the user's total. Those carry a user-supplied `price`
# (the NAV or balance) instead.
MARKET_TRADED_CLASSES = frozenset({"stock", "etf"})

# A demo portfolio for the one-click button (FR-062). Deliberately imperfect, and
# verified against the real analysis on 2026-11-08 rather than assumed: it values
# at about ₹4.17 lakh and comes out 35.6% in one sovereign gold bond, which trips
# the concentration flag; 23.5% in three stocks; and spread over all five asset
# classes, which gives the allocation pie (FR-063) something to show. Effective
# holdings 4.81 against seven positions, diversification 73/100, risk band
# moderate, ₹829/year in fund fees, and a mix of live, cached and user-supplied
# prices so the provenance labels are visible too.
#
# A perfectly balanced sample would make the concentration flag and the
# diversification score look like decoration. If you edit these rows, re-run the
# analysis and update these numbers — a comment describing a portfolio that no
# longer exists is worse than no comment.
SAMPLE_PORTFOLIO: tuple[dict[str, Any], ...] = (
    {"symbol": "RELIANCE.NS", "quantity": 25, "asset_class": "stock", "avg_cost": 1180,
     "name": "Reliance Industries"},
    {"symbol": "TCS.NS", "quantity": 12, "asset_class": "stock", "avg_cost": 3100,
     "name": "Tata Consultancy Services"},
    {"symbol": "INFY.NS", "quantity": 30, "asset_class": "stock", "avg_cost": 1450,
     "name": "Infosys"},
    {"symbol": "NIFTYBEES.NS", "quantity": 100, "asset_class": "etf", "avg_cost": 245,
     "expense_ratio": 0.05, "name": "Nippon India NIFTY 50 ETF"},
    # No ticker, so these carry their own NAV/balance rather than being looked up.
    {"symbol": "HDFCFLEXI", "quantity": 400, "asset_class": "mutual_fund", "avg_cost": 142,
     "price": 168.4, "expense_ratio": 1.21, "name": "HDFC Flexi Cap Fund (Direct)"},
    {"symbol": "SGBAUG32", "quantity": 20, "asset_class": "bond", "avg_cost": 6150,
     "price": 7420, "name": "Sovereign Gold Bond 2032"},
    {"symbol": "LIQUIDCASH", "quantity": 75000, "asset_class": "cash", "avg_cost": 1,
     "price": 1, "name": "Emergency fund (sweep account)"},
)


@dataclass(frozen=True)
class Holding:
    """One position. Frozen: an analysis must not mutate its own input."""

    symbol: str
    quantity: float
    asset_class: str = DEFAULT_ASSET_CLASS
    avg_cost: float | None = None  # per unit, in INR
    price: float | None = None  # current unit price/NAV, for instruments with no ticker
    expense_ratio: float | None = None  # annual percentage, funds and ETFs only
    name: str = ""

    @property
    def cost_basis(self) -> float | None:
        """Total paid, or None when the user did not supply a purchase price."""
        if self.avg_cost is None:
            return None
        return round(self.quantity * self.avg_cost, 2)


# ── parsing ───────────────────────────────────────────────────────────────────


def _clean_asset_class(raw: Any) -> str:
    """'  Mutual Fund ' -> 'mutual_fund'. Users type labels, not identifiers."""
    if raw is None:
        return DEFAULT_ASSET_CLASS
    # NaN from a pandas float64 column (data_editor with no value set) — raw != raw is True only for NaN
    if isinstance(raw, float) and raw != raw:
        return DEFAULT_ASSET_CLASS
    text = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    return text or DEFAULT_ASSET_CLASS


def _parse_number(raw: Any, field: str, row_no: int, errors: list[str]) -> float | None:
    """Parse an optional number, recording a readable complaint on failure."""
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip().replace(",", "").replace("₹", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        errors.append(f"row {row_no}: {field} {str(raw).strip()!r} is not a number")
        return None


def parse_holdings(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Holding], list[str]]:
    """Validate rows into holdings, merging duplicates.

    Returns `(holdings, errors)`. Row numbers in errors are 1-based and count the
    data rows the user sees, not including a CSV header.
    """
    holdings: list[Holding] = []
    errors: list[str] = []
    index: dict[str, int] = {}  # symbol -> position in `holdings`, for merging

    for row_no, row in enumerate(rows, start=1):
        raw_symbol = str(row.get("symbol") or "").strip()
        if not raw_symbol:
            errors.append(f"row {row_no}: symbol is missing")
            continue

        asset_class = _clean_asset_class(row.get("asset_class"))
        if asset_class not in ASSET_CLASSES:
            errors.append(
                f"row {row_no}: asset_class {asset_class!r} is not one of "
                f"{', '.join(ASSET_CLASSES)}"
            )
            continue

        if asset_class in MARKET_TRADED_CLASSES:
            try:
                symbol = normalise_symbol(raw_symbol)
            except OutOfScopeError:
                errors.append(f"row {row_no}: symbol {raw_symbol!r} is not usable")
                continue
        else:
            # No exchange lookup, so no suffix: the label is whatever the user
            # calls this fund or account.
            symbol = raw_symbol.upper()

        row_errors: list[str] = []
        quantity = _parse_number(row.get("quantity"), "quantity", row_no, row_errors)
        if row_errors:
            errors.extend(row_errors)
            continue
        if quantity is None:
            errors.append(f"row {row_no}: quantity is missing")
            continue
        if quantity <= 0:
            errors.append(
                f"row {row_no}: quantity {quantity:g} must be positive "
                "(a zero or negative holding is almost always a typo)"
            )
            continue

        avg_cost = _parse_number(row.get("avg_cost"), "avg_cost", row_no, errors)
        expense_ratio = _parse_number(
            row.get("expense_ratio"), "expense_ratio", row_no, errors
        )
        price = _parse_number(row.get("price"), "price", row_no, errors)

        holding = Holding(
            symbol=symbol,
            quantity=quantity,
            asset_class=asset_class,
            avg_cost=avg_cost,
            price=price,
            expense_ratio=expense_ratio,
            name=str(row.get("name") or "").strip(),
        )

        if symbol in index:
            holdings[index[symbol]] = _merge(holdings[index[symbol]], holding)
        else:
            index[symbol] = len(holdings)
            holdings.append(holding)

    if errors:
        logger.info("Parsed %d holdings with %d rejected rows", len(holdings), len(errors))
    return holdings, errors


def _merge(existing: Holding, incoming: Holding) -> Holding:
    """Combine two rows for the same symbol.

    Quantities add; average cost is the *weighted* mean, which is the only
    correct answer — averaging the two prices would ignore how much was bought at
    each. When one side has no cost basis the known one is kept rather than
    discarded, so a partially-documented position keeps what documentation it has.
    """
    quantity = existing.quantity + incoming.quantity
    costs = [(h.quantity, h.avg_cost) for h in (existing, incoming) if h.avg_cost is not None]
    if costs:
        known_qty = sum(q for q, _ in costs)
        avg_cost = round(sum(q * c for q, c in costs) / known_qty, 4) if known_qty else None
    else:
        avg_cost = None

    return replace(
        existing,
        quantity=quantity,
        avg_cost=avg_cost,
        price=existing.price or incoming.price,
        expense_ratio=existing.expense_ratio or incoming.expense_ratio,
        name=existing.name or incoming.name,
    )


def parse_portfolio_csv(text: str) -> tuple[list[Holding], list[str]]:
    """Parse an uploaded CSV. Header names are normalised; blank lines are ignored."""
    if not text or not text.strip():
        return [], ["The file is empty. Expected columns: symbol, quantity, asset_class."]

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["The file has no header row. Expected: symbol, quantity, asset_class."]

    # "Asset Class" / " Quantity " -> asset_class / quantity. Broker exports
    # capitalise and pad headers freely, and rejecting a real export over a
    # capital letter would be an own goal.
    mapping = {name: _clean_asset_class(name) for name in reader.fieldnames if name}

    missing = [c for c in REQUIRED_COLUMNS if c not in mapping.values()]
    if missing:
        return [], [
            f"The file is missing required column(s): {', '.join(missing)}. "
            f"Expected: {', '.join(REQUIRED_COLUMNS)}, and optionally asset_class, "
            "avg_cost, price, expense_ratio, name."
        ]

    rows = []
    for raw in reader:
        row = {mapping.get(k, k): v for k, v in raw.items() if k}
        if not any(str(v or "").strip() for v in row.values()):
            continue  # a blank line, which every spreadsheet export leaves behind
        rows.append(row)

    if not rows:
        return [], ["The file has a header but no holdings in it."]

    return parse_holdings(rows)
