"""News tab — dedicated showcase for the NewsSynthesizerAgent (FR-014).

Lets the user search for headlines about any Indian company, index, sector,
or macro theme with a persistent mini-thread so follow-up queries carry context.
"""

from __future__ import annotations

import streamlit as st

from web_app import session
from web_app.tabs.chat import render_trace

_PLACEHOLDER_TOPICS = [
    "India-Pakistan war impact on markets",
    "RBI interest rate decision",
    "Nifty 50 outlook",
    "RELIANCE.NS",
    "TCS earnings",
    "Indian IT sector",
    "Gold vs equities 2024",
]


def _render_thread_entry(entry: dict) -> None:
    """Render one Q&A pair from the thread."""
    with st.chat_message("user"):
        st.markdown(entry["q"])
    with st.chat_message("assistant"):
        st.markdown(entry["result"]["answer"])

        if entry["result"].get("trace"):
            with st.expander("🔍 Agent trace", expanded=False):
                render_trace(entry["result"]["trace"])

        if entry["result"].get("error"):
            st.warning(f"⚠️ {entry['result']['error']}")


def render() -> None:
    if "news_thread" not in st.session_state:
        st.session_state.news_thread = []
    if "news_q_counter" not in st.session_state:
        st.session_state.news_q_counter = 0

    st.markdown("### 📰 News & Market Intelligence")
    st.caption(
        "Ask about any Indian company, index, sector, or macro theme. "
        "The News agent fetches live headlines and synthesises them for you."
    )

    # ── render existing thread ─────────────────────────────────────────────────
    for entry in st.session_state.news_thread:
        _render_thread_entry(entry)

    if st.session_state.news_thread:
        if st.button("🗑️ Clear conversation", key="news_clear_btn"):
            st.session_state.news_thread = []
            st.rerun()
        st.divider()

    # ── quick topics (shown only when thread is empty) ─────────────────────────
    if not st.session_state.news_thread:
        st.markdown("**Quick topics:**")
        chip_cols = st.columns(len(_PLACEHOLDER_TOPICS))
        chosen_chip = None
        for col, label in zip(chip_cols, _PLACEHOLDER_TOPICS):
            if col.button(label, key=f"chip_{label}", use_container_width=True):
                chosen_chip = label
    else:
        chosen_chip = None

    # ── input row ──────────────────────────────────────────────────────────────
    topic = st.text_input(
        "Topic or company",
        placeholder="e.g. India-Pakistan war impact on markets, RELIANCE.NS, RBI policy",
        key=f"news_topic_input_{st.session_state.news_q_counter}",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        run = st.button("Get news", use_container_width=True, key="news_run_btn")
    with col2:
        st.caption("Powered by the News Synthesizer agent · yfinance data · ~15 min delay")

    effective_topic = chosen_chip or topic

    if (run or chosen_chip) and effective_topic:
        question = (
            f"What is the latest news about {effective_topic}? "
            "Summarise the key developments and their potential impact on Indian investors."
        )
        with st.spinner("Fetching headlines…"):
            result = session.run_turn(question, record_in_chat=False)
        st.session_state.news_thread.append({"q": effective_topic, "result": result})
        st.session_state.news_q_counter += 1  # forces a fresh empty input on rerun
        st.rerun()
    elif run and not effective_topic:
        st.warning("Please enter a topic or company to search.")
