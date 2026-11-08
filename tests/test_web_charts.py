"""Acceptance tests for the Plotly charts (PRD FR-063, §6.5a, NFR-07).

The charts are built by pure functions that take the agents' state dicts and
return a `go.Figure`, so the visual rules the PRD states are *checkable* rather
than aspirational:

    "every chart titled and axis-labelled, INR-formatted" (FR-063)
    "no chart relies on colour alone to carry meaning" (NFR-07)

A figure object is inspectable — titles, axis labels, trace names, text labels
and marker patterns are all attributes. So "every chart has an axis label" is a
test, not a hope, and it stays true when someone adds a fifth chart.
"""

from __future__ import annotations

import pytest

from web_app.charts import (
    allocation_pie,
    asset_class_bar,
    goal_projection_area,
    price_trend_line,
)

ANALYSIS = {
    "total_value": 1_13_085.60,
    "currency": "INR",
    "holdings": [
        {"symbol": "RELIANCE.NS", "name": "Reliance", "asset_class": "stock",
         "value": 33_100.0, "weight_pct": 29.27, "quantity": 25, "price": 1324.0,
         "source": "live", "is_degraded": False},
        {"symbol": "TCS.NS", "name": "TCS", "asset_class": "stock",
         "value": 29_985.6, "weight_pct": 26.52, "quantity": 12, "price": 2498.8,
         "source": "cache", "is_degraded": False},
        {"symbol": "LIQUIDCASH", "name": "Emergency fund", "asset_class": "cash",
         "value": 50_000.0, "weight_pct": 44.21, "quantity": 50_000, "price": 1.0,
         "source": "user", "is_degraded": False},
    ],
    # Deliberately NOT largest-first: the real agent sorts, but the bar chart must
    # not depend on that, so this fixture hands it the awkward order on purpose.
    "class_breakdown": {"cash": 44.21, "stock": 55.79},
}

TRENDS = {
    "30d": {"days": 30, "direction": "up", "change_pct": 7.99,
            "start_price": 1226.0, "end_price": 1324.0, "high": 1324.0, "low": 1158.0,
            "closes": [1226.0, 1250.0, 1198.0, 1158.0, 1290.0, 1324.0]},
}

PROJECTION = [
    {"year": 0, "value": 0.0, "contributed": 0.0, "growth": 0.0},
    {"year": 1, "value": 1_28_093.28, "contributed": 1_20_000.0, "growth": 8_093.28},
    {"year": 2, "value": 2_72_432.0, "contributed": 2_40_000.0, "growth": 32_432.0},
    {"year": 3, "value": 4_35_076.47, "contributed": 3_60_000.0, "growth": 75_076.47},
]


def all_charts():
    return [
        allocation_pie(ANALYSIS),
        asset_class_bar(ANALYSIS),
        price_trend_line("RELIANCE.NS", TRENDS),
        goal_projection_area(PROJECTION, target=10_00_000.0),
    ]


# ── FR-063: every chart titled and labelled ────────────────────────────────────


@pytest.mark.parametrize("figure", all_charts())
def test_every_chart_has_a_title(figure):
    assert figure.layout.title.text, "an untitled chart in a report is a decoration"


@pytest.mark.parametrize("figure", all_charts())
def test_every_chart_has_at_least_one_trace(figure):
    assert len(figure.data) >= 1


def test_the_cartesian_charts_have_axis_labels():
    """A pie has no axes; a bar, a line and an area chart have no excuse."""
    for figure in (
        asset_class_bar(ANALYSIS),
        price_trend_line("RELIANCE.NS", TRENDS),
        goal_projection_area(PROJECTION, target=10_00_000.0),
    ):
        assert figure.layout.xaxis.title.text, f"{figure.layout.title.text}: no x label"
        assert figure.layout.yaxis.title.text, f"{figure.layout.title.text}: no y label"


def test_rupee_axes_say_so():
    """A y-axis of large bare numbers is unreadable; the unit belongs in the label."""
    for figure in (asset_class_bar(ANALYSIS), goal_projection_area(PROJECTION, target=0)):
        labels = f"{figure.layout.xaxis.title.text} {figure.layout.yaxis.title.text}"
        assert "₹" in labels or "%" in labels


# ── NFR-07: no chart relies on colour alone ────────────────────────────────────


