"""Portfolio tab (PRD §6.5a, FR-062, FR-063).

Layout, per the spec: three metrics, then the allocation pie full width, then the
holdings table, the asset-class bar, and the narration.

Input is three ways in, because the spec asks for all three and they fail
differently: a CSV upload (fastest, and the one that can be malformed), a
`st.data_editor` for typing rows (no file needed, no parse errors), and a sample
portfolio button (zero effort, and the only one that works in a demo on a machine
with no data).

Every number shown here comes from `portfolio.analysis` via the agent — never
recomputed locally. That is not laziness: if the tab did its own arithmetic, the
pie could disagree with the paragraph underneath it, and the user would have no
way to tell which was wrong.
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
import streamlit as st

from web_app import session
from web_app.charts import allocation_pie, asset_class_bar
from web_app.formatting import format_inr, format_inr_compact, format_pct, format_signed_pct
from web_app.tabs.chat import render_trace

ANALYSE_PROMPT = "Analyse my portfolio."

COLUMNS = ("symbol", "quantity", "asset_class", "avg_cost", "price", "expense_ratio", "name")


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame([{c: None for c in COLUMNS}])


def _input_section() -> None:
    st.markdown("##### Your holdings")
    upload, manual, sample = st.tabs(["📄 Upload CSV", "⌨️ Enter manually", "✨ Sample"])

    with upload:
        st.caption(
            "Columns: **symbol**, **quantity**, and optionally asset_class, "
            "avg_cost, price, expense_ratio, name. Funds, bonds and cash have no "
            "ticker, so give them a `price` (their NAV or balance) instead."
        )
        uploaded = st.file_uploader("CSV file", type=["csv"], label_visibility="collapsed")
        if uploaded is not None and st.button("Load this file", type="primary"):
            from portfolio.holdings import parse_portfolio_csv

            text = io.StringIO(uploaded.getvalue().decode("utf-8", errors="replace")).read()
            holdings, errors = parse_portfolio_csv(text)
            # Errors are shown rather than raised, and the good rows are kept —
            # a twenty-row file with one typo should not be rejected whole
            # (FR-062).
            for error in errors:
                st.warning(error)
            if holdings:
                session.set_holdings([_to_row(h) for h in holdings])
                st.success(f"Loaded {len(holdings)} holdings.")
                st.rerun()

    with manual:
        current = session.holdings()
        frame = pd.DataFrame(current) if current else _empty_frame()
        for column in COLUMNS:
            if column not in frame.columns:
                frame[column] = None
        edited = st.data_editor(
            frame[list(COLUMNS)],
            num_rows="dynamic",
            use_container_width=True,
            key="holdings_editor",
            column_config={
                "symbol": st.column_config.TextColumn("Symbol", required=True),
                "quantity": st.column_config.NumberColumn("Quantity", min_value=0.0),
                "asset_class": st.column_config.SelectboxColumn(
                    "Asset class",
                    options=["stock", "etf", "mutual_fund", "bond", "cash", "crypto"],
                ),
                "avg_cost": st.column_config.NumberColumn("Avg cost (₹)"),
                "price": st.column_config.NumberColumn("Price / NAV (₹)", help="Only if it has no ticker"),
                "expense_ratio": st.column_config.NumberColumn("Expense ratio (%)"),
                "name": st.column_config.TextColumn("Name"),
            },
        )
        if st.button("Save holdings", type="primary"):
            rows = [
                {k: v for k, v in row.items() if v not in (None, "")}
                for row in edited.to_dict("records")
                if row.get("symbol")
            ]
            session.set_holdings(rows)
            st.success(f"Saved {len(rows)} holdings.")
            st.rerun()

    with sample:
        st.caption(
            "A realistic Indian portfolio, deliberately imperfect: it is 35% in one "
            "sovereign gold bond, so the concentration flag has something true to say."
        )
        if st.button("Load sample portfolio", type="primary"):
            from portfolio.holdings import SAMPLE_PORTFOLIO

            session.set_holdings([dict(row) for row in SAMPLE_PORTFOLIO])
            st.rerun()


def _to_row(holding: Any) -> dict[str, Any]:
    return {
        "symbol": holding.symbol,
        "quantity": holding.quantity,
        "asset_class": holding.asset_class,
        "avg_cost": holding.avg_cost,
        "price": holding.price,
        "expense_ratio": holding.expense_ratio,
        "name": holding.name,
    }


def _metrics(analysis: dict[str, Any]) -> None:
    left, middle, right = st.columns(3)
    left.metric("Total value", format_inr_compact(analysis.get("total_value")))

    pnl = analysis.get("unrealised_pnl")
    middle.metric(
        "Unrealised P&L",
        format_inr_compact(pnl) if pnl is not None else "—",
        format_signed_pct(analysis.get("unrealised_pnl_pct")) if pnl is not None else None,
        help=None if pnl is not None else "Add average costs to see profit and loss",
    )

    score = analysis.get("diversification_score")
    right.metric(
        "Diversification",
        f"{score}/100" if score is not None else "—",
        help=(
            "A composite of how evenly weighted the holdings are, how many there "
            "effectively are, and how many asset classes they span. Finnie's own "
            "heuristic, not a standard measure."
        ),
    )


def _holdings_table(analysis: dict[str, Any]) -> None:
    rows = analysis.get("holdings") or []
    if not rows:
        return
    frame = pd.DataFrame(
        [
            {
                "Symbol": row["symbol"],
                "Name": row["name"],
                "Class": row["asset_class"],
                "Qty": row["quantity"],
                "Price (₹)": format_inr(row["price"], paise=True, symbol=False),
                "Value (₹)": format_inr(row["value"], symbol=False),
                "Weight": format_pct(row["weight_pct"]),
                "P&L (₹)": format_inr(row.get("unrealised_pnl"), symbol=False),
                "Price source": row["source"] + (" ⚠" if row["is_degraded"] else ""),
            }
            for row in rows
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def render() -> None:
    _input_section()
    st.divider()

    holdings = session.holdings()
    if not holdings:
        st.info("Add some holdings above, or load the sample portfolio, and I will analyse them.")
        return

    analysis = session.analysis()
    left, right = st.columns([3, 1])
    left.markdown(f"##### Analysis · {len(holdings)} holdings")

    # Auto-analyse once per change of holdings, then only on request.
    #
    # `or not analysis` was the obvious condition and it was wrong: `st.tabs`
    # runs every tab's body on every rerun, so moving the risk slider in the
    # sidebar re-ran the whole analysis — an LLM call and a round of price
    # lookups per slider nudge. Keying on the holdings themselves means loading
    # a portfolio analyses it straight away (which is what a demo needs) while
    # an unrelated rerun costs nothing.
    signature = repr(holdings)
    first_time = st.session_state.get("portfolio_signature") != signature
    if right.button("Analyse", type="primary", use_container_width=True) or first_time:
        st.session_state.portfolio_signature = signature
        with st.spinner("Pricing your holdings…"):
            # record_in_chat=False: pressing a button in this tab must not inject
            # a message the user never typed into the Chat transcript.
            result = session.run_turn(ANALYSE_PROMPT, record_in_chat=False)
            st.session_state.portfolio_result = result
        analysis = session.analysis()

    if not analysis:
        st.warning("I could not analyse those holdings. Check the rows above.")
        return

    _metrics(analysis)
    st.plotly_chart(allocation_pie(analysis), use_container_width=True)

    if analysis.get("concentration_flags"):
        flags = ", ".join(
            f"{f['symbol']} at {format_pct(f['weight_pct'])}"
            for f in analysis["concentration_flags"]
        )
        st.warning(f"Above the concentration limit: {flags}")
    if analysis.get("unpriced"):
        st.warning(
            f"No price for {', '.join(analysis['unpriced'])} — these are excluded "
            "from the total. If they have no ticker, give them a price in the table above."
        )
    if analysis.get("is_degraded"):
        st.warning("At least one price is stale or sample data, so the total is not current.")

    _holdings_table(analysis)
    st.plotly_chart(asset_class_bar(analysis), use_container_width=True)

    left, right = st.columns(2)
    left.metric("Risk band", str(analysis.get("risk_band", "—")).title(),
                help=f"Structural risk score {analysis.get('risk_score')}/5, from asset-class weights")
    right.metric("Fund fees a year", format_inr(analysis.get("annual_expense_cost")),
                 help=f"{format_pct(analysis.get('blended_expense_ratio'))} of the whole portfolio")

    result = st.session_state.get("portfolio_result") or {}
    if result.get("answer"):
        st.markdown("##### What this means")
        st.markdown(result["answer"])
        render_trace(result.get("trace") or [])
