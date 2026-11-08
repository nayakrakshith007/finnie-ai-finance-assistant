"""Market tab (PRD §6.5a, FR-011, FR-033).

Layout: a ticker selector, a metric row, the trend line full width, the freshness
caption, and the interpretation below.

The selector offers the two indices, the configured default tickers, and anything
in the user's portfolio — the last of those because the holding someone actually
owns is the price they actually want, and making them retype `RELIANCE.NS` to see
it would be the kind of friction nobody forgives.

Freshness is shown in three places on purpose: in the metric row's caption, on
the chart title, and in the agent's own narration (FR-033). A stale price that
looks live is the single worst thing this tab could do, and three cheap
reminders are better than one that a user might scroll past.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from web_app import session
from web_app.charts import price_trend_line
from web_app.formatting import format_inr, format_signed_pct
from web_app.tabs.chat import render_trace

WINDOW_LABELS = {"30 days": "30d", "90 days": "90d"}


def _symbol_options() -> list[str]:
    """Indices, the configured defaults, and the user's own holdings."""
    try:
        from core.config import load_config

        cfg = load_config()
        options = [*cfg.market.default_indices, *cfg.market.default_tickers]
    except Exception:  # noqa: BLE001 - a config problem must not empty the selector
        options = ["^NSEI", "^BSESN", "RELIANCE.NS", "TCS.NS"]

    from portfolio.holdings import MARKET_TRADED_CLASSES

    for row in session.holdings():
        symbol = str(row.get("symbol") or "").upper()
        tradeable = row.get("asset_class", "stock") in MARKET_TRADED_CLASSES
        if symbol and tradeable and symbol not in options:
            options.append(symbol)
    return options


def _quote_for(symbol: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """The quote this tab asked for, matched loosely on the suffix.

    The agent normalises `TCS` to `TCS.NS`, so the key in state may not be the
    string the selector held.
    """
    for key, value in data.items():
        if key in ("news", "news_query") or not isinstance(value, dict):
            continue
        if key == symbol or key.split(".")[0] == symbol.split(".")[0]:
            return value
    return None


def render() -> None:
    options = _symbol_options()
    left, middle, right = st.columns([2, 1, 1])
    symbol = left.selectbox("Ticker or index", options, index=0)
    window_label = middle.selectbox("Window", list(WINDOW_LABELS), index=0)
    fetch = right.button("Get quote", type="primary", use_container_width=True)

    # Only ever on an explicit click, or when the user changes ticker *after*
    # having asked once. Nothing here may fire on a bare page load.
    #
    # `st.tabs` renders every tab's body on every rerun — Streamlit shows one and
    # runs them all. An auto-fetch here therefore spent an LLM call and a price
    # lookup for someone who opened the app and stayed in Chat. Found in the
    # browser on 2026-11-08; invisible to the tests, which never render a tab.
    asked_before = "market_result" in st.session_state
    changed_ticker = asked_before and st.session_state.get("market_symbol") != symbol

    if fetch or changed_ticker:
        with st.spinner(f"Fetching {symbol}…"):
            st.session_state.market_result = session.run_turn(
                f"How is {symbol} doing?", record_in_chat=False
            )
            st.session_state.market_symbol = symbol
    elif not asked_before:
        st.info(f"Press **Get quote** to fetch {symbol}.")
        return

    result = st.session_state.get("market_result") or {}
    data = session.market_data()
    quote = _quote_for(symbol, data)

    if quote is None:
        st.warning(result.get("answer") or f"No data available for {symbol}.")
        return

    a, b, c = st.columns(3)
    a.metric("Price", format_inr(quote["price"], paise=True))
    b.metric("Change", format_inr(quote["change"], paise=True),
             format_signed_pct(quote["change_pct"]))
    c.metric("Previous close", format_inr(quote["previous_close"], paise=True))

    freshness = quote.get("freshness", "")
    if quote.get("is_degraded"):
        st.warning(f"⚠ {freshness} — this is not a current price.")
    else:
        st.caption(f"{quote['symbol']} · {freshness} · source: {quote.get('source', '—')}")

    st.plotly_chart(
        price_trend_line(
            quote["symbol"],
            quote.get("trends") or {},
            window=WINDOW_LABELS[window_label],
            freshness=freshness if quote.get("is_degraded") else "",
        ),
        use_container_width=True,
    )

    if result.get("answer"):
        st.markdown("##### What this means")
        st.markdown(result["answer"])
        render_trace(result.get("trace") or [])
