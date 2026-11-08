"""Finnie — Streamlit chat interface for the RAG agent.

Run from the ai_finance_assistant/ directory:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ── make src/ importable ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

# ── page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="Finnie — Finance Assistant",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── lazy imports (after sys.path is set) ───────────────────────────────────────
@st.cache_resource(show_spinner="Loading Finnie…")
def load_graph():
    """The compiled LangGraph workflow: router -> agent(s) -> compliance.

    Note what this module no longer imports: `core.compliance`. Until Day 4 the
    UI appended the disclaimer itself, which meant FR-006's guarantee held only
    because the UI happened to be the single caller — the MCP server in Phase 13
    would have bypassed it entirely. Compliance is now a terminal node inside the
    graph, so the UI cannot forget it and cannot apply it twice (PRD §7.5 / D1).
    """
    from workflow.graph import build_production_graph
    return build_production_graph()


def _render_trace(trace: list[dict]) -> None:
    """The "how I answered this" expander (FR-007).

    Shows which nodes ran, in what order, and how long each took — so the
    supervisor's routing decision, a composed two-agent turn, and a degraded
    price are all visible rather than inferred from the prose.
    """
    with st.expander(f"🔍 How I answered this ({len(trace)} steps)", expanded=False):
        for step in trace:
            icon = "✅" if step["status"] == "ok" else "⚠️"
            st.markdown(
                f"{icon} **{step['agent']}** · {step['latency_ms']:.0f} ms"
                f"<br><span style='color:grey;font-size:0.85em'>{step['detail']}</span>",
                unsafe_allow_html=True,
            )


# ── session state init ─────────────────────────────────────────────────────────
def _init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []           # list of {role, content, sources, latency}
    if "query_count" not in st.session_state:
        st.session_state.query_count = 0
    if "total_latency" not in st.session_state:
        st.session_state.total_latency = 0.0
    if "category" not in st.session_state:
        st.session_state.category = None
    if "graph_state" not in st.session_state:
        # The conversation as the graph sees it: LangChain messages, the user
        # profile and the per-turn working data. Kept separate from `messages`,
        # which is only what Streamlit renders. The graph owns memory (FR-004);
        # the UI owns presentation.
        from workflow.state import new_state
        st.session_state.graph_state = new_state("")
        st.session_state.graph_state["messages"] = []


_init_state()

# ── sidebar ────────────────────────────────────────────────────────────────────
# ── warm up chain at startup so the first message is fast ─────────────────────
with st.spinner("Loading Finnie… (first load only)"):
    try:
        _graph = load_graph()
    except Exception as _startup_err:
        st.error(
            f"⚠️ Could not start Finnie: {_startup_err}"
            "\n\nCheck that `OPENAI_API_KEY` is set in `.env`, and that the index "
            "has been built with `python scripts/build_index.py`."
        )
        st.stop()

CATEGORIES = [
    "All topics",
    "basics",
    "behavioural",
    "bonds",
    "diversification",
    "etfs",
    "fixed-income",
    "insurance",
    "investing",
    "mutual-funds",
    "personal-finance",
    "retirement",
    "risk",
    "stocks",
    "tax",
]

with st.sidebar:
    st.title("⚙️ Settings")

    selected = st.selectbox(
        "Knowledge base category",
        CATEGORIES,
        index=0,
        help="Filter retrieval to one topic, or search everything.",
    )
    st.session_state.category = None if selected == "All topics" else selected

    st.divider()
    st.subheader("📊 Session stats")
    st.metric("Queries asked", st.session_state.query_count)
    if st.session_state.query_count:
        avg_ms = st.session_state.total_latency / st.session_state.query_count * 1000
        st.metric("Avg response time", f"{avg_ms:.0f} ms")

    st.divider()
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.query_count = 0
        st.session_state.total_latency = 0.0
        st.rerun()

    st.divider()
    st.caption(
        "Finnie is an **educational** AI. It never recommends trades. "
        "Always verify with a licensed financial adviser."
    )

# ── header ─────────────────────────────────────────────────────────────────────
st.title("💰 Finnie — Personal Finance Assistant")
st.caption(
    "Ask anything about investing, taxes, mutual funds, ETFs, bonds, or risk. "
    "Finnie answers from the Zerodha Varsity knowledge base."
)

# ── render existing messages ───────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander(f"📚 Sources ({len(msg['sources'])} chunks retrieved)", expanded=False):
                for i, src in enumerate(msg["sources"], 1):
                    cat   = src.get("category", "—")
                    sec   = src.get("section", "—")
                    title = src.get("title", "—")
                    dist  = src.get("distance")
                    dist_str = f"{dist:.3f}" if dist is not None else "—"
                    st.markdown(
                        f"**{i}.** `{cat}` › {title} › {sec} &nbsp; "
                        f"<span style='color:grey;font-size:0.85em'>dist={dist_str}</span>",
                        unsafe_allow_html=True,
                    )
        if msg["role"] == "assistant" and msg.get("trace"):
            _render_trace(msg["trace"])
        if msg.get("latency"):
            st.caption(f"⏱ {msg['latency']*1000:.0f} ms")

# ── chat input ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask a finance question…"):
    # show user bubble
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # generate answer
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            from langchain_core.messages import HumanMessage

            answer, sources, trace, latency = "", [], [], 0.0
            try:
                graph = load_graph()
                state = st.session_state.graph_state
                state["messages"] = [*state.get("messages", []), HumanMessage(content=prompt)]

                # Per-turn working data is cleared first, so last turn's quote or
                # portfolio analysis cannot be rendered beside this turn's answer.
                # `messages` and `user_profile` deliberately survive: they are the
                # conversation memory (FR-004).
                for key in ("retrieved_docs", "market_data", "portfolio", "route", "error"):
                    if key == "portfolio":
                        # Keep the user's holdings; drop only the computed analysis.
                        held = state.get("portfolio") or {}
                        held.pop("analysis", None)
                        state["portfolio"] = held
                    else:
                        state.pop(key, None)
                state["agent_trace"] = []

                t0 = time.perf_counter()
                state = graph.invoke(state)
                latency = time.perf_counter() - t0

                st.session_state.graph_state = state
                answer = str(state["messages"][-1].content)
                sources = state.get("retrieved_docs") or []
                trace = state.get("agent_trace") or []

            except Exception as exc:
                # Only the graph itself failing reaches here: every agent has its
                # own error boundary and the compliance node never raises.
                answer = (
                    f"❌ Something went wrong before I could answer: {exc}"
                    "\n\nIf this is the first run, check `OPENAI_API_KEY` in `.env` "
                    "and that the index is built (`python scripts/build_index.py`)."
                )

        st.markdown(answer)

        if trace:
            _render_trace(trace)

        if sources:
            with st.expander(f"📚 Sources ({len(sources)} chunks retrieved)", expanded=False):
                for i, src in enumerate(sources, 1):
                    cat   = src.get("category", "—")
                    sec   = src.get("section", "—")
                    title = src.get("title", "—")
                    dist  = src.get("distance")
                    dist_str = f"{dist:.3f}" if dist is not None else "—"
                    st.markdown(
                        f"**{i}.** `{cat}` › {title} › {sec} &nbsp; "
                        f"<span style='color:grey;font-size:0.85em'>dist={dist_str}</span>",
                        unsafe_allow_html=True,
                    )

        st.caption(f"⏱ {latency*1000:.0f} ms")

    # persist to session state
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "trace": trace,
        "latency": latency,
    })
    st.session_state.query_count += 1
    st.session_state.total_latency += latency
