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
@st.cache_resource(show_spinner="Loading Finnie RAG chain…")
def load_chain():
    from rag.chain import build_rag_chain
    return build_rag_chain()


def get_compliance():
    from core.compliance import check_and_wrap
    return check_and_wrap


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


_init_state()

# ── sidebar ────────────────────────────────────────────────────────────────────
# ── warm up chain at startup so the first message is fast ─────────────────────
with st.spinner("Loading Finnie knowledge base… (first load only)"):
    try:
        _chain = load_chain()
    except Exception as _startup_err:
        if "does not exist" in str(_startup_err):
            load_chain.clear()
            try:
                _chain = load_chain()
            except Exception as _e2:
                st.error(f"⚠️ Could not load RAG chain: {_e2}")
                st.stop()
        else:
            st.error(f"⚠️ Could not load RAG chain: {_startup_err}")
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
            try:
                chain = load_chain()
                check_and_wrap = get_compliance()

                t0 = time.perf_counter()
                result = chain.ask_with_sources(
                    prompt,
                    category=st.session_state.category,
                )
                latency = time.perf_counter() - t0

                raw_answer = result["answer"]
                sources    = result["sources"]

                # compliance guard — appends disclaimer, raises on banned phrases
                try:
                    answer = check_and_wrap(raw_answer)
                except ValueError as exc:
                    answer = (
                        "⚠️ I cannot answer that in the way you've phrased it — "
                        "Finnie gives education, not investment advice. "
                        "Please rephrase your question.\n\n"
                        f"*({exc})*"
                    )
                    sources = []

            except RuntimeError as exc:
                # most likely: OPENAI_API_KEY missing or index not built
                answer = (
                    f"❌ **Setup error:** {exc}\n\n"
                    "Make sure you have:\n"
                    "1. Added `OPENAI_API_KEY` to `.env`\n"
                    "2. Built the vector index: `python scripts/build_index.py`"
                )
                sources = []
                latency = 0.0

            except Exception as exc:
                # Stale Chroma collection after a --rebuild: auto-recover once
                if "does not exist" in str(exc):
                    load_chain.clear()
                    try:
                        chain = load_chain()
                        t0 = time.perf_counter()
                        result = chain.ask_with_sources(
                            prompt,
                            category=st.session_state.category,
                        )
                        latency = time.perf_counter() - t0
                        raw_answer = result["answer"]
                        sources    = result["sources"]
                        try:
                            answer = get_compliance()(raw_answer)
                        except ValueError:
                            answer  = "⚠️ I cannot answer that as phrased. Please rephrase."
                            sources = []
                    except Exception as exc2:
                        answer  = f"❌ Unexpected error after cache reset: {exc2}"
                        sources = []
                        latency = 0.0
                else:
                    answer  = f"❌ Unexpected error: {exc}"
                    sources = []
                    latency = 0.0

        st.markdown(answer)

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
        "latency": latency,
    })
    st.session_state.query_count += 1
    st.session_state.total_latency += latency
