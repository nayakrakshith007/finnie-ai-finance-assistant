"""Acceptance tests for Indian number formatting (PRD §6.5a visual rules).

"INR formatted with the Indian digit grouping (₹12,50,000, not ₹1,250,000)."

This is a small function with a large blast radius: it renders every number the
user reads, in the metrics, the tables, the charts and the narration. Western
grouping on an Indian finance app does not look like a styling slip — it looks
like the app was built for somewhere else, which for this project is the whole
point missed.
"""

from __future__ import annotations

import pytest

from web_app.formatting import format_inr, format_inr_compact, format_pct, format_signed_pct

# ── the 2-2-3 grouping ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "₹0"),
        (7, "₹7"),
        (100, "₹100"),
        (999, "₹999"),
        (1_000, "₹1,000"),
        (10_000, "₹10,000"),
        (99_999, "₹99,999"),
        # From a lakh upward the grouping changes: three digits, then twos.
        (1_00_000, "₹1,00,000"),
        (12_50_000, "₹12,50,000"),
        (10_00_000, "₹10,00,000"),
        (1_00_00_000, "₹1,00,00,000"),
        (17_90_847, "₹17,90,847"),
        (4_17_468, "₹4,17,468"),
        (1_00_00_00_000, "₹1,00,00,00,000"),
    ],
)
def test_amounts_use_the_indian_digit_grouping(value, expected):
    assert format_inr(value) == expected


def test_the_western_grouping_is_not_used():
    """The specific thing being prevented: ₹12,50,000 and not ₹1,250,000."""
    assert format_inr(12_50_000) != "₹1,250,000"
    assert format_inr(1_00_00_000) != "₹10,000,000"


def test_rounding_is_to_the_rupee_by_default():
    assert format_inr(1_234.49) == "₹1,234"
    assert format_inr(1_234.50) == "₹1,235"


def test_paise_are_shown_when_asked_for():
    """Needed for a NAV or a unit price, where the paise are the information."""
    assert format_inr(1_234.56, paise=True) == "₹1,234.56"
    assert format_inr(168.4, paise=True) == "₹168.40"


def test_a_negative_amount_puts_the_sign_before_the_symbol():
    """−₹1,000 reads as a negative amount; ₹−1,000 reads as a typo."""
    assert format_inr(-1_000) == "-₹1,000"
    assert format_inr(-12_50_000) == "-₹12,50,000"


def test_the_symbol_can_be_dropped_for_a_table_column():
    """A column already headed "Value (₹)" should not repeat the symbol per row."""
    assert format_inr(12_50_000, symbol=False) == "12,50,000"


def test_none_renders_as_an_em_dash_not_zero():
    """An unknown value is not zero. Rendering a missing cost basis as ₹0 would
    tell the user they had broken even."""
    assert format_inr(None) == "—"


# ── lakh and crore, for metric tiles ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "₹0"),
        (999, "₹999"),
        (50_000, "₹50,000"),
        (99_999, "₹99,999"),
        (1_00_000, "₹1.00 lakh"),
        (4_17_468, "₹4.17 lakh"),
        (17_90_848, "₹17.91 lakh"),
        (99_99_999, "₹100.00 lakh"),
        (1_00_00_000, "₹1.00 crore"),
        (1_79_08_477, "₹1.79 crore"),
        (10_00_00_000, "₹10.00 crore"),
    ],
)
def test_large_amounts_compact_to_lakh_and_crore(value, expected):
    """How an Indian reader actually says these numbers. "₹1.79 crore" is
    legible at a glance in a metric tile; "₹1,79,08,477" is not."""
    assert format_inr_compact(value) == expected


def test_compact_keeps_small_amounts_exact():
    """Below a lakh there is nothing to gain and precision to lose."""
    assert format_inr_compact(45_670) == "₹45,670"


def test_compact_handles_negatives():
    assert format_inr_compact(-1_79_08_477) == "-₹1.79 crore"


def test_compact_none_is_an_em_dash():
    assert format_inr_compact(None) == "—"


# ── percentages ────────────────────────────────────────────────────────────────


def test_percentages_carry_two_decimals_and_a_sign_where_it_matters():
    assert format_pct(7.14) == "7.14%"
    assert format_pct(0) == "0.00%"
    assert format_signed_pct(1.35) == "+1.35%"
    assert format_signed_pct(-0.04) == "-0.04%"
    assert format_signed_pct(0) == "0.00%", "zero takes no sign; +0.00% reads as a gain"


def test_percent_none_is_an_em_dash():
    assert format_pct(None) == "—"
    assert format_signed_pct(None) == "—"


def test_percentages_can_be_given_fewer_decimals():
    assert format_pct(7.14, places=0) == "7%"
    assert format_pct(7.56, places=1) == "7.6%"
