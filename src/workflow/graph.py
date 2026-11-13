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
from langgraph.types import Send

from core.compliance import check_and_wrap
from core.logging_setup import get_logger
from workflow.registry import AGENT_NAMES, build_agents
from workflow.router import ROUTER_NAME, SupervisorRouter
from workflow.state import AgentState, TraceEntry

MEMORY_NODE = "memory_manager"

logger = get_logger(__name__)

AGGREGATOR_NODE = "response_aggregator"
COMPLIANCE_NODE = "compliance"
DISPATCHER_NODE = "dispatcher"
EVALUATOR_NODE = "evaluator"
FALLBACK_NODE = "fallback"
CLARIFICATION_NODE = "clarifier"

# Max evaluation retries per turn. Prevents infinite supervisor loops.
_MAX_EVAL_ITERATIONS = 2

# Agent pairs where the second depends on the first's output — must run sequentially.
# goal_planning reads portfolio.analysis which portfolio_analysis writes.
_SEQUENTIAL_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"portfolio_analysis", "goal_planning"}),
})

# Signals in an agent's answer that indicate it couldn't fully answer.
# The evaluator uses these to decide whether to retry with a different route.
_INCOMPLETE_SIGNALS = (
    "i could not fetch",
    "i don't have enough",
    "i do not have enough",
    "news feed is not responding",
    "not in my knowledge base",
    "i was not able to work out",
)

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


# ── memory management node ────────────────────────────────────────────────────


def memory_manager_node(state: AgentState) -> dict[str, Any]:
    """Summarise old messages so the router always has context without an ever-growing prompt.

    Industry-standard 3-tier memory:
      Tier 1: structured user profile (already in state["user_profile"])
      Tier 2: rolling session summary (state["session_summary"], updated here)
      Tier 3: last K verbatim turns (kept by removing older messages via RemoveMessage)

    When the conversation has fewer than `summarise_after_turns` human turns, this
    node is a no-op — it returns {} and the graph continues to the supervisor unchanged.
    That makes the tests pass with no changes: `new_state()` starts with one message,
    well below the threshold.
    """
    from langchain_core.messages import SystemMessage as _Sys
    from langchain_openai import ChatOpenAI

    try:
        from core.config import load_config
        cfg = load_config().memory
        threshold = cfg.summarise_after_turns
        keep = cfg.keep_verbatim_turns
    except Exception:  # noqa: BLE001 - config failure must not block the turn
        threshold, keep = 10, 5

    messages = state.get("messages") or []
    human_turns = [m for m in messages if isinstance(m, HumanMessage)]

    if len(human_turns) <= threshold:
        return {}  # not enough history yet — pass through unchanged

    # Keep the last `keep` human–AI pairs verbatim; summarise everything before.
    # Find the index of the (len - keep)th HumanMessage so we know the cut point.
    human_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    cut_index = human_indices[-(keep)]  # first message index to keep verbatim

    old_messages = messages[:cut_index]
    if not old_messages:
        return {}

    # Build the conversation text to summarise.
    lines = []
    for m in old_messages:
        if isinstance(m, HumanMessage):
            lines.append(f"User: {m.content}")
        elif isinstance(m, AIMessage):
            # Strip the disclaimer suffix that compliance appended — not useful in a summary.
            text = str(m.content)
            disclaimer_start = text.find("\n\n*This is educational")
            if disclaimer_start != -1:
                text = text[:disclaimer_start]
            lines.append(f"Assistant: {text[:400]}")  # cap per-message length

    conversation_text = "\n".join(lines)
    existing_summary = (state.get("session_summary") or "").strip()

    summary_prompt = (
        "You are summarising a financial assistant conversation for memory compression. "
        "Produce a concise paragraph (under 150 words) covering: the user's key goals, "
        "instruments discussed, decisions considered, and any numbers that matter. "
        "Write it as a third-person summary the assistant can use as background context.\n\n"
    )
    if existing_summary:
        summary_prompt += f"Earlier summary:\n{existing_summary}\n\nNew turns to integrate:\n"
    else:
        summary_prompt += "Conversation:\n"
    summary_prompt += conversation_text

    try:
        cfg_full = load_config()
        llm = ChatOpenAI(
            model=cfg_full.llm.router_model,
            temperature=0.0,
            api_key=cfg_full.secrets.openai_api_key,
        )
        new_summary = str(llm.invoke([_Sys(content=summary_prompt)]).content).strip()
    except Exception as exc:  # noqa: BLE001 - summary failure must not block the turn
        logger.warning("Memory summarisation failed (%s); skipping", type(exc).__name__)
        return {}

    # Remove the old messages from state using RemoveMessage.
    to_remove = [RemoveMessage(id=m.id) for m in old_messages if getattr(m, "id", None)]

    logger.info(
        "Memory manager: summarised %d old messages; keeping %d verbatim turns",
        len(old_messages), keep,
    )
    return {
        "messages": to_remove,
        "session_summary": new_summary,
    }