def test_the_pie_labels_each_slice_in_text():
    """A pie distinguished only by colour is unreadable to a colour-blind reader
    and in a greyscale print of the report."""
    figure = allocation_pie(ANALYSIS)
    trace = figure.data[0]
    assert trace.textinfo and "label" in trace.textinfo
    assert "percent" in trace.textinfo


def test_the_bar_chart_prints_its_values():
    figure = asset_class_bar(ANALYSIS)
    assert figure.data[0].text is not None, "bar values must be readable without the axis"


def test_the_projection_traces_are_named_and_shown_in_a_legend():
    """Contributions versus growth is the whole point of the chart, so the two
    bands must be distinguishable by label rather than by shade."""
    figure = goal_projection_area(PROJECTION, target=10_00_000.0)
    names = [trace.name for trace in figure.data if trace.name]
    assert "Your contributions" in names
    assert "Growth" in names
    assert figure.layout.showlegend is not False


def test_the_trend_line_names_its_series():
    figure = price_trend_line("RELIANCE.NS", TRENDS)
    assert any(trace.name for trace in figure.data)


# ── content ────────────────────────────────────────────────────────────────────


def test_the_pie_uses_holding_names_and_values():
    figure = allocation_pie(ANALYSIS)
    labels = list(figure.data[0].labels)
    assert "Reliance" in labels
    assert "Emergency fund" in labels
    assert pytest.approx(sum(figure.data[0].values), rel=1e-6) == 1_13_085.6


def test_the_pie_hover_shows_indian_formatted_rupees():
    figure = allocation_pie(ANALYSIS)
    hover = " ".join(figure.data[0].hovertext)
    assert "₹50,000" in hover, "Indian grouping in the hover text too"


def test_the_bar_chart_is_ordered_largest_first():
    """Matches the order of `class_breakdown`, which the agent already sorted."""
    figure = asset_class_bar(ANALYSIS)
    assert list(figure.data[0].x) == ["stock", "cash"]


def test_the_trend_line_plots_every_close():
    figure = price_trend_line("RELIANCE.NS", TRENDS)
    assert len(figure.data[0].y) == len(TRENDS["30d"]["closes"])


def test_the_projection_target_is_drawn_as_a_reference_line():
    """The question the chart answers is "do I get there?", which needs a there."""
    figure = goal_projection_area(PROJECTION, target=10_00_000.0)
    assert figure.layout.shapes or any(
        getattr(trace, "name", "") == "Target" for trace in figure.data
    )


def test_the_projection_stacks_contributions_and_growth():
    figure = goal_projection_area(PROJECTION, target=10_00_000.0)
    stacked = [trace for trace in figure.data if getattr(trace, "stackgroup", None)]
    assert len(stacked) == 2, "contributions and growth must stack to the total"


# ── empty and degraded inputs ──────────────────────────────────────────────────


def test_an_empty_portfolio_still_produces_a_titled_figure():
    """A new user has no holdings. The tab must render something, not raise."""
    empty = {"total_value": 0.0, "currency": "INR", "holdings": [], "class_breakdown": {}}
    for figure in (allocation_pie(empty), asset_class_bar(empty)):
        assert figure.layout.title.text
        assert figure.layout.annotations, "an empty chart should say that it is empty"


def test_a_missing_trend_window_produces_an_empty_titled_figure():
    figure = price_trend_line("RELIANCE.NS", {})
    assert figure.layout.title.text
    assert figure.layout.annotations


def test_an_empty_projection_does_not_raise():
    figure = goal_projection_area([], target=0)
    assert figure.layout.title.text


def test_a_degraded_price_is_flagged_on_the_trend_chart():
    """FR-033 again: provenance travels with the number, including onto a chart."""
    figure = price_trend_line("RELIANCE.NS", TRENDS, freshness="as of 14:32 — STALE")
    text = f"{figure.layout.title.text} {[a.text for a in figure.layout.annotations]}"
    assert "STALE" in text


def test_the_charts_do_not_mutate_their_input():
    """They are handed state dicts that other code reads afterwards."""
    import copy

    snapshot = copy.deepcopy(ANALYSIS)
    allocation_pie(ANALYSIS)
    asset_class_bar(ANALYSIS)
    assert snapshot == ANALYSIS


# ── the palette ────────────────────────────────────────────────────────────────


