"""The supervisor router — one node, two jobs (PRD FR-002, FR-004).

Job one: decide which agents handle this turn, in what order.
Job two: rewrite the question so it stands on its own.

Why the second job lives here
-----------------------------
"What about the second one?" is unanswerable in isolation, and every agent reads
the latest question rather than the whole history. The obvious fixes are both
bad: giving all six agents the full transcript multiplies prompt cost by six and
makes each agent's behaviour depend on turns it has nothing to do with, while a
separate rewriting call adds a round trip to every turn.

The router already reads the history, already runs on every turn, and already
returns structured output. Adding one field to that output makes follow-ups work
for all six agents at zero extra cost. The technique is contextual query
rewriting; `resolved_question` is where it lands, and `BaseAgent._latest_question`
prefers it over the raw message.

Why structured output and not parsing text
------------------------------------------
`with_structured_output` constrains the *shape* — a list of strings and a string
come back, or an exception does. It does not constrain the *values*: the model can
still return "crypto_advisor", or six agents, or the same agent twice. So
everything it returns is validated against the registry before it becomes control
flow. A route is a decision about what code runs next; it is the last place to
trust a model's word for it.

This node never raises. A routing outage degrades to the Q&A agent, which is the
one agent that can honestly refuse anything it cannot ground (FR-005).
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.config import load_config
from core.llm import build_router_llm
from core.logging_setup import get_logger
from workflow.registry import (
    AGENT_NAMES,
    DEFAULT_AGENT,
    MAX_AGENTS_PER_TURN,
    agent_catalogue,
)
from workflow.state import AgentState, TraceEntry

logger = get_logger(__name__)

ROUTER_NAME = "supervisor"


class RouteDecision(BaseModel):
    """What the router must return. The schema the model is constrained to."""

    agents: list[str] = Field(
        default_factory=list,
        description=(
            "The agent names that should handle this turn, in the order they "
            "should run. One for a simple question; two when the question "
            "genuinely needs both. Never more than two."
        ),
    )
    standalone_question: str = Field(
        default="",
        description=(
            "The user's latest question rewritten so it can be understood "
            "without the conversation history. Resolve pronouns and references "
            "like 'the second one' or 'that fund' into explicit names. If the "
            "question already stands alone, repeat it unchanged."
        ),
    )
    reasoning: str = Field(
        default="",
        description="One short clause on why these agents. Shown in the trace.",
    )


ROUTER_SYSTEM_PROMPT = """You are the supervisor of a multi-agent Indian personal \
finance assistant. You do not answer questions yourself. You decide which \
specialist agent handles each turn, and you rewrite the question so the chosen \
agent can understand it without the conversation history.

The agents available to you:

{catalogue}

Choosing agents:
- Pick ONE agent for a simple question. That is the normal case.
- Pick TWO, in order, only when the question genuinely needs both — for example \
"does my portfolio fit my 10-year goal?" needs portfolio_analysis then \
goal_planning, because the second needs what the first works out.
- Never pick more than two.
- If the question is conceptual, definitional, or you are unsure, pick \
{default_agent}. It is the only agent that can honestly say it does not know.
- If the question is not about personal finance at all, still pick \
{default_agent}: it will check its knowledge base and refuse properly.

Rewriting the question:
- Resolve every reference that depends on earlier turns. "What about the second \
one?" after a question comparing Reliance and TCS becomes "What is the TCS \
price?".
- Keep the user's meaning exactly. Do not add detail they did not give, do not \
answer the question, and do not make it more specific than they were.
- If it already stands alone, repeat it unchanged.

