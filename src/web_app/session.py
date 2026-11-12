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
from langchain_core.messages import AIMessage, HumanMessage

# Per-turn working keys. Cleared before each turn so last turn's quote or
# analysis cannot be rendered beside this turn's answer. `messages` and
# `user_profile` are deliberately absent: they are the memory (FR-004).
TRANSIENT_KEYS = (
    "retrieved_docs", "market_data", "route", "resolved_question",
    "sub_queries", "pending_clarification",
    "needs_retry", "iteration_count", "retry_hint",  # evaluator loop — reset each new user turn
    "error",
)

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
    st.session_state.setdefault("financial_profile", {})
    st.session_state.setdefault("goal_chat_messages", [])


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
    """Push the sidebar controls and financial profile into the state the agents read.

    FR-064's acceptance criterion is that changing risk appetite demonstrably
    changes the Goal agent's output — it does, because the assumed return comes
    from `config.yaml: goals.risk_profiles[risk_appetite]`.
    """
    financial = st.session_state.get("financial_profile") or {}
    st.session_state.graph_state["user_profile"] = {
        "risk_appetite": st.session_state.profile_risk,
        "horizon_years": int(st.session_state.profile_horizon),
        "knowledge_level": st.session_state.profile_knowledge,
        **{k: v for k, v in financial.items() if v},  # only non-empty values
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


def load_user_history() -> None:
    """After login, restore the user's previous conversation from the checkpointer.

    Rebuilds both `graph_state` (what the agents read) and `ui_messages` (what
    the Chat tab renders). Historical messages have no sources/trace stored, so
    those fields default to empty — the user sees the text, not the metadata.
    """
    user_id = st.session_state.get("user_id")
    if not user_id:
        return

    graph = load_graph()
    if not hasattr(graph, "get_state"):
        return  # graph compiled without a checkpointer

    config = {"configurable": {"thread_id": user_id}}
    try:
        snapshot = graph.get_state(config)
    except Exception:  # noqa: BLE001 - no history is a valid starting point
        return

    if not snapshot or not snapshot.values:
        return  # first login, nothing to restore

    state = dict(snapshot.values)
    # Restore holdings so the Portfolio tab sees them too.
    st.session_state.graph_state = state
    messages = state.get("messages") or []
    st.session_state.ui_messages = _ui_messages_from_history(messages)
    st.session_state.turn_count = sum(
        1 for m in messages if isinstance(m, HumanMessage)
    )


def _ui_messages_from_history(messages: list) -> list[dict[str, Any]]:
    """Convert LangChain message history into the shape the Chat tab renders."""
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage):
            result.append({
                "role": "assistant",
                "content": str(msg.content),
                "sources": [],
                "trace": [],
                "latency": 0.0,
                "error": None,
            })
    return result


MAX_TURNS = 10  # per session limit


def run_turn(question: str, *, record_in_chat: bool = True) -> dict[str, Any]:
    """Put a question through the graph and return what came back.

    Args:
        question: the user's words, or the text a tab's button stands for.
        record_in_chat: whether this turn appears in the Chat tab's transcript.
            False for a tab's own button — pressing "Analyse my portfolio"
            should not silently inject a message the user never typed.

    When a user is logged in, the graph is called with their `thread_id` so the
    LangGraph checkpointer saves the conversation to SQLite. Each turn only
    passes the NEW human message; the checkpointer merges it with the full
    history. Without a login (anonymous) the existing in-memory approach is kept.

    Returns a dict of answer/sources/trace/latency/error. Never raises: the
    agents have their own error boundaries and the compliance node never raises,
    so the only thing left is the graph failing to start, which is reported as
    the answer.
    """
    if st.session_state.get("turn_count", 0) >= MAX_TURNS:
        return {
            "answer": (
                f"⚠️ You've reached the {MAX_TURNS}-message limit for this session. "
                "Click **Clear conversation** in the sidebar to start a new one."
            ),
            "sources": [],
            "trace": [],
            "error": "turn_limit_reached",
            "latency": 0.0,
        }

    sync_profile()

    user_id: str | None = st.session_state.get("user_id")
    graph = load_graph()

    started = time.perf_counter()
    try:
        if user_id:
            # ── authenticated path: checkpointer owns history ──────────────────
            # Only the new message + current profile/portfolio are passed.
            # add_messages reducer merges this with the checkpoint's history.
            config: dict[str, Any] = {"configurable": {"thread_id": user_id}}
            increment: dict[str, Any] = {
                "messages": [HumanMessage(content=question)],
                "user_profile": st.session_state.graph_state.get("user_profile", {}),
                "portfolio": st.session_state.graph_state.get("portfolio", {"holdings": []}),
                "agent_trace": None,   # None sentinel resets per-turn trace
                "needs_retry": False,  # clear evaluator loop state from previous turn
                "iteration_count": 0,
                "retry_hint": "",
            }
            state = graph.invoke(increment, config=config)
        else:
            # ── anonymous path: in-memory accumulation (original behaviour) ───
            state = st.session_state.graph_state
            state["messages"] = [*state.get("messages", []), HumanMessage(content=question)]
            for key in TRANSIENT_KEYS:
                state.pop(key, None)
            held = state.get("portfolio") or {}
            held.pop("analysis", None)
            state["portfolio"] = held
            state["agent_trace"] = []
            state = graph.invoke(state)

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

    # Persist which agents ran this turn to the user's profile (no LLM call needed).
    if user_id:
        try:
            from web_app.auth import update_user_topics
            agent_names = [
                entry["agent"]
                for entry in (result.get("trace") or [])
                if entry.get("agent") not in ("supervisor", "compliance", "memory_manager")
            ]
            if agent_names:
                update_user_topics(user_id, agent_names)
        except Exception:  # noqa: BLE001 - topic tracking must not break the turn
            pass

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