def test_one_accent_and_one_warning_colour_only():
    """§6.5a: "one accent colour and one warning colour only".

    A categorical chart needs a few hues, but the *semantic* colours are two, and
    a third would stop either meaning anything.
    """
    from web_app.charts import ACCENT, SEMANTIC_COLOURS, WARNING

    assert SEMANTIC_COLOURS == (ACCENT, WARNING)


# ── the trend axis must show the movement (found in the browser 2026-11-08) ───


def test_the_trend_y_axis_is_not_anchored_at_zero():
    """A price chart filled to ₹0 renders a real 8% month as a flat line.

    Found by looking at NIFTY in the browser: the series sat at the top of the
    chart with the whole plot area below it empty, and the movement the Market
    tab exists to show was invisible. A non-zero baseline is the standard choice
    for a price series — the range annotation carries the absolute context.
    """
    figure = price_trend_line("RELIANCE.NS", TRENDS)
    low, high = figure.layout.yaxis.range

    assert low > 0, "the axis must not start at zero"
    assert low < min(TRENDS["30d"]["closes"]), "the lowest close must be visible"
    assert high > max(TRENDS["30d"]["closes"]), "the highest close must be visible"


def test_the_trend_axis_covers_the_whole_series_with_headroom():
    figure = price_trend_line("RELIANCE.NS", TRENDS)
    low, high = figure.layout.yaxis.range
    span = max(TRENDS["30d"]["closes"]) - min(TRENDS["30d"]["closes"])

    assert (high - low) > span, "the range must have padding beyond the data"
    assert (high - low) < span * 3, "but not so much that the movement flattens again"


def test_a_flat_series_still_gets_a_usable_range():
    """A stock that did not move must not produce a zero-height axis."""
    flat = {"30d": {"days": 30, "direction": "flat", "change_pct": 0.0,
                    "start_price": 100.0, "end_price": 100.0, "high": 100.0, "low": 100.0,
                    "closes": [100.0, 100.0, 100.0]}}
    low, high = price_trend_line("X.NS", flat).layout.yaxis.range
    assert high > low


def test_the_pie_labels_sit_outside_the_slices():
    """Seven holdings with long names do not fit inside a slice; Plotly's answer
    to that is to rotate the text vertically, which was unreadable in the
    browser. Outside labels with leader lines keep every slice named."""
    trace = allocation_pie(ANALYSIS).data[0]
    assert trace.textposition == "outside"


# ── rupee axes use Indian grouping (found in the browser 2026-11-08) ──────────


def test_the_corpus_axis_labels_use_indian_formatting():
    """The metric above the chart read ₹17.91 lakh while the axis beside it read
    ₹1,500,000 — the same number formatted two ways, two inches apart.

    Plotly's `tickformat` speaks d3-format, which has no Indian digit grouping,
    so the ticks are computed and labelled with Finnie's own formatter.
    """
    figure = goal_projection_area(PROJECTION, target=10_00_000.0)
    labels = list(figure.layout.yaxis.ticktext)

    assert labels, "the axis must have explicit labels"
    assert all(label.startswith(("₹", "-₹")) for label in labels)
    assert not any("," in label and "lakh" not in label and len(label) > 8 for label in labels), (
        f"Western grouping leaked into {labels}"
    )


def test_the_price_axis_labels_use_indian_formatting():
    figure = price_trend_line("RELIANCE.NS", TRENDS)
    labels = list(figure.layout.yaxis.ticktext)
    assert labels
    assert all(label.startswith("₹") for label in labels)


def test_a_six_figure_price_axis_groups_the_indian_way():
    """At five digits Indian and Western grouping agree, so the bug hid at NIFTY
    levels. It only shows from a lakh up — hence this case."""
    big = {"30d": {"days": 30, "direction": "up", "change_pct": 5.0,
                   "start_price": 1_00_000.0, "end_price": 1_05_000.0,
                   "high": 1_05_000.0, "low": 1_00_000.0,
                   "closes": [1_00_000.0, 1_02_000.0, 1_05_000.0]}}
    labels = list(price_trend_line("X.NS", big).layout.yaxis.ticktext)
    joined = " ".join(labels)
    assert "1,00,000" in joined or "1,05,000" in joined, joined
    assert "100,000" not in joined and "105,000" not in joined


def test_the_axis_ticks_span_the_data():
    figure = goal_projection_area(PROJECTION, target=10_00_000.0)
    values = list(figure.layout.yaxis.tickvals)
    assert max(values) >= max(p["value"] for p in PROJECTION) * 0.8
