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
   - `agent_trace` uses `operator.add`, so every agent appends its own entry and
     we end up with the full execution path rather than only the last hop.

   A node returning `{"agent_trace": [entry]}` therefore *appends* one entry. This
   is why `BaseAgent.run` returns a single-element list.

Partial updates are the rule: a node returns only the keys it changed, never the
whole state.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

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
    """Persists across turns; set from the sidebar controls."""

    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    horizon_years: int
    knowledge_level: Literal["beginner", "intermediate", "advanced"]


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

    # Per-turn working data, written by whichever agent produced it.
    retrieved_docs: list[dict[str, Any]]
    market_data: dict[str, Any]
    portfolio: dict[str, Any]
    goal_params: dict[str, Any]

    # Execution path. Appended to by every agent.
    agent_trace: Annotated[list[TraceEntry], operator.add]

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