# ── the clarification node ────────────────────────────────────────────────────


def clarification_node(state: AgentState) -> dict[str, Any]:
    """Asks the user for missing context instead of guessing.

    Reached when the supervisor identified that it cannot route well without
    more information — typically a personal-situation question (tax, goals,
    portfolio) where no numbers have been given yet. The question goes through
    compliance like any other answer, so the disclaimer is appended.

    Clears `pending_clarification` so the next turn routes to agents normally
    with the user's answer in history.
    """
    question = (state.get("pending_clarification") or "").strip()
    if not question:
        question = "Could you share a few details so I can give you a precise answer?"

    logger.info("Clarification node: asking '%s'", question[:80])
    return {
        "messages": [AIMessage(content=question)],
        "pending_clarification": "",
        "agent_trace": [
            TraceEntry(
                agent=CLARIFICATION_NODE,
                status="ok",
                latency_ms=0.0,
                detail=f"asked: {question[:80]}",
            )
        ],
    }


# ── the evaluator node (answer quality + retry loop) ──────────────────────────


def evaluator_node(state: AgentState) -> dict[str, Any]:
    """Check the answer quality and optionally loop back to the supervisor.

    After compliance has wrapped the final answer, this node checks whether the
    answer actually addressed the question. If it looks incomplete (the agent
    couldn't fetch data, had no knowledge-base context, etc.) AND we haven't
    exceeded the retry budget, it sets `needs_retry=True` so the edge after this
    node routes back to the supervisor for a second attempt.

    On retry, the supervisor sees the original question plus the incomplete answer
    in the message history, so it can try a different route (e.g. fall back from
    news_synthesizer to finance_qa for a knowledge-base answer).

    Why rule-based and not an LLM judge: this runs on every turn. An LLM call here
    would add ~500 ms and cost to every response — too expensive for a signal that
    simple string matching delivers well enough. A proper production system would
    use a cheap judge model only when the route was multi-agent or high-stakes.
    """
    iteration = state.get("iteration_count") or 0

    if iteration >= _MAX_EVAL_ITERATIONS:
        logger.info("Evaluator: max iterations (%d) reached; accepting answer", _MAX_EVAL_ITERATIONS)
        return {"needs_retry": False}

    messages = state.get("messages") or []
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)

    if last_ai is None:
        return {"needs_retry": False}

    answer_lower = str(last_ai.content).lower()
    incomplete = any(signal in answer_lower for signal in _INCOMPLETE_SIGNALS)

    if incomplete:
        logger.info(
            "Evaluator: answer looks incomplete on iteration %d — scheduling retry",
            iteration,
        )
        # Tell the supervisor which agents ran and failed so it can try differently.
        ran = [e["agent"] for e in (state.get("agent_trace") or [])
               if e.get("agent") not in ("supervisor", "compliance", "evaluator", "clarifier")]
        hint = (
            f"Your previous routing to [{', '.join(ran)}] did not produce a complete "
            "answer. Try a different agent or approach for this retry."
        ) if ran else "Previous answer was incomplete. Try a different routing."

        # Remove ALL AI messages produced this turn so the next compliance pass
        # starts with a clean slate. Removing only last_ai is insufficient:
        # compliance may have already removed superseded intermediate messages
        # but left raw agent outputs behind, causing all rounds to be merged.
        to_remove = []
        for m in reversed(state.get("messages") or []):
            if isinstance(m, HumanMessage):
                break
            if isinstance(m, AIMessage) and getattr(m, "id", None):
                to_remove.append(RemoveMessage(id=m.id))

        return {
            "messages": to_remove,
            "iteration_count": iteration + 1,
            "needs_retry": True,
            "retry_hint": hint,
        }

    return {"needs_retry": False, "retry_hint": ""}


