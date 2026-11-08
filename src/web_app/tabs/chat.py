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

from typing import Any

import streamlit as st

from web_app import session

SUGGESTIONS = (
    "What is a SIP and how is it different from a lump sum?",
    "How has TCS performed over the last month?",
    "Is PPF better than ELSS?",
    "What tax do I pay if I sell shares after 2 years?",
)


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
        st.markdown("#### Ask me something")
        st.caption(
            "I can explain how an instrument works, look up a live price, analyse "
            "holdings you enter in the Portfolio tab, work out what a goal needs "
            "monthly, or explain an Indian tax rule."
        )
        columns = st.columns(2)
        for index, suggestion in enumerate(SUGGESTIONS):
            if columns[index % 2].button(suggestion, use_container_width=True):
                session.run_turn(suggestion)
                st.rerun()

    for message in history:
        # `.get`, not `[...]`: a transcript lives in session state and can outlive
        # a code change during development, so a message written by an older
        # shape must render blank rather than take the whole page down with a
        # KeyError. That is exactly what happened on 2026-11-08.
        with st.chat_message(message.get("role", "assistant")):
            st.markdown(message.get("content") or "_(no content)_")
            if message["role"] == "assistant":
                render_trace(message.get("trace") or [])
                render_sources(message.get("sources") or [])
                if message.get("latency"):
                    st.caption(f"⏱ {message['latency'] * 1000:.0f} ms")

    if prompt := st.chat_input("Ask a finance question…"):
        session.run_turn(prompt)
        st.rerun()
