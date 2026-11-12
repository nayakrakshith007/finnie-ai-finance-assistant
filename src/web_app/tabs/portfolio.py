"""Portfolio tab (PRD §6.5a, FR-062, FR-063).

Layout, per the spec: three metrics, then the allocation pie full width, then the
holdings table, the asset-class bar, and the narration.

Input is a single `st.data_editor` — type your holdings directly, no file needed.

Every number shown here comes from `portfolio.analysis` via the agent — never
recomputed locally. That is not laziness: if the tab did its own arithmetic, the
pie could disagree with the paragraph underneath it, and the user would have no
way to tell which was wrong.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core import deep_dive_cache
from web_app import session
from web_app.charts import allocation_pie, asset_class_bar, stock_price_history_chart
from web_app.formatting import format_inr, format_inr_compact, format_pct, format_signed_pct
from web_app.tabs.chat import render_trace

ANALYSE_PROMPT = "Analyse my portfolio."

COLUMNS = ("symbol", "quantity", "asset_class", "avg_cost", "price", "expense_ratio", "name")

# Asset classes that have an NSE/BSE ticker and are eligible for stock deep dive.
_TRADEABLE = frozenset({"stock", "etf"})


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame([{c: None for c in COLUMNS}])


def _input_section() -> None:
    st.markdown("##### Your holdings")
    current = session.holdings()
    frame = pd.DataFrame(current) if current else _empty_frame()
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    # Ensure string columns stay object dtype so Streamlit's SelectboxColumn works.
    # pandas infers NaN-only columns as float64; SelectboxColumn then can't store
    # a string selection back and the asset_class value silently stays NaN.
    for _col in ("symbol", "asset_class", "name"):
        frame[_col] = frame[_col].astype(object)

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
    st.caption("✏️ Click a cell to edit · Select a row's checkbox then click **Delete selected rows** to remove it · Use the ＋ at the top-right to add a new row")

    col_save, col_clear = st.columns([1, 1])
    if col_save.button("Save holdings", type="primary", use_container_width=True):
        rows = [
            {k: v for k, v in row.items() if v not in (None, "")}
            for row in edited.to_dict("records")
            if row.get("symbol")
        ]
        session.set_holdings(rows)
        st.success(f"Saved {len(rows)} holdings.")
        st.rerun()
    if col_clear.button("Clear all", use_container_width=True):
        session.set_holdings([])
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


def _holdings_table_with_buttons(analysis: dict[str, Any]) -> None:
    """Holdings table with per-stock Deep Dive buttons.

    Uses st.columns to render each row manually — the only way to mix a live
    button with tabular data in Streamlit. `st.dataframe` is read-only and
    `st.data_editor` does not support arbitrary widget columns.
    Only stocks and ETFs get the Deep Dive button; funds, bonds and cash have
    no ticker the deep-dive agent can resolve.
    """
    rows = analysis.get("holdings") or []
    if not rows:
        return

    # Column widths: symbol, name, class, qty, price, value, weight, P&L, button
    COL_W = [1.4, 2.2, 1.2, 0.7, 1.4, 1.5, 0.9, 1.4, 1.3]

    # Header row
    hdr = st.columns(COL_W)
    for col, label in zip(hdr, ["Symbol", "Name", "Class", "Qty", "Price ₹", "Value ₹", "Wt%", "P&L ₹", ""]):
        col.markdown(f"<small><b>{label}</b></small>", unsafe_allow_html=True)

    for row in rows:
        tradeable = row["asset_class"] in _TRADEABLE
        c = st.columns(COL_W)
        source_flag = " ⚠" if row.get("is_degraded") else ""
        c[0].markdown(f"`{row['symbol']}{source_flag}`")
        c[1].write(row.get("name") or "—")
        c[2].write(row["asset_class"])
        c[3].write(f"{row['quantity']:g}")
        c[4].write(format_inr(row["price"], paise=True, symbol=False))
        c[5].write(format_inr(row["value"], symbol=False))
        c[6].write(format_pct(row["weight_pct"]))
        pnl = row.get("unrealised_pnl")
        c[7].write(format_inr(pnl, symbol=False) if pnl is not None else "—")

        if tradeable:
            # Strip any exchange suffix so the agent receives the bare ticker.
            base = row["symbol"].upper().split(".")[0]
            if c[8].button("🔍 Deep Dive", key=f"dd_btn_{base}", use_container_width=True):
                st.session_state["selected_dd_symbol"] = base
                # Invalidate any cached result so a fresh fetch runs.
                st.session_state.pop(f"dd_result_{base}", None)
                st.rerun()


def _fetch_dd_price_history(symbol: str) -> tuple[list[str], list[float]]:
    """6-month daily closes for symbol, cached in session_state for the tab lifetime."""
    cache_key = f"dd_price_{symbol}"
    cached = st.session_state.get(cache_key)
    if cached:
        return cached
    try:
        import yfinance as yf
        from data.market import normalise_symbol
        ticker_sym = normalise_symbol(symbol)
        hist = yf.Ticker(ticker_sym).history(period="6mo")
        if hist.empty:
            return [], []
        dates = [str(d.date()) for d in hist.index]
        closes = [round(float(c), 2) for c in hist["Close"]]
        st.session_state[cache_key] = (dates, closes)
        return dates, closes
    except Exception:
        return [], []


def _stock_deep_dive_section() -> None:
    """Render the deep-dive panel for whichever stock was last clicked.

    Cache hierarchy (fastest → slowest):
      1. st.session_state  — in-memory, this browser tab, instant
      2. deep_dive_cache   — JSON file on disk, 15-min TTL, shared across all
                             sessions and survives app restarts
      3. LLM call          — yfinance fetch + OpenAI, costs money, ~10-30 s

    In production layer 2 would be Redis (same interface, different backend).
    """
    symbol = st.session_state.get("selected_dd_symbol")
    if not symbol:
        return

    st.divider()
    hdr_col, close_col = st.columns([6, 1])
    hdr_col.markdown(f"#### 🔬 Stock Deep Dive — {symbol}")
    if close_col.button("✕ Close", key="close_dd", use_container_width=True):
        st.session_state.pop("selected_dd_symbol", None)
        st.rerun()

    dd_key = f"dd_result_{symbol}"

    # Layer 1: session state (this tab, this session)
    result = st.session_state.get(dd_key)

    # Layer 2: file cache (persists across sessions, 15-min TTL)
    if result is None:
        result = deep_dive_cache.get(symbol)
        if result is not None:
            st.session_state[dd_key] = result  # promote to session state
            ttl = deep_dive_cache.ttl_remaining(symbol)
            st.caption(f"⚡ Loaded from cache · refreshes in {ttl // 60}m {ttl % 60}s")

    # Layer 3: live fetch (network + LLM)
    if result is None:
        with st.spinner(f"Fetching fundamentals, technicals and analyst data for {symbol}…"):
            result = session.run_turn(
                f"Give me a full deep dive analysis on {symbol}",
                record_in_chat=False,
            )
            if result and result.get("answer"):
                deep_dive_cache.set(symbol, result)   # write to file cache
                st.session_state[dd_key] = result
            else:
                # Live fetch failed — try stale cache as last resort
                stale = deep_dive_cache.get_stale(symbol)
                if stale:
                    result, age_minutes = stale
                    st.session_state[dd_key] = result
                    st.warning(
                        f"⚠️ **Yahoo Finance is currently unavailable.** "
                        f"Showing cached data from **{age_minutes} minute{'s' if age_minutes != 1 else ''} ago**. "
                        "Numbers may be outdated — refresh once the feed recovers."
                    )
                else:
                    st.session_state[dd_key] = result  # None / empty

    result = result or {}
    if result.get("answer"):
        # Price history chart — fetched fresh (or from session cache), no LLM cost.
        with st.spinner(f"Loading {symbol} price history…"):
            dates, closes = _fetch_dd_price_history(symbol)
        st.plotly_chart(
            stock_price_history_chart(symbol, dates, closes),
            use_container_width=True,
        )
        st.markdown(result["answer"])
        render_trace(result.get("trace") or [])
    else:
        st.warning(
            f"Could not fetch deep-dive data for **{symbol}**. "
            "Make sure the ticker is listed on Yahoo Finance (e.g. RELIANCE, TCS, HDFCBANK)."
        )


def render() -> None:
    _input_section()
    st.divider()

    holdings = session.holdings()
    if not holdings:
        st.info("Add your holdings above and I will analyse them.")
        return

    analysis = session.analysis()

    # ── top action bar ────────────────────────────────────────────────────────
    left, overview_col, dd_col, analyse_col = st.columns([3, 1.3, 1.3, 1])
    left.markdown(f"##### Analysis · {len(holdings)} holdings")

    # "Portfolio Overview" shows the AI narration in an expander at the top.
    if overview_col.button("📊 Portfolio Overview", use_container_width=True):
        st.session_state["show_portfolio_overview"] = not st.session_state.get(
            "show_portfolio_overview", False
        )

    # "Stocks Deep Dive" — if a stock is already open, clicking closes it;
    # otherwise it shows an inline picker so the user can choose without scrolling.
    if dd_col.button("🔬 Stocks Deep Dive", use_container_width=True):
        if st.session_state.get("selected_dd_symbol"):
            st.session_state.pop("selected_dd_symbol", None)
            st.session_state["show_dd_picker"] = False
        else:
            st.session_state["show_dd_picker"] = not st.session_state.get(
                "show_dd_picker", False
            )
        st.rerun()

    # Auto-analyse once per change of holdings, then only on request.
    signature = repr(holdings)
    first_time = st.session_state.get("portfolio_signature") != signature
    if analyse_col.button("Analyse", type="primary", use_container_width=True) or first_time:
        st.session_state["portfolio_signature"] = signature
        st.session_state.pop("show_portfolio_overview", None)
        with st.spinner("Pricing your holdings…"):
            result = session.run_turn(ANALYSE_PROMPT, record_in_chat=False)
            st.session_state["portfolio_result"] = result
        analysis = session.analysis()

    if not analysis:
        st.warning("I could not analyse those holdings. Check the rows above.")
        return

    # ── portfolio overview panel (toggled by button) ──────────────────────────
    result = st.session_state.get("portfolio_result") or {}
    if st.session_state.get("show_portfolio_overview") and result.get("answer"):
        with st.expander("📊 Portfolio Overview — AI Analysis", expanded=True):
            st.markdown(result["answer"])
            render_trace(result.get("trace") or [])

    # ── stock picker (shown when user clicks Stocks Deep Dive with no stock open) ──
    if st.session_state.get("show_dd_picker") and analysis:
        tradeable = [
            r["symbol"].upper().split(".")[0]
            for r in (analysis.get("holdings") or [])
            if r.get("asset_class") in _TRADEABLE
        ]
        if tradeable:
            with st.container(border=True):
                pick_col, go_col, close_col = st.columns([3, 1, 1])
                sym = pick_col.selectbox(
                    "Select stock:", tradeable,
                    key="dd_top_picker", label_visibility="collapsed",
                )
                if go_col.button("Analyse", type="primary", key="dd_top_go"):
                    st.session_state["selected_dd_symbol"] = sym
                    st.session_state.pop(f"dd_result_{sym}", None)
                    st.session_state["show_dd_picker"] = False
                    st.rerun()
                if close_col.button("✕ Cancel", key="dd_top_cancel"):
                    st.session_state["show_dd_picker"] = False
                    st.rerun()
        else:
            st.info("No stocks or ETFs in this portfolio — add some to use deep dive.")
            st.session_state["show_dd_picker"] = False

    # ── stock deep-dive panel — shown near the top so user doesn't need to scroll ──
    _stock_deep_dive_section()

    # ── metrics + charts ──────────────────────────────────────────────────────
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

    # ── holdings table with deep-dive buttons ─────────────────────────────────
    _holdings_table_with_buttons(analysis)
    st.plotly_chart(asset_class_bar(analysis), use_container_width=True)

    left, right = st.columns(2)
    left.metric("Risk band", str(analysis.get("risk_band", "—")).title(),
                help=f"Structural risk score {analysis.get('risk_score')}/5, from asset-class weights")
    right.metric("Fund fees a year", format_inr(analysis.get("annual_expense_cost")),
                 help=f"{format_pct(analysis.get('blended_expense_ratio'))} of the whole portfolio")

