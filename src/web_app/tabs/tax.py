"""Tax tab — dedicated showcase for the TaxEducationAgent (FR-048, FR-049).

Gives users a focused interface to ask Indian tax questions with a persistent
mini-thread so follow-up questions carry context from the same session.
"""

from __future__ import annotations

import streamlit as st

from web_app import session
from web_app.tabs.chat import render_trace

_QUICK_QUESTIONS = [
    "What is LTCG tax on equity mutual funds?",
    "STCG vs LTCG — what's the difference?",
    "How is ELSS taxed?",
    "Tax on debt mutual funds after 2023",
    "How to save tax under Section 80C?",
    "What is indexation benefit?",
    "Tax on SGB (Sovereign Gold Bond) redemption",
]


def _render_thread_entry(entry: dict) -> None:
    """Render one Q&A pair from the thread."""
    with st.chat_message("user"):
        st.markdown(entry["q"])
    with st.chat_message("assistant"):
        st.markdown(entry["result"]["answer"])

        sources = entry["result"].get("sources") or []
        if sources:
            with st.expander(f"📚 Sources · {len(sources)} passages", expanded=False):
                for src in sources:
                    title = src.get("title") or src.get("section") or "Untitled"
                    url = src.get("url", "")
                    if url:
                        st.markdown(f"- [{title}]({url})  `{src.get('category', '')}`")
                    else:
                        st.markdown(f"- **{title}**  `{src.get('category', '')}`")

        if entry["result"].get("trace"):
            with st.expander("🔍 Agent trace", expanded=False):
                render_trace(entry["result"]["trace"])

        if entry["result"].get("error"):
            st.warning(f"⚠️ {entry['result']['error']}")


def render() -> None:
    if "tax_thread" not in st.session_state:
        st.session_state.tax_thread = []
    if "tax_q_counter" not in st.session_state:
        st.session_state.tax_q_counter = 0

    st.markdown("### 🧾 Tax Education")
    st.caption(
        "Ask any question about Indian investment taxation — LTCG, STCG, ELSS, "
        "Section 80C, indexation, and more. Rates reflect post-Budget 2024 rules."
    )

    # ── render existing thread ─────────────────────────────────────────────────
    for entry in st.session_state.tax_thread:
        _render_thread_entry(entry)

    if st.session_state.tax_thread:
        if st.button("🗑️ Clear conversation", key="tax_clear_btn"):
            st.session_state.tax_thread = []
            st.rerun()
        st.divider()

    # ── quick questions (shown only when thread is empty) ──────────────────────
    if not st.session_state.tax_thread:
        st.markdown("**Quick questions:**")
        rows = [_QUICK_QUESTIONS[:4], _QUICK_QUESTIONS[4:]]
        chosen_chip = None
        for row in rows:
            cols = st.columns(len(row))
            for col, q in zip(cols, row):
                if col.button(q, key=f"taxchip_{q}", use_container_width=True):
                    chosen_chip = q
    else:
        chosen_chip = None

    # ── input row ──────────────────────────────────────────────────────────────
    question = st.text_input(
        "Your tax question",
        placeholder="e.g. What is the LTCG tax rate on equity funds after July 2024?",
        key=f"tax_question_input_{st.session_state.tax_q_counter}",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        run = st.button("Ask", use_container_width=True, key="tax_run_btn")
    with col2:
        st.caption("Powered by the Tax Education agent · Knowledge base grounded · Post-Budget 2024")

    effective_q = chosen_chip or question

    if (run or chosen_chip) and effective_q:
        with st.spinner("Looking up tax rules…"):
            result = session.run_turn(effective_q, record_in_chat=False)
        st.session_state.tax_thread.append({"q": effective_q, "result": result})
        st.session_state.tax_q_counter += 1  # forces a fresh empty input on rerun
        st.rerun()
    elif run and not effective_q:
        st.warning("Please enter a tax question.")
