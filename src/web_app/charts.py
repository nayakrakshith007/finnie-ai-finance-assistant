"""Plotly figures for the UI (PRD FR-063, §6.5a, NFR-07).

Pure functions: each takes a state dict an agent produced and returns a
`go.Figure`. They touch no Streamlit, so `tests/test_web_charts.py` can assert on
titles, axis labels, trace names and text labels — which turns the PRD's visual
rules into tests instead of intentions:

* every chart titled and axis-labelled (FR-063);
* no chart relying on colour alone (NFR-07);
* INR in Indian digit grouping, including in hover text (§6.5a).

Taking the agents' dicts directly rather than re-deriving anything matters for a
reason beyond convenience: the percentages on the chart and the percentages in
the narration then come from the same arithmetic, so the pie cannot disagree with
the paragraph beside it.

Every function handles the empty case by returning a titled figure with an
annotation saying it is empty. A new user has no holdings, and a tab that raises
on its first render is worse than one that says "nothing here yet".
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from web_app.formatting import format_inr, format_inr_compact, format_signed_pct

# §6.5a: one accent colour and one warning colour. A third semantic colour would
# stop either of them meaning anything.
ACCENT = "#0F766E"  # teal: Finnie's own
WARNING = "#B45309"  # amber: degraded data, concentration, anything to look at
SEMANTIC_COLOURS: tuple[str, str] = (ACCENT, WARNING)

# Categorical hues for pie slices and bars. Not semantic — they only separate
# categories, which is why every such chart also carries text labels (NFR-07).
CATEGORY_COLOURS = (
    "#0F766E", "#0E7490", "#4338CA", "#7E22CE",
    "#A16207", "#B45309", "#15803D", "#1D4ED8",
)

NEUTRAL_GRID = "rgba(128,128,128,0.18)"
EMPTY_NOTE = "Nothing to show yet"


def _base_layout(figure: go.Figure, title: str) -> go.Figure:
    figure.update_layout(
        title={"text": title, "x": 0.0, "xanchor": "left"},
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel={"align": "left"},
    )
    figure.update_xaxes(gridcolor=NEUTRAL_GRID, zeroline=False)
    figure.update_yaxes(gridcolor=NEUTRAL_GRID, zeroline=False)
    return figure


def _rupee_ticks(low: float, high: float, *, compact: bool, count: int = 6) -> dict[str, Any]:
    """Explicit tick values and Indian-formatted labels for a rupee axis.

    Plotly's `tickformat` speaks d3-format, which has no Indian digit grouping:
    `","` produces ₹1,500,000. That put Western grouping on the chart axis while
    the metric above it read ₹17.91 lakh — the same number, formatted two
    different ways, two inches apart. Spotted in the browser on 2026-11-08.

    So the ticks are computed here and labelled with Finnie's own formatter.
    """
    if high <= low:
        high = low + 1

    # A round step, so the ticks land on readable numbers rather than on
    # 1,23,456.78 at even intervals.
    rough = (high - low) / max(count - 1, 1)
    magnitude = 10 ** int(f"{rough:e}".split("e")[1])
    step = next(
        (m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= rough), 10 * magnitude
    )

    start = step * int(low / step)
    values: list[float] = []
    value = start
    while value <= high + step * 0.5:
        if value >= low - step * 0.5:
            values.append(round(value, 2))
        value += step

    formatter = format_inr_compact if compact else format_inr
    return {"tickmode": "array", "tickvals": values, "ticktext": [formatter(v) for v in values]}


def _empty(title: str, note: str = EMPTY_NOTE) -> go.Figure:
    """A titled, labelled figure that says it has no data."""
    figure = go.Figure()
    figure.add_annotation(
        text=note, showarrow=False, font={"size": 14, "color": "grey"},
        xref="paper", yref="paper", x=0.5, y=0.5,
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return _base_layout(figure, title)


# ── portfolio ──────────────────────────────────────────────────────────────────


def allocation_pie(analysis: dict[str, Any]) -> go.Figure:
    """Holdings by value (§6.5a: the Portfolio tab's primary element).

    `textinfo="label+percent"` is not decoration: a pie whose slices are
    distinguished only by hue is unreadable to a colour-blind reader and in a
    greyscale print, so every slice carries its own name and share (NFR-07).
    """
    holdings = list(analysis.get("holdings") or [])
    if not holdings:
        return _empty("Allocation by holding", "No holdings yet — add some in this tab")

    labels = [h.get("name") or h["symbol"] for h in holdings]
    values = [h["value"] for h in holdings]
    hover = [
        f"{h.get('name') or h['symbol']}<br>{format_inr(h['value'])}"
        f"<br>{h['weight_pct']:.2f}% of portfolio"
        f"<br>{h['quantity']:g} × {format_inr(h['price'], paise=True)}"
        + ("<br>⚠ price not current" if h.get("is_degraded") else "")
        for h in holdings
    ]

    figure = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hovertext=hover,
            hoverinfo="text",
            textinfo="label+percent",
            # Outside with leader lines, not "auto". Seven holdings with names
            # like "Sovereign Gold Bond 2032" do not fit inside a slice, and
            # Plotly's response to that is to rotate the text vertically — which
            # was unreadable on a real portfolio in the browser. Outside labels
            # keep NFR-07 satisfied (every slice named in text, not by colour
            # alone) without the rotation.
            textposition="outside",
            automargin=True,
            marker={
                "colors": list(CATEGORY_COLOURS[: len(labels)]),
                "line": {"color": "white", "width": 1},
            },
            sort=False,  # the agent already ordered these; re-sorting would desync
            hole=0.45,
        )
    )
    total = format_inr_compact(analysis.get("total_value"))
    figure = _base_layout(figure, f"Allocation by holding · {total} total")
    # Room for the leader lines; without it the outside labels are clipped.
    figure.update_layout(height=460, margin={"l": 80, "r": 80, "t": 60, "b": 40})
    return figure


def asset_class_bar(analysis: dict[str, Any]) -> go.Figure:
    """Share of the portfolio by asset class, largest first."""
    breakdown = dict(analysis.get("class_breakdown") or {})
    if not breakdown:
        return _empty("Allocation by asset class", "No holdings yet")

    # Sorted here rather than trusting the caller. The portfolio agent does order
    # it largest-first, but a chart that promises an ordering should enforce it:
    # the alternative is a chart whose correctness depends on an upstream detail
    # nobody will remember when that agent is next edited.
    ordered = sorted(breakdown.items(), key=lambda kv: -kv[1])
    names = [name for name, _ in ordered]
    shares = [share for _, share in ordered]

    figure = go.Figure(
        go.Bar(
            x=names,
            y=shares,
            text=[f"{s:.1f}%" for s in shares],  # readable without the axis
            textposition="outside",
            marker_color=list(CATEGORY_COLOURS[: len(names)]),
            hovertemplate="%{x}<br>%{y:.2f}% of portfolio<extra></extra>",
        )
    )
    figure.update_layout(yaxis_range=[0, max(shares) * 1.18])
    figure.update_xaxes(title_text="Asset class")
    figure.update_yaxes(title_text="Share of portfolio (%)")
    return _base_layout(figure, "Allocation by asset class")


# ── market ─────────────────────────────────────────────────────────────────────


def price_trend_line(
    symbol: str, trends: dict[str, Any], *, window: str = "30d", freshness: str = ""
) -> go.Figure:
    """Closing prices over one window (§6.5a: the Market tab's primary element)."""
    trend = (trends or {}).get(window)
    title = f"{symbol} · {window} price trend"
    if freshness:
        # FR-033: provenance travels with the number, onto the chart as well.
        title += f" · {freshness}"

    if not trend or not trend.get("closes"):
        return _empty(title, f"No price history available for {symbol}")

    closes = list(trend["closes"])
    # x is sessions-ago rather than dates: yfinance gives a calendar window whose
    # session count varies, and inventing dates for the gaps would be a lie.
    sessions = list(range(-(len(closes) - 1), 1))
    direction = trend.get("direction", "flat")
    colour = ACCENT if direction != "down" else WARNING

    figure = go.Figure(
        go.Scatter(
            x=sessions,
            y=closes,
            mode="lines+markers",
            name=f"{symbol} close",
            line={"color": colour, "width": 2},
            marker={"size": 4},
            hovertemplate="%{x} sessions ago<br>₹%{y:,.2f}<extra></extra>",
        )
    )
    figure.add_annotation(
        text=(
            f"{direction} {format_signed_pct(trend.get('change_pct'))} over {window} · "
            f"range {format_inr(trend.get('low'))}–{format_inr(trend.get('high'))}"
        ),
        showarrow=False,
        xref="paper", yref="paper", x=0.0, y=1.08, xanchor="left",
        font={"size": 12, "color": "grey"},
    )
    figure.update_xaxes(title_text="Trading sessions ago")
    # Autoscaled to the data, NOT anchored at zero. An earlier version filled to
    # zero, which rendered NIFTY's real 8% month as a flat line at the top of the
    # chart — the movement the tab exists to show, invisible. A non-zero baseline
    # exaggerates movement and is the classic misleading-chart critique, but for
    # a *price* series it is the standard and correct choice: nobody plots a
    # share price from ₹0. The range annotation above gives the absolute context
    # that the axis no longer carries.
    low, high = min(closes), max(closes)
    padding = max((high - low) * 0.12, high * 0.002)
    figure.update_yaxes(
        title_text="Close (₹)",
        range=[low - padding, high + padding],
        **_rupee_ticks(low - padding, high + padding, compact=False),
    )
    return _base_layout(figure, title)


# ── goals ──────────────────────────────────────────────────────────────────────


def goal_projection_area(projection: list[dict[str, Any]], *, target: float) -> go.Figure:
    """Corpus against years, split into contributions and growth.

    The split is the chart's reason to exist. "You will have ₹4.35 lakh" is a
    number; "₹3.6 lakh of that is money you put in and ₹75,076 is growth" is the
    thing that makes compounding visible — and the gap widening over the years is
    the argument for starting early, made without saying a word.
    """
    title = "Projected corpus"
    if not projection:
        return _empty(title, "Set a target and a horizon to see the projection")

    years = [p["year"] for p in projection]
    contributed = [p["contributed"] for p in projection]
    growth = [p["growth"] for p in projection]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=years, y=contributed, name="Your contributions",
            mode="lines", stackgroup="corpus",
            line={"color": ACCENT, "width": 1},
            fillcolor="rgba(15,118,110,0.55)",
            hovertemplate="Year %{x}<br>Contributed ₹%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=years, y=growth, name="Growth",
            mode="lines", stackgroup="corpus",
            line={"color": WARNING, "width": 1},
            fillcolor="rgba(180,83,9,0.45)",
            hovertemplate="Year %{x}<br>Growth ₹%{y:,.0f}<extra></extra>",
        )
    )

    if target:
        figure.add_hline(
            y=target,
            line={"color": "grey", "width": 1, "dash": "dash"},
            annotation_text=f"Target {format_inr_compact(target)}",
            annotation_position="top left",
        )

    figure.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.2})
    figure.update_xaxes(title_text="Years from now", dtick=max(1, len(years) // 10))
    top = max([*(p["value"] for p in projection), target or 0])
    figure.update_yaxes(
        title_text="Corpus (₹)", **_rupee_ticks(0, top, compact=True)
    )
    return _base_layout(figure, title)
