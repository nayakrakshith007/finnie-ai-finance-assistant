"""Finnie — Streamlit entry point (PRD §6.5a).

    streamlit run app.py

This file is deliberately thin: page config, the sidebar, the always-on
disclaimer banner, and four `st.tabs` that each delegate to a module in
`src/web_app/tabs/`. No business logic, no arithmetic, no prompt text.

Why the entry point stays at the repository root (PRD §7.5 / D3, resolved here)
------------------------------------------------------------------------------
Streamlit Cloud asks for a main file path and the documented local command is
`streamlit run app.py`, so a root entry point is the least surprising thing for
anyone who clones this. The *implementation* lives in `src/web_app/`, which is
what `src/web_app/` being empty was previously hiding. One file at the root, the
code in the package, and the Dockerfile and the deploy config agree.

What this file must never do
----------------------------
Import `core.compliance`. The disclaimer is appended by a terminal graph node
(PRD §7.5 / D1), and a second application here would double it — the exact defect
found live on 2026-11-08. Two tests in `tests/test_graph.py` assert that this
file does not call the guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

# src/ on the path before any Finnie import. One import convention everywhere:
# `from core.x import ...`, never `src.core.x`.
sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Finnie — AI Finance Assistant",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

from web_app import session  # noqa: E402
from web_app.formatting import format_inr_compact  # noqa: E402
from web_app.session import KNOWLEDGE_LEVELS, RISK_LEVELS  # noqa: E402
from web_app.tabs import chat, goals, market, portfolio  # noqa: E402

session.init_session()
# Before the tabs run, from the values the widgets stored last time. The widgets
# themselves are created at the bottom of this file — see why there.
session.sync_profile()


# ── the always-on banner (§6.5a) ───────────────────────────────────────────────

st.warning(
    "**Educational information only — not financial advice.** Finnie explains how "
    "things work and what the numbers say. It never recommends a trade, and it "
    "cannot know your full circumstances.",
    icon="⚠️",
)


# ── tabs ───────────────────────────────────────────────────────────────────────

chat_tab, portfolio_tab, market_tab, goals_tab = st.tabs(
    ["💬 Chat", "📊 Portfolio", "📈 Market", "🎯 Goals"]
)

with chat_tab:
    chat.render()

with portfolio_tab:
    portfolio.render()

with market_tab:
    market.render()

with goals_tab:
    goals.render()


# ── sidebar, rendered last ─────────────────────────────────────────────────────
#
# `with st.sidebar:` places content in the sidebar wherever it appears in the
# script, so the *position in the file* is free — and it has to be last. The
# session meter counts a turn that one of the tabs above has just run; rendered
# first, it read the counters before that turn happened and showed "Turns 0"
# directly beneath a freshly generated answer. Spotted in the browser on
# 2026-11-08.
#
# The profile widgets can safely be created down here: the tabs read
# `st.session_state.profile_*`, which holds whatever the widget stored on the
# previous interaction, and `init_session()` seeds the defaults.

with st.sidebar:
    st.markdown("## 💰 Finnie")
    st.caption("An AI finance assistant for Indian investors. Education, not advice.")
    st.divider()

    st.markdown("##### Your profile")
    st.select_slider(
        "Risk appetite",
        options=list(RISK_LEVELS),
        key="profile_risk",
        help="Sets the assumed return the Goal agent plans with.",
    )
    st.number_input("Horizon (years)", min_value=1, max_value=50, step=1, key="profile_horizon")
    st.selectbox("Knowledge level", options=list(KNOWLEDGE_LEVELS), key="profile_knowledge")
    session.sync_profile()

    st.divider()
    st.markdown("##### This session")
    usage = session.session_usage()
    left, right = st.columns(2)
    left.metric("Turns", usage["turns"])
    right.metric("Avg latency", f"{usage['avg_latency']:.1f}s" if usage["turns"] else "—")

    if usage["tokens"]:
        left, right = st.columns(2)
        left.metric("Tokens", f"{usage['tokens']:,}")
        right.metric("Est. cost", f"${usage['cost_usd']:.4f}")
    else:
        st.caption("Token meter starts after the first answer.")

    if st.button("Clear conversation", use_container_width=True):
        session.clear_conversation()
        for key in ("portfolio_result", "market_result", "goal_result", "goal_inputs"):
            st.session_state.pop(key, None)
        st.rerun()

    holdings = session.holdings()
    if holdings:
        total = session.analysis().get("total_value")
        st.caption(
            f"{len(holdings)} holdings saved"
            + (f" · {format_inr_compact(total)}" if total else "")
        )

    st.divider()
    st.caption(
        "Prices come from yfinance (Yahoo), which redistributes the exchange feed "
        "with a delay of roughly 15 minutes. Fit for learning, not for trading."
    )