{profile}"""


class SupervisorRouter:
    """Classifies each turn to one or two agents and contextualises the question."""

    name = ROUTER_NAME

    def __init__(self, structured_llm: Any | None = None) -> None:
        """`structured_llm` is injected in tests; built lazily otherwise."""
        self._structured_llm = structured_llm

    @property
    def structured_llm(self) -> Any:
        """gpt-4o-mini with the decision schema bound, built on first use.

        The cheap model on purpose: this runs on every turn, so it is the
        highest-frequency LLM call in the app. Classification among six labelled
        options is well within `gpt-4o-mini`, and using `gpt-4o` here would be
        the single most expensive line in Finnie for no measurable gain.
        """
        if self._structured_llm is None:
            self._structured_llm = build_router_llm().with_structured_output(RouteDecision)
        return self._structured_llm

    # ── the node ──────────────────────────────────────────────────────────────

    def route(self, state: AgentState) -> dict[str, Any]:
        """Decide the route. Returns a partial state update; never raises."""
        started = perf_counter()
        question = self._latest_question(state)

        try:
            decision = self.structured_llm.invoke(self._prompt(state, question))
        except Exception as exc:  # noqa: BLE001 - deliberate boundary; see module docstring
            elapsed = (perf_counter() - started) * 1000
            logger.exception("Router failed after %.0fms; defaulting to %s", elapsed, DEFAULT_AGENT)
            return {
                "route": [DEFAULT_AGENT],
                "resolved_question": question,
                "agent_trace": [
                    TraceEntry(
                        agent=ROUTER_NAME,
                        status="error",
                        latency_ms=round(elapsed, 1),
                        detail=f"{type(exc).__name__}: {exc}; defaulted to {DEFAULT_AGENT}",
                    )
                ],
            }

        route = self._validate(decision)
        resolved = (getattr(decision, "standalone_question", "") or "").strip() or question
        elapsed = (perf_counter() - started) * 1000

        detail = f"routed to {', '.join(route)}"
        reasoning = (getattr(decision, "reasoning", "") or "").strip()
        if reasoning:
            detail += f" — {reasoning}"
        if resolved != question:
            # Worth recording: a rewritten question is the most likely cause of a
            # surprising answer, and the trace is where that gets diagnosed.
            detail += f'; rewrote as "{resolved}"'

        logger.info("Supervisor routed to %s", route)
        return {
            "route": route,
            "resolved_question": resolved,
            "agent_trace": [
                TraceEntry(
                    agent=ROUTER_NAME,
                    status="ok",
                    latency_ms=round(elapsed, 1),
                    detail=detail,
                )
            ],
        }

    # ── validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate(decision: Any) -> list[str]:
        """Turn whatever came back into a route that is safe to execute.

        Drops unknown names, collapses duplicates, preserves order, caps the
        length, and falls back to the default when nothing survives. Each of
        those is a thing a model has actually done.
        """
        raw = list(getattr(decision, "agents", None) or [])
        route: list[str] = []
        for name in raw:
            candidate = str(name).strip()
            if candidate in AGENT_NAMES and candidate not in route:
                route.append(candidate)
            elif candidate not in AGENT_NAMES:
                logger.warning("Router returned unknown agent %r; ignoring", candidate)

        if not route:
            logger.info("No usable route returned; defaulting to %s", DEFAULT_AGENT)
            return [DEFAULT_AGENT]
        return route[:MAX_AGENTS_PER_TURN]

    # ── prompt assembly ───────────────────────────────────────────────────────

    def _prompt(self, state: AgentState, question: str) -> list[Any]:
        profile = state.get("user_profile") or {}
        profile_text = (
            "What is known about this user: "
            + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in profile.items())
            if profile
            else "Nothing is known about this user yet."
        )

        system = ROUTER_SYSTEM_PROMPT.format(
            catalogue=agent_catalogue(),
            default_agent=DEFAULT_AGENT,
            profile=profile_text,
        )

        messages: list[Any] = [SystemMessage(content=system)]
        messages.extend(self._recent_history(state))
        if not messages[1:] or not isinstance(messages[-1], HumanMessage):
            messages.append(HumanMessage(content=question))
        return messages

    @staticmethod
    def _recent_history(state: AgentState) -> list[Any]:
        """The last N messages, oldest first.

        Bounded because the router runs every turn: an unbounded transcript is an
        unbounded prompt on the highest-frequency call in the app. N comes from
        `config.yaml: memory.max_recent_messages` (FR-004).
        """
        try:
            window = load_config().memory.max_recent_messages
        except Exception:  # noqa: BLE001 - a missing config must not break routing
            window = 10

        history = [
            message
            for message in state.get("messages", [])
            if isinstance(message, HumanMessage | AIMessage)
        ]
        return history[-window:]

    @staticmethod
    def _latest_question(state: AgentState) -> str:
        """The user's latest words, or a neutral default when a button invoked us."""
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return "Analyse what I have given you."
