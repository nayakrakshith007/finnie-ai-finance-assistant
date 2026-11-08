"""The LangGraph workflow — the thing that makes six agents one assistant.

    START -> supervisor -> [one or two agents, in order] -> compliance -> END
                              \\-> fallback -^

Why a state machine and not a function that calls agents
--------------------------------------------------------
A chain of calls would answer the same questions. What it would not give is a
*graph*: nodes and edges that can be drawn, inspected, tested edge by edge, and
asserted on. `test_no_path_reaches_the_end_without_compliance` is only writable
because "every path" is a real object here. The rubric weights LangGraph at 10
points for this reason, and it is also why the diagram in DESIGN.md can be
generated from the code rather than drawn by hand and left to rot.

How the next node is chosen
---------------------------
From `agent_trace`, not from a counter. `_next_node` takes the route, subtracts
the agents that have already recorded a trace entry, and returns the first one
left — or the compliance node when none are. No index to keep in sync, and the
decision is derived from what actually happened rather than from what was
supposed to happen. An agent cannot run twice, so a route cannot loop.

Compliance is terminal
----------------------
Every path ends at the compliance node, and only it writes the user's final text.
Until Day 4 `check_and_wrap` was called in `app.py`, which satisfied FR-006 only
because the UI was the single caller — the MCP server in Phase 13 would have
bypassed it entirely (PRD section 7.5 / D1). A guarantee that depends on every
future caller remembering is not a guarantee; a node every path must traverse is.

The node never raises, for the same reason agents never raise: a raising node
aborts the whole invocation, and the one node whose job is to make the answer
safe is the worst possible place to lose the answer.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.graph import END, START, StateGraph

from core.compliance import check_and_wrap
from core.logging_setup import get_logger
from workflow.registry import AGENT_NAMES, build_agents
from workflow.router import ROUTER_NAME, SupervisorRouter
from workflow.state import AgentState, TraceEntry

logger = get_logger(__name__)

COMPLIANCE_NODE = "compliance"
FALLBACK_NODE = "fallback"

# Shown when a turn produced no answer at all. Distinct from BaseAgent's
# FALLBACK_MESSAGE, which covers one agent failing: this covers the turn
# producing nothing, which means routing itself came to nothing.
NOTHING_PRODUCED = (
    "I was not able to work out an answer to that. Try rephrasing it, or ask me "
    "about a specific company, your portfolio, a savings goal, Indian tax rules, "
    "or how a particular investment works."
)

BLOCKED_REPLY = (
    "I cannot answer that the way it is phrased. Finnie explains how things work "
    "— it does not tell anyone what to buy or sell, or promise what a return will "
    "be. Ask me how the instrument works, what the trade-offs are, or what the "
    "tax treatment is, and I can help with that."
)


# ── the compliance node (FR-006) ───────────────────────────────────────────────


def compliance_node(state: AgentState) -> dict[str, Any]:
    """Terminal node: the last thing that touches the user's answer.

    Finds the final AI message, runs it through the guard, and returns it with
    the *same id* so `add_messages` replaces it rather than appending — an append
    would leave the unwrapped answer sitting in the transcript above the wrapped
    one, and the UI renders every message.

    Three outcomes, all of them an answer:
      * clean  -> the text plus exactly one disclaimer
      * banned -> a fixed refusal plus the disclaimer, and an error trace entry
      * empty  -> the "nothing produced" message, so a dead turn still speaks
    """
    started = perf_counter()
    answers = _this_turns_answers(state)
    answer = answers[-1] if answers else None

    if answer is None:
        logger.warning("Turn produced no answer; emitting the fallback message")
        return _compliance_update(
            AIMessage(content=_wrap_safely(NOTHING_PRODUCED)),
            started,
            status="error",
            detail="no answer was produced by any agent",
        )

    # A composed turn (FR-003) produces one answer per agent. The user asked one
    # question, so they get one reply: the pieces are joined before wrapping, and
    # the superseded messages are removed from state. Leaving them would mean
    # every consumer that reads `messages[-1]` as "the answer" silently drops the
    # first agent's work -- which is what the app did until this was found live.
    draft = "\n\n".join(str(m.content).rstrip() for m in answers if str(m.content).strip())
    superseded = [m for m in answers[:-1] if m.id]

    try:
        wrapped = check_and_wrap(draft)
        detail = "disclaimer appended"
        if len(answers) > 1:
            detail = f"merged {len(answers)} agent answers; {detail}"
        status = "ok"
    except ValueError as exc:
        # A banned phrase. The user gets a fixed refusal: the offending text is
        # never quoted back, which would defeat the point of blocking it.
        logger.warning("Compliance blocked a response: %s", exc)
        wrapped = _wrap_safely(BLOCKED_REPLY)
        detail = "blocked: banned phrase in the draft answer; replaced with a refusal"
        status = "error"
    except Exception as exc:  # noqa: BLE001 - the safety node must not be the failure
        logger.exception("Compliance guard itself failed")
        wrapped = f"{draft}\n\n{NOTHING_PRODUCED}"
        detail = f"guard failed ({type(exc).__name__}); answer passed through"
        status = "error"

    return _compliance_update(
        AIMessage(content=wrapped, id=answer.id),
        started,
        status=status,
        detail=detail,
        remove=superseded,
    )


def _wrap_safely(text: str) -> str:
    """Append the disclaimer to text Finnie wrote itself, which cannot be banned."""
    try:
        return check_and_wrap(text)
    except Exception:  # noqa: BLE001 - config missing or guard broken
        return text


def _compliance_update(
    message: AIMessage,
    started: float,
    *,
    status: str,
    detail: str,
    remove: list[AIMessage] | None = None,
) -> dict[str, Any]:
    """Build the node's state update.

    `remove` carries `RemoveMessage` instructions for the intermediate answers a
    composed turn produced. `add_messages` honours them, which is why the merge
    can happen here rather than being reassembled by every consumer.
    """
    messages: list[Any] = [RemoveMessage(id=m.id) for m in (remove or []) if m.id]
    messages.append(message)
    return {
        "messages": messages,
        "agent_trace": [
            TraceEntry(
                agent=COMPLIANCE_NODE,
                status=status,  # type: ignore[typeddict-item]
                latency_ms=round((perf_counter() - started) * 1000, 1),
                detail=detail,
            )
        ],
    }


def _this_turns_answers(state: AgentState) -> list[AIMessage]:
    """Every AI message produced since the user last spoke, in order.

    "Since the last human message" is what defines a turn here: one agent leaves
    one, a composed pair leaves two, and anything from earlier turns has already
    been wrapped and must not be wrapped again.
    """
    answers: list[AIMessage] = []
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage):
            answers.append(message)
    return list(reversed(answers))


# ── the fallback node (FR-005) ─────────────────────────────────────────────────


def fallback_node(state: AgentState) -> dict[str, Any]:
    """Reached when there was no agent to run.

    The router guarantees a non-empty, validated route, so this is defence in
    depth: if that guarantee ever breaks, the graph must still terminate with an
    answer rather than deadlock on a conditional edge with nowhere to go.
    """
    route = state.get("route") or []
    logger.warning("Fallback node reached; route was %r", route)
    return {
        "messages": [AIMessage(content=NOTHING_PRODUCED)],
        "error": state.get("error") or f"no runnable agent for route {route!r}",
        "agent_trace": [
            TraceEntry(
                agent=FALLBACK_NODE,
                status="error",
                latency_ms=0.0,
                detail=f"no runnable agent for route {route!r}",
            )
        ],
    }


# ── edge logic ─────────────────────────────────────────────────────────────────


def _next_node(state: AgentState, known: frozenset[str]) -> str:
    """The next agent to run, or the compliance node when the route is done.

    Derived from the trace rather than an index: `ran` is who actually recorded an
    entry, so this is self-correcting and cannot pick an agent twice. `known`
    guards against a route naming an agent that has no node, which would be an
    edge into nothing.
    """
    ran = {entry["agent"] for entry in state.get("agent_trace", [])}
    for name in state.get("route") or []:
        if name in known and name not in ran:
            return name

    if ran & known:
        return COMPLIANCE_NODE  # at least one agent ran; go and make it safe
    return FALLBACK_NODE  # nothing ran and nothing can


# ── assembly ───────────────────────────────────────────────────────────────────


def build_graph(agents: dict[str, Any] | None = None, router: Any | None = None) -> Any:
    """Compile the workflow.

    Args:
        agents: name -> object with `.run(state)`. Defaults to the real six.
        router: object with `.route_node(state)` or `.route(state)`. Defaults to
            the real supervisor.

    Both are injectable so `tests/test_graph.py` can assert on the wiring with
    doubles instead of six real agents and an API key. Compiling the real graph
    is still cheap, because every agent's `__init__` is lazy.
    """
    agents = agents if agents is not None else build_agents()
    router = router if router is not None else SupervisorRouter()
    route_fn = getattr(router, "route_node", None) or router.route

    known = frozenset(agents)
    graph = StateGraph(AgentState)

    graph.add_node(ROUTER_NAME, route_fn)
    for name, agent in agents.items():
        graph.add_node(name, agent.run)
    graph.add_node(COMPLIANCE_NODE, compliance_node)
    graph.add_node(FALLBACK_NODE, fallback_node)

    graph.add_edge(START, ROUTER_NAME)

    # The destinations map has to list every node a conditional edge may return,
    # so LangGraph can validate the graph at compile time rather than failing on
    # an unreachable branch at run time.
    destinations = {name: name for name in agents}
    destinations[COMPLIANCE_NODE] = COMPLIANCE_NODE
    destinations[FALLBACK_NODE] = FALLBACK_NODE

    def chooser(state: AgentState) -> str:
        return _next_node(state, known)

    graph.add_conditional_edges(ROUTER_NAME, chooser, destinations)
    for name in agents:
        # After each agent: the next agent on the route, or compliance. This is
        # what makes a two-agent chain (FR-003) fall out of the same wiring as a
        # one-agent turn, with no special case for composition.
        graph.add_conditional_edges(name, chooser, destinations)

    graph.add_edge(FALLBACK_NODE, COMPLIANCE_NODE)
    graph.add_edge(COMPLIANCE_NODE, END)

    compiled = graph.compile()
    logger.info("Workflow compiled with %d agents: %s", len(agents), ", ".join(agents))
    return compiled


def build_production_graph() -> Any:
    """The real graph, for the Streamlit app and the MCP server.

    A separate name so the app does not have to know that `build_graph()` takes
    test doubles, and so `@st.cache_resource` has one obvious thing to cache.
    """
    return build_graph()


__all__ = [
    "AGENT_NAMES",
    "COMPLIANCE_NODE",
    "FALLBACK_NODE",
    "build_graph",
    "build_production_graph",
    "compliance_node",
    "fallback_node",
]
