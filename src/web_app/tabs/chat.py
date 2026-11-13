"""Chat tab (PRD §6.5a, FR-061).

Primary element: the transcript plus `st.chat_input` pinned at the bottom.
Supporting detail per answer: a Sources expander and a "How I answered this"
expander showing the agent trace.

The trace expander is the most interesting thing in the UI and the cheapest to
build, because the graph already records it. It is what turns "a chatbot
answered" into "the supervisor routed this to two agents, in this order, and
here is how long each took" — which is the difference between claiming a
multi-agent architecture and showing one.
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from web_app import session
from web_app.charts import stock_price_history_chart

SUGGESTIONS = (
    "What is a SIP and how is it different from a lump sum?",
    "How has TCS performed over the last month?",
    "Is PPF better than ELSS?",
    "What tax do I pay if I sell shares after 2 years?",
)

# Navigation hints shown after the latest assistant message so the user knows
# which tab has the full interactive version of what was just answered.
_AGENT_TAB_HINTS: dict[str, str] = {
    "market_analysis":   "📈 Open the **Market** tab for the full price chart and 30-day trend.",
    "stock_deep_dive":   "📊 Open the **Portfolio** tab → add the stock → click **🔍 Deep Dive** for the full panel with live charts.",
    "portfolio_analysis":"📊 Open the **Portfolio** tab to see your full allocation charts and holdings table.",
    "goal_planning":     "🎯 Open the **Goals** tab for the interactive SIP calculator and projections chart.",
    "news_synthesizer":  "📰 Open the **News** tab to browse all headlines across your holdings.",
    "tax_education":     "🧾 Open the **Tax** tab for the full tax rules reference.",
}


def _get_dd_price_history(symbol: str) -> tuple[list[str], list[float]]:
    """6-month daily closes for symbol, using the shared session_state cache."""
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


def render_trace(trace: list[dict[str, Any]]) -> None:
    """The agent trace for one turn (FR-007)."""
    if not trace:
        return
    path = " → ".join(step["agent"] for step in trace)
    with st.expander(f"🔍 How I answered this · {path}", expanded=False):
        for step in trace:
            icon = "✅" if step["status"] == "ok" else "⚠️"
            st.markdown(
                f"{icon} **{step['agent']}** · {step['latency_ms']:.0f} ms"
                f"<br><span style='color:grey;font-size:0.85em'>{step['detail']}</span>",
                unsafe_allow_html=True,
            )


def render_sources(sources: list[dict[str, Any]]) -> None:
    """Cited knowledge-base articles, with links where the metadata has them."""
    if not sources:
        return
    with st.expander(f"📚 Sources · {len(sources)} passages retrieved", expanded=False):
        for index, source in enumerate(sources, start=1):
            title = source.get("title") or "untitled"
            url = source.get("url") or ""
            label = f"[{title}]({url})" if url else title
            distance = source.get("distance")
            distance_text = f"distance {distance:.3f}" if distance is not None else ""
            st.markdown(
                f"**{index}.** {label}  \n"
                f"<span style='color:grey;font-size:0.85em'>"
                f"{source.get('category', '—')} › {source.get('section', '—')} · "
                f"{source.get('source', 'unknown source')} · {distance_text}</span>",
                unsafe_allow_html=True,
            )


def render() -> None:
    history = st.session_state.ui_messages

    if not history:
        with st.chat_message("assistant"):
            st.markdown(
                "👋 Hi! I'm **Finnie**, your AI-powered personal finance assistant "
                "for Indian investors.\n\n"
                "Here's what I can help you with:\n"
                "- 💬 **Finance Q&A** — explain SIPs, PPF, ELSS, NPS and other instruments\n"
                "- 📈 **Market data** — live prices and trends for NSE/BSE stocks and indices\n"
                "- 🔬 **Stock deep dive** — fundamentals, technicals, analyst outlook and sentiment\n"
                "- 📊 **Portfolio analysis** — value, P&L, diversification and fees on your holdings\n"
                "- 🎯 **Goal planning** — SIP calculator to reach any financial goal\n"
                "- 🧾 **Tax education** — LTCG, STCG, 80C, old vs new regime and more\n"
                "- 📰 **Market news** — latest headlines on companies and themes\n\n"
                "How can I help you today?"
            )
        st.caption("Or try one of these to get started:")
        columns = st.columns(2)
        for index, suggestion in enumerate(SUGGESTIONS):
            if columns[index % 2].button(suggestion, use_container_width=True):
                session.run_turn(suggestion)
                st.rerun()

    # Index of the last assistant message — tab hints are shown only there so
    # old messages in the transcript don't accumulate a banner each.
    last_asst_idx = max(
        (i for i, m in enumerate(history) if m.get("role") == "assistant"),
        default=-1,
    )

    for idx, message in enumerate(history):
        with st.chat_message(message.get("role", "assistant")):
            if message["role"] == "assistant":
                trace = message.get("trace") or []

                # Resolve chart symbol from stock_deep_dive trace entry (if any).
                dd_step = next(
                    (s for s in trace if s.get("agent") == "stock_deep_dive"), None
                )
                chart_symbol: str | None = None
                if dd_step:
                    detail = dd_step.get("detail", "")
                    # detail format: "RELIANCE.NS — P/E 21.85, RSI 72, …"
                    if " — " in detail:
                        chart_symbol = detail.split(" — ")[0].split(".")[0].strip() or None

                content = message.get("content") or "_(no content)_"

                # ── price-history chart placement ─────────────────────────────
                # Multi-agent turns: the aggregator embeds [CHART:SYMBOL] inline
                # right after the ## heading for the stock section. We split on
                # that token and render the chart in position so it appears only
                # within the stock deep-dive section, not at the top of the page.
                # Single-agent stock_deep_dive: no token → chart leads the text
                # (matching the Portfolio tab layout).
                chart_token_re = re.compile(r"\[CHART:([A-Z0-9]+)\]")
                token_match = chart_token_re.search(content)

                if token_match:
                    sym = token_match.group(1)
                    before, after = content.split(token_match.group(0), 1)
                    if before.strip():
                        st.markdown(before)
                    with st.spinner(f"Loading {sym} price history…"):
                        dates, closes = _get_dd_price_history(sym)
                    st.plotly_chart(
                        stock_price_history_chart(sym, dates, closes),
                        use_container_width=True,
                    )
                    if after.strip():
                        st.markdown(after)
                elif chart_symbol:
                    # Single-agent deep-dive: chart before text
                    with st.spinner(f"Loading {chart_symbol} price history…"):
                        dates, closes = _get_dd_price_history(chart_symbol)
                    st.plotly_chart(
                        stock_price_history_chart(chart_symbol, dates, closes),
                        use_container_width=True,
                    )
                    st.markdown(content)
                else:
                    st.markdown(content)
                render_trace(trace)
                render_sources(message.get("sources") or [])
                if message.get("latency"):
                    st.caption(f"⏱ {message['latency'] * 1000:.0f} ms")

                # ── tab navigation hints (latest message only) ────────────────
                if idx == last_asst_idx:
                    agent_names = {s.get("agent") for s in trace}
                    hints = [
                        _AGENT_TAB_HINTS[a]
                        for a in _AGENT_TAB_HINTS
                        if a in agent_names
                    ]
                    if hints:
                        st.info("  \n".join(hints))
            else:
                st.markdown(message.get("content") or "_(no content)_")

    at_limit = st.session_state.get("turn_count", 0) >= session.MAX_TURNS
    if at_limit:
        st.info(
            f"⚠️ You've used all {session.MAX_TURNS} messages for this session. "
            "Click **Clear conversation** in the sidebar to start a new one.",
            icon="🔒",
        )
    else:
        if prompt := st.chat_input("Ask a finance question…"):
            session.run_turn(prompt)
            st.rerun()
