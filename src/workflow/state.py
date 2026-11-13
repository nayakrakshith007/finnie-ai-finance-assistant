"""The single shared state object that flows through the LangGraph workflow.

Design notes
------------
Every node reads from and writes to this one dict. Two things make that safe:

1. **Declared keys.** `AgentState` is a `TypedDict`, so a typo like `portfolo` is a
   type error rather than a silently-ignored key that reads back as `None` at
   runtime.

2. **Reducers.** LangGraph merges each node's returned dict into the running state.
   By default a returned key *replaces* the existing value, which is right for
   things like `route` or `market_data`. For two keys it is wrong:

   - `messages` uses `add_messages`, which appends and handles message IDs, so
     conversation history accumulates instead of each node clobbering the last.
   - `agent_trace` uses `_trace_reducer`: within a turn it appends (like
     `operator.add`), but passing `None` as the value resets the list to `[]`.
     The session layer passes `None` at the start of each turn so a new turn
     always begins with a clean trace — critical when the graph has a SQLite
     checkpointer, which persists agent_trace across browser sessions.

   A node returning `{"agent_trace": [entry]}` therefore *appends* one entry. This
   is why `BaseAgent.run` returns a single-element list.
   The router/session reset by returning `{"agent_trace": None}`.

Partial updates are the rule: a node returns only the keys it changed, never the
whole state.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def _trace_reducer(existing: list, incoming: list | None) -> list:
    """Append within a turn; reset when `None` is passed.

    `None` is the per-turn reset sentinel. The session layer sends it at the
    start of every turn so the trace does not accumulate across sessions when
    the graph uses a checkpointer.
    """
    if incoming is None:
        return []
    return existing + incoming


def _concat_docs(left: list, right: list) -> list:
    """Merge retrieved_docs written by parallel agents.

    When the supervisor fans out to 3 agents simultaneously via Send(), each
    agent writes its own retrieved_docs list. Without this reducer LangGraph
    raises INVALID_CONCURRENT_GRAPH_UPDATE because only one write per step is
    allowed on a plain field. This concatenates all agents' docs so the UI
    citation panel shows every source from every agent that ran.
    """
    return (left or []) + (right or [])


def _merge_dict(left: dict, right: dict) -> dict:
    """Merge dicts written by parallel agents; right wins on key conflicts.

    Applied to market_data, portfolio, and goal_params so that any combination
    of agents can run in parallel without racing on these fields.
    """
    return {**(left or {}), **(right or {})}

TraceStatus = Literal["ok", "error"]


class TraceEntry(TypedDict):
    """One agent's contribution to the execution path.

    Surfaced in the UI's "How I answered this" expander (PRD FR-007) and used by
    tests to assert which agents ran, so it is part of the contract rather than
    debug output.
    """

    agent: str
    status: TraceStatus
    latency_ms: float
    detail: str


class UserProfile(TypedDict, total=False):
    """Persists across turns; set from the sidebar controls and onboarding wizard."""

    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    horizon_years: int
    knowledge_level: Literal["beginner", "intermediate", "advanced"]
    # Financial profile fields (from onboarding wizard)
    age_range: str
    life_stage: str
    employment_type: str
    monthly_investable: str
    emergency_fund_months: str
    debt_band: str
    insurance_status: str
    tax_regime: str
    investment_experience: str
    primary_goal: str
    loss_behaviour: str


class AgentState(TypedDict, total=False):
    """State shared by every node in the workflow.

    `total=False` because nodes populate different subsets -- the Market agent
    never touches `goal_params`, and requiring every key everywhere would mean
    threading empty placeholders through the whole graph.
    """

    # Conversation. Appended to, never replaced.
    messages: Annotated[list[AnyMessage], add_messages]

    # Who is asking. Survives the whole session.
    user_profile: UserProfile

    # Router output: which agents should handle this turn, in order.
    route: list[str]

    # The latest question rewritten to stand on its own, set by the supervisor.
    # "What about the second one?" becomes "What is the TCS price?" once, here,
    # rather than six agents each being handed the whole transcript. Agents read
    # it in preference to the raw message (see `BaseAgent._latest_question`).
    resolved_question: str

    # Per-turn working data. Annotated with reducers so parallel agents (fan-out
    # via Send()) can all write without triggering INVALID_CONCURRENT_GRAPH_UPDATE.
    retrieved_docs: Annotated[list[dict[str, Any]], _concat_docs]
    market_data: Annotated[dict[str, Any], _merge_dict]
    portfolio: Annotated[dict[str, Any], _merge_dict]
    goal_params: Annotated[dict[str, Any], _merge_dict]

    # Execution path. Appended to by every agent; reset per turn via None sentinel.
    agent_trace: Annotated[list[TraceEntry], _trace_reducer]

    # Rolling summary of older conversation turns, managed by memory_manager_node.
    # Injected into the router's prompt so context is preserved beyond the verbatim
    # window without sending the whole history on every turn.
    session_summary: str

    # Targeted search/retrieval queries, one per agent in the route.
    # Supervisor writes these; each agent reads its own entry instead of the
    # raw question. A news agent gets "US Iran war India markets 2026"; a RAG
    # agent gets the concept to look up. Agents not listed here use the
    # resolved_question fallback.
    sub_queries: dict[str, str]

    # Non-empty when the supervisor needs more context before routing.
    # The clarification node emits it as a question; agents don't run that turn.
    # Cleared by the clarification node after it emits the question.
    pending_clarification: str

    # Retry loop control. Set by the evaluator node when the answer is incomplete;
    # read by the edge after evaluator to decide whether to loop back to supervisor.
    # Cleared at the start of each new user turn via TRANSIENT_KEYS in session.py.
    needs_retry: bool
    iteration_count: int  # counts how many evaluation retries have happened this turn
    retry_hint: str       # e.g. "news_synthesizer had no results; try finance_qa"

    # Set by the fallback path; a non-empty value means something degraded.
    error: str


def new_state(question: str, profile: UserProfile | None = None) -> AgentState:
    """Build a fresh state for a single-turn invocation.

    Convenience for tests and scripts. The Streamlit app keeps a longer-lived
    state in `session_state` instead of calling this per turn.
    """
    from langchain_core.messages import HumanMessage

    return AgentState(
        messages=[HumanMessage(content=question)],
        user_profile=profile or {},
        route=[],
        agent_trace=[],
    )
