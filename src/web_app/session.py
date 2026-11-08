"""Session state and the one way the UI talks to the graph (PRD §6.5a, FR-004).

Every tab asks a question the same way: `run_turn()`. That matters more than it
looks. Four tabs each assembling their own state update would be four chances to
forget to clear last turn's market data, or to drop the user profile, or to
invoke the graph without the conversation history — and the bug would appear in
one tab only, which is the hardest kind to notice.

The division of ownership
-------------------------
* `graph_state` is the conversation as the graph sees it: LangChain messages, the
  user profile, the per-turn working data. The graph owns memory.
* `ui_messages` is what Streamlit renders: dicts with the answer, its sources and
  its trace. The UI owns presentation.

Keeping them apart is why the Portfolio tab can run an analysis from a button
with no chat message, and why the Chat tab can replay a transcript without
re-running anything.

Nothing here imports `core.compliance`. The disclaimer is a terminal graph node
(PRD §7.5 / D1) and the UI must not apply it a second time.
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

# Per-turn working keys. Cleared before each turn so last turn's quote or
# analysis cannot be rendered beside this turn's answer. `messages` and
# `user_profile` are deliberately absent: they are the memory (FR-004).
TRANSIENT_KEYS = ("retrieved_docs", "market_data", "route", "resolved_question", "error")

RISK_LEVELS = ("conservative", "moderate", "aggressive")
KNOWLEDGE_LEVELS = ("beginner", "intermediate", "advanced")


@st.cache_resource(show_spinner="Starting Finnie…")
def load_graph() -> Any:
    """The compiled workflow, built once per server process.

    `cache_resource` and not `cache_data`: this is a live object with an LLM
    client and a Chroma connection inside it, not a value to copy per session.
    """
    from workflow.graph import build_production_graph

    return build_production_graph()


def init_session() -> None:
    """Create everything the tabs assume exists. Idempotent, safe every rerun."""
    from workflow.state import new_state

    if "graph_state" not in st.session_state:
        state = new_state("")
        state["messages"] = []
        state["portfolio"] = {"holdings": []}
        st.session_state.graph_state = state

    st.session_state.setdefault("ui_messages", [])
    st.session_state.setdefault("turn_count", 0)
    st.session_state.setdefault("total_latency", 0.0)
    st.session_state.setdefault("profile_risk", "moderate")
    st.session_state.setdefault("profile_horizon", 10)
    st.session_state.setdefault("profile_knowledge", "beginner")


def clear_conversation() -> None:
    """Reset the conversation but keep the profile and the holdings.

    Deliberate: "clear conversation" means the chat, not the portfolio someone
    spent five minutes typing in. Wiping that too would be the kind of
    helpfulness nobody asks for twice.
    """
    from workflow.state import new_state

    holdings = (st.session_state.graph_state.get("portfolio") or {}).get("holdings", [])
    state = new_state("")
    state["messages"] = []
    state["portfolio"] = {"holdings": holdings}
    st.session_state.graph_state = state
    st.session_state.ui_messages = []
    st.session_state.turn_count = 0
    st.session_state.total_latency = 0.0


# ── the profile (FR-064) ───────────────────────────────────────────────────────


def sync_profile() -> None:
    """Push the sidebar controls into the state the agents read.

    FR-064's acceptance criterion is that changing risk appetite demonstrably
    changes the Goal agent's output — it does, because the assumed return comes
    from `config.yaml: goals.risk_profiles[risk_appetite]`.
    """
    st.session_state.graph_state["user_profile"] = {
        "risk_appetite": st.session_state.profile_risk,
        "horizon_years": int(st.session_state.profile_horizon),
        "knowledge_level": st.session_state.profile_knowledge,
    }


def profile() -> dict[str, Any]:
    return st.session_state.graph_state.get("user_profile") or {}


# ── holdings ───────────────────────────────────────────────────────────────────


def holdings() -> list[dict[str, Any]]:
    return list((st.session_state.graph_state.get("portfolio") or {}).get("holdings") or [])


def set_holdings(rows: list[dict[str, Any]]) -> None:
    """Replace the holdings and drop any analysis computed from the old ones."""
    st.session_state.graph_state["portfolio"] = {"holdings": rows}


def analysis() -> dict[str, Any]:
    return (st.session_state.graph_state.get("portfolio") or {}).get("analysis") or {}


def market_data() -> dict[str, Any]:
    return st.session_state.graph_state.get("market_data") or {}


def goal_params() -> dict[str, Any]:
    return st.session_state.graph_state.get("goal_params") or {}


# ── the one way to ask ─────────────────────────────────────────────────────────


def run_turn(question: str, *, record_in_chat: bool = True) -> dict[str, Any]:
    """Put a question through the graph and return what came back.

    Args:
        question: the user's words, or the text a tab's button stands for.
        record_in_chat: whether this turn appears in the Chat tab's transcript.
            False for a tab's own button — pressing "Analyse my portfolio"
            should not silently inject a message the user never typed.

    Returns a dict of answer/sources/trace/latency/error. Never raises: the
    agents have their own error boundaries and the compliance node never raises,
    so the only thing left is the graph failing to start, which is reported as
    the answer.
    """
    from langchain_core.messages import HumanMessage

    sync_profile()
    state = st.session_state.graph_state
    state["messages"] = [*state.get("messages", []), HumanMessage(content=question)]
    for key in TRANSIENT_KEYS:
        state.pop(key, None)
    held = state.get("portfolio") or {}
    held.pop("analysis", None)  # keep the holdings, drop the stale analysis
    state["portfolio"] = held
    state["agent_trace"] = []

    started = time.perf_counter()
    try:
        state = load_graph().invoke(state)
        st.session_state.graph_state = state
        result = {
            "answer": str(state["messages"][-1].content),
            "sources": state.get("retrieved_docs") or [],
            "trace": state.get("agent_trace") or [],
            "error": state.get("error"),
        }
    except Exception as exc:  # noqa: BLE001 - the UI must always render something
        result = {
            "answer": (
                f"❌ I could not start that turn: {exc}\n\n"
                "If this is a fresh setup, check `OPENAI_API_KEY` in `.env` and that "
                "the index exists (`python scripts/build_index.py`)."
            ),
            "sources": [],
            "trace": [],
            "error": str(exc),
        }

    result["latency"] = time.perf_counter() - started
    st.session_state.turn_count += 1
    st.session_state.total_latency += result["latency"]

    if record_in_chat:
        st.session_state.ui_messages.append(user_message(question))
        st.session_state.ui_messages.append(assistant_message(result))
    return result


# The renderer reads `content`; `run_turn` produced `answer`, and `{**result}`
# spread it straight into the transcript without one. Every chat turn crashed
# with KeyError: 'content' — found in the browser on 2026-11-08, invisible to
# 585 passing tests, because no test renders a tab.
#
# So the shape is built by these two functions rather than by a dict spread at
# the call site, and `tests/test_web_session.py` checks that what they produce
# is exactly what `chat.render()` reads.
CHAT_MESSAGE_KEYS = ("role", "content")


def user_message(question: str) -> dict[str, Any]:
    return {"role": "user", "content": question}


def assistant_message(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.get("answer", ""),
        "sources": result.get("sources") or [],
        "trace": result.get("trace") or [],
        "latency": result.get("latency", 0.0),
        "error": result.get("error"),
    }


# ── the cost meter (FR-075) ────────────────────────────────────────────────────


def session_usage() -> dict[str, Any]:
    """Tokens and spend so far, from the LLM client's own meter.

    Shown in the sidebar because the API allowance is of unknown size (NFR-02a),
    so the person demonstrating this should be able to see what a conversation
    costs rather than find out afterwards.
    """
    try:
        from core.llm import CostMeterCallback

        meter = CostMeterCallback.session_totals()
    except Exception:  # noqa: BLE001 - a missing meter must not break the sidebar
        meter = {}

    turns = st.session_state.get("turn_count", 0)
    total = st.session_state.get("total_latency", 0.0)
    return {
        "turns": turns,
        "avg_latency": (total / turns) if turns else 0.0,
        "tokens": meter.get("total_tokens"),
        "cost_usd": meter.get("total_cost_usd"),
    }