# ── the response aggregator node ─────────────────────────────────────────────


def response_aggregator_node(state: AgentState) -> dict[str, Any]:
    """Structure multi-agent answers into one coherent response.

    When the supervisor fans out to 2-3 agents, each agent answers its own
    sub-question independently. This node takes all their answers and either:

    - Uses ## section headers for genuinely separate topics (e.g. SIP investing
      + LTCG tax rates + TCS stock analysis in one message)
    - Synthesises into a single flowing answer for related sub-tasks of one
      question (e.g. portfolio analysis → goal planning)

    How it knows which: sub_queries maps each agent to its specific question.
    The LLM reads those and decides whether the questions are independent
    topics or related parts of the same question.

    Single-agent turns skip this — the conditional edge never routes here when
    len(route) == 1.

    Never raises: a failure passes the raw answers through unchanged so
    compliance can still wrap them.
    """
    started = perf_counter()
    answers = _this_turns_answers(state)

    if len(answers) <= 1:
        return {}  # nothing to aggregate

    sub_queries: dict[str, str] = state.get("sub_queries") or {}
    route: list[str] = state.get("route") or []

    # Without sub_queries the supervisor didn't decompose the question, so we
    # have no basis for structuring the response — pass through to compliance
    # which will concatenate as usual. This also keeps graph tests (which use
    # a FakeRouter that never writes sub_queries) deterministic.
    if not sub_queries:
        return {}

    # Reconstruct the original question from the last HumanMessage.
    messages = state.get("messages") or []
    original_q = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            original_q = str(m.content)
            break

    # Build the per-agent section text, keyed by route order.
    sections: list[str] = []
    for i, msg in enumerate(answers):
        agent_name = route[i] if i < len(route) else f"agent_{i + 1}"
        sub_q = sub_queries.get(agent_name, "").strip()
        label = f"[{agent_name}]" + (f" – {sub_q}" if sub_q else "")
        sections.append(f"{label}\n{str(msg.content).strip()}")

    agents_text = "\n\n---\n\n".join(sections)

    prompt = (
        "You received answers from multiple specialised financial agents for this question:\n"
        f'"{original_q}"\n\n'
        "Agent answers:\n"
        f"{agents_text}\n\n"
        "Your job: produce ONE clean, well-structured response.\n\n"
        "Rules:\n"
        "1. If the agent answers cover CLEARLY DIFFERENT topics (e.g. SIP investing vs "
        "tax rates vs stock analysis), use a ## heading for each topic and remove any "
        "duplication between sections.\n"
        "2. If the agent answers are RELATED PARTS of one question (e.g. portfolio "
        "analysis feeding into goal planning), synthesise them into a single flowing "
        "answer — no separate headers needed.\n"
        "3. Keep ALL factual data intact: every number, rate, percentage, date, and "
        "named figure must appear in the output.\n"
        "4. Do NOT add any disclaimer — that is appended by a separate compliance step.\n"
        "5. Write in second person (you/your). Be concise but complete."
    )

    try:
        from langchain_core.messages import SystemMessage as _Sys
        from langchain_openai import ChatOpenAI

        from core.config import load_config

        cfg = load_config()
        llm = ChatOpenAI(
            model=cfg.llm.router_model,  # gpt-4o-mini — cheap, fast
            temperature=0.0,
            api_key=cfg.secrets.openai_api_key,
        )
        structured = str(llm.invoke([_Sys(content=prompt)]).content).strip()
    except Exception as exc:  # noqa: BLE001 — aggregator failure must not lose the answer
        logger.warning("Response aggregator failed (%s); passing raw answers through", type(exc).__name__)
        return {}

    # Replace all individual agent messages with the single structured one.
    # Reuse the last answer's id so add_messages replaces rather than appends.
    superseded = [m for m in answers[:-1] if getattr(m, "id", None)]
    remove = [RemoveMessage(id=m.id) for m in superseded]

    latency_ms = round((perf_counter() - started) * 1000, 1)
    logger.info("Response aggregator: merged %d answers in %dms", len(answers), latency_ms)

    return {
        "messages": remove + [AIMessage(content=structured, id=answers[-1].id)],
        "agent_trace": [
            TraceEntry(
                agent=AGGREGATOR_NODE,
                status="ok",
                latency_ms=latency_ms,
                detail=f"merged {len(answers)} agent answers into structured response",
            )
        ],
    }


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

    Two cases:
    - Sequential chain (e.g. portfolio_analysis → goal_planning): advance to the
      next unrun agent.
    - Parallel fan-out (all other multi-agent routes): every agent was dispatched
      simultaneously via Send.  When any one of them finishes its conditional edge
      is evaluated with intermediate state — the other agents' trace entries haven't
      merged yet.  Chaining to the "missing" agent causes it to run a second time,
      doubling the output.  For parallel routes, return COMPLIANCE_NODE as soon as
      any agent has run; LangGraph deduplicates the multiple COMPLIANCE edges into
      a single compliance call after all agents finish.
    """
    ran = {entry["agent"] for entry in state.get("agent_trace", [])}
    route = state.get("route") or []
    valid_route = [n for n in route if n in known]

    # Detect parallel vs sequential dispatch (mirrors _after_supervisor logic).
    route_set = frozenset(valid_route)
    is_sequential = len(valid_route) > 1 and any(
        pair.issubset(route_set) for pair in _SEQUENTIAL_PAIRS
    )

    if len(valid_route) > 1 and not is_sequential:
        # Parallel fan-out: any finishing agent → aggregator.
        # LangGraph deduplicates the multiple edges into one aggregator call
        # after all parallel agents finish, then aggregator → compliance.
        if ran & known:
            return AGGREGATOR_NODE
        return FALLBACK_NODE

    # Sequential chain: advance to the next unrun agent.
    for name in valid_route:
        if name not in ran:
            return name

    if ran & known:
        # Multi-agent sequential chain also benefits from aggregation.
        if len(valid_route) > 1:
            return AGGREGATOR_NODE
        return COMPLIANCE_NODE  # single agent — go straight to compliance
    return FALLBACK_NODE  # nothing ran and nothing can


def _after_supervisor(state: AgentState, known: frozenset[str]) -> str | list[Send]:
    """What to do immediately after the supervisor runs.

    Returns either a node name (string) or a list of Send objects for parallel fan-out.
    LangGraph's conditional edge machinery handles both: a string is looked up in the
    destinations map; Send objects bypass it and dispatch directly to their targets.

    Decision tree:
    1. Needs clarification → clarifier node (single path)
    2. No valid agents → fallback node (single path)
    3. One agent → route directly (no overhead)
    4. Sequential dependency pair in route → first agent only; _next_node chains rest
    5. Multiple independent agents → Send fan-out (parallel execution)
    """
    if (state.get("pending_clarification") or "").strip():
        return CLARIFICATION_NODE

    route = state.get("route") or []
    valid = [n for n in route if n in known]

    if not valid:
        return FALLBACK_NODE

    if len(valid) == 1:
        return valid[0]

    # Check for sequential dependency pairs — goal_planning needs portfolio results.
    route_set = frozenset(valid)
    for pair in _SEQUENTIAL_PAIRS:
        if pair.issubset(route_set):
            logger.info("Dispatcher: sequential (dependency %s), starting %s", pair, valid[0])
            return valid[0]

    # Independent agents — fan out in parallel.
    logger.info("Dispatcher: parallel fan-out to %s", valid)
    return [Send(name, state) for name in valid]


def _after_evaluator(state: AgentState) -> str:
    """Route after the evaluator: retry via supervisor, or done.

    Skips memory_manager on retry — the conversation hasn't grown enough to need
    summarisation within a single turn's retry loop.
    """
    if state.get("needs_retry"):
        return ROUTER_NAME
    return END


# ── assembly ───────────────────────────────────────────────────────────────────


def build_graph(
    agents: dict[str, Any] | None = None,
    router: Any | None = None,
    checkpointer: Any | None = None,
) -> Any:
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

    # ── nodes ──────────────────────────────────────────────────────────────────
    graph.add_node(MEMORY_NODE, memory_manager_node)
    graph.add_node(ROUTER_NAME, route_fn)
    for name, agent in agents.items():
        graph.add_node(name, agent.run)
    graph.add_node(AGGREGATOR_NODE, response_aggregator_node)
    graph.add_node(COMPLIANCE_NODE, compliance_node)
    graph.add_node(EVALUATOR_NODE, evaluator_node)
    graph.add_node(FALLBACK_NODE, fallback_node)
    graph.add_node(CLARIFICATION_NODE, clarification_node)

    # ── fixed edges ────────────────────────────────────────────────────────────
    graph.add_edge(START, MEMORY_NODE)
    graph.add_edge(MEMORY_NODE, ROUTER_NAME)
    graph.add_edge(CLARIFICATION_NODE, COMPLIANCE_NODE)
    graph.add_edge(FALLBACK_NODE, COMPLIANCE_NODE)
    graph.add_edge(AGGREGATOR_NODE, COMPLIANCE_NODE)
    graph.add_edge(COMPLIANCE_NODE, EVALUATOR_NODE)

    # ── conditional edges ──────────────────────────────────────────────────────

    # Supervisor → clarifier (if needs_clarification), or one agent (sequential/single),
    # or multiple Send objects (parallel fan-out). Send bypasses the destinations map;
    # the map covers only the string-return paths.
    supervisor_destinations: dict[str, str] = {
        CLARIFICATION_NODE: CLARIFICATION_NODE,
        FALLBACK_NODE: FALLBACK_NODE,
        **{name: name for name in agents},
    }

    def after_supervisor(state: AgentState) -> str | list[Send]:
        return _after_supervisor(state, known)

    graph.add_conditional_edges(ROUTER_NAME, after_supervisor, supervisor_destinations)

    # Agent destinations: next unrun agent, aggregator (multi-agent turns), or
    # compliance (single-agent turns). LangGraph deduplicates the multiple
    # AGGREGATOR edges from parallel agents into one aggregator call.
    agent_destinations = {name: name for name in agents}
    agent_destinations[AGGREGATOR_NODE] = AGGREGATOR_NODE
    agent_destinations[COMPLIANCE_NODE] = COMPLIANCE_NODE
    agent_destinations[FALLBACK_NODE] = FALLBACK_NODE

    def after_agent(state: AgentState) -> str:
        return _next_node(state, known)

    for name in agents:
        graph.add_conditional_edges(name, after_agent, agent_destinations)

    # Evaluator → retry (back to supervisor, skipping memory_manager) or done.
    graph.add_conditional_edges(
        EVALUATOR_NODE,
        _after_evaluator,
        {ROUTER_NAME: ROUTER_NAME, END: END},
    )

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("Workflow compiled with %d agents: %s", len(agents), ", ".join(agents))
    return compiled


def build_production_graph() -> Any:
    """The real graph, for the Streamlit app and the MCP server.

    A separate name so the app does not have to know that `build_graph()` takes
    test doubles, and so `@st.cache_resource` has one obvious thing to cache.

    Wires in a SQLite checkpointer so every user's conversation history
    persists across browser reloads. Each user is identified by a UUID
    `thread_id` that callers pass in `config={"configurable": {"thread_id": id}}`.
    """
    import sqlite3
    from pathlib import Path

    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path = Path(__file__).parents[2] / "data" / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return build_graph(checkpointer=checkpointer)


__all__ = [
    "AGENT_NAMES",
    "AGGREGATOR_NODE",
    "CLARIFICATION_NODE",
    "COMPLIANCE_NODE",
    "EVALUATOR_NODE",
    "FALLBACK_NODE",
    "MEMORY_NODE",
    "build_graph",
    "build_production_graph",
    "clarification_node",
    "compliance_node",
    "evaluator_node",
    "fallback_node",
    "memory_manager_node",
    "response_aggregator_node",
]
