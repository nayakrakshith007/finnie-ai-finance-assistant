"""Indian number formatting for the UI (PRD §6.5a).

`₹12,50,000`, not `₹1,250,000`. Below a lakh the grouping is the familiar three
digits; from a lakh upward it is three digits and then pairs — 1,00,000 /
12,50,000 / 1,00,00,000. Python's `:,` does the Western thing, so this is hand
rolled.

It is a small module with a large blast radius: every number the user reads
passes through it, in the metrics, the tables, the chart labels and the hover
text. Western grouping on an Indian finance app does not read as a styling slip,
it reads as an app built for somewhere else.

`None` renders as an em dash throughout, never as zero. A missing cost basis
shown as ₹0 would tell the user they had broken even.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

RUPEE = "₹"
MISSING = "—"

LAKH = 1_00_000
CRORE = 1_00_00_000


def _round_half_up(value: float, places: int) -> Decimal:
    """Round the way a reader expects money to round.

    `Decimal` rather than arithmetic on the float, because the float is already
    inexact: 1234.5 is representable, but 2.675 is stored as 2.67499999..., and
    multiplying by 100 to round would produce 2.67 where 2.68 is intended.
    """
    quantum = Decimal(1).scaleb(-places)
    return Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def _group_indian(digits: str) -> str:
    """Insert separators Indian-style into a string of digits.

    The last three digits stay together; everything before them is grouped in
    twos, from the right. 1234567 -> 12,34,567.
    """
    if len(digits) <= 3:
        return digits

    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join([*pairs, tail])


def format_inr(value: float | int | None, *, paise: bool = False, symbol: bool = True) -> str:
    """An amount in rupees with Indian digit grouping.

    Args:
        value: the amount, or None for unknown.
        paise: keep two decimal places. Default off — a portfolio total to the
            paise is noise, but a NAV or a unit price without them is wrong.
        symbol: include ₹. Turn it off for a column already headed "Value (₹)".

    The sign goes before the symbol: -₹1,000 reads as a negative amount, while
    ₹-1,000 reads as a typo.
    """
    if value is None:
        return MISSING

    negative = value < 0
    magnitude = abs(float(value))

    if paise:
        whole, _, fraction = f"{_round_half_up(magnitude, 2):.2f}".partition(".")
        body = f"{_group_indian(whole)}.{fraction}"
    else:
        # Half-up, not Python's default banker's rounding. `round(1234.5)` is
        # 1234, which is correct for statistics and surprising for money: a user
        # reading ₹1,234.50 expects ₹1,235. Banker's rounding also makes a column
        # of displayed values stop summing to the displayed total.
        body = _group_indian(f"{int(_round_half_up(magnitude, 0)):d}")

    prefix = "-" if negative else ""
    return f"{prefix}{RUPEE if symbol else ''}{body}"


def format_inr_compact(value: float | int | None) -> str:
    """An amount as a reader would say it: ₹4.17 lakh, ₹1.79 crore.

    Used in metric tiles, where a glance has to be enough. Below a lakh there is
    nothing to compact and precision to lose, so small amounts are left exact.
    """
    if value is None:
        return MISSING

    negative = value < 0
    magnitude = abs(float(value))
    prefix = "-" if negative else ""

    if magnitude >= CRORE:
        return f"{prefix}{RUPEE}{magnitude / CRORE:.2f} crore"
    if magnitude >= LAKH:
        return f"{prefix}{RUPEE}{magnitude / LAKH:.2f} lakh"
    return format_inr(value)


def format_pct(value: float | None, *, places: int = 2) -> str:
    """A percentage, unsigned."""
    if value is None:
        return MISSING
    return f"{value:.{places}f}%"


def format_signed_pct(value: float | None, *, places: int = 2) -> str:
    """A percentage with an explicit + or -, for a change figure.

    Zero takes no sign: "+0.00%" reads as a small gain rather than as no change.
    """
    if value is None:
        return MISSING
    if value == 0:
        return f"{0:.{places}f}%"
    return f"{value:+.{places}f}%"
