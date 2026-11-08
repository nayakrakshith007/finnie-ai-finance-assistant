"""The shared contract every Finnie agent implements.

Why an abstract base class
--------------------------
Six agents need the same plumbing: build an LLM lazily, time the call, log it,
append a trace entry, and never let an exception escape into the graph. Writing
that six times guarantees six slightly different versions of it. `BaseAgent` is a
*template method*: `run()` is fixed and owns the plumbing, while each subclass
implements only `handle()`, the part that differs.

The error contract
------------------
`run()` never raises. An agent that throws returns a degraded state update
instead: a friendly message, `error` set, and a trace entry with status "error".
This matters because a node raising inside a LangGraph run aborts the whole
invocation -- one failing agent would take down a turn that other agents could
still have answered. The graph's fallback node (PRD FR-005) handles routing on
that `error` key; this is the inner layer of the same defence.

What this class deliberately does *not* do
------------------------------------------
It does not apply the compliance guard. Compliance is a single terminal node in
the graph (PRD FR-006) so that it cannot be bypassed by a new agent that forgets
to call it. Applying it per-agent as well would double-inject the disclaimer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any, ClassVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from core.llm import build_llm
from core.logging_setup import get_logger
from workflow.state import AgentState, TraceEntry

logger = get_logger(__name__)

# Shown to the user when an agent fails. Deliberately plain: it says what happened
# and what to do, names no internals, and leaks no stack trace.
FALLBACK_MESSAGE = (
    "I ran into a problem working that out and would rather say so than guess. "
    "Please try rephrasing the question, or ask me something else."
)


class BaseAgent(ABC):
    """Base class for all specialised agents.

    Subclasses must set `name` and `description`, and implement `handle()`.

    `name` is the routing key -- the supervisor emits it, the trace records it, and
    tests assert on it. `description` is what the router sees when deciding where a
    query belongs, so it is prompt text, not a code comment: write it for the model.
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    #: Override in a subclass to use the cheap routing model, or pin a specific one.
    model: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Fail at import time if a subclass forgot its identity.

        Catching this at class-definition time rather than at first call means a
        malformed agent cannot reach the graph -- the test suite fails on import
        instead of producing a mysterious empty route at runtime.
        """
        super().__init_subclass__(**kwargs)
        if ABC in cls.__bases__:  # an intermediate abstract class, not a leaf agent
            return
        for attr in ("name", "description"):
            if not getattr(cls, attr, ""):
                raise TypeError(f"{cls.__name__} must define a non-empty '{attr}'")

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        """Store an optional LLM. Nothing is built here.

        Construction stays cheap and offline on purpose: tests instantiate agents
        without an API key, and the graph builds all six at startup. The real client
        is created on first use by the `llm` property.
        """
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        """The chat model, built on first access and cached thereafter."""
        if self._llm is None:
            self._llm = build_llm(self.model)
        return self._llm

    # ── the fixed part ────────────────────────────────────────────────────────

    def run(self, state: AgentState) -> dict[str, Any]:
        """Invoke the agent and return a partial state update. Never raises.

        Returns only changed keys. `agent_trace` is always a single-element list
        because the state reducer appends rather than replaces (see
        `workflow.state`).
        """
        started = perf_counter()
        try:
            update = self.handle(state)
        except Exception as exc:  # noqa: BLE001 - deliberate boundary: see module docstring
            elapsed = (perf_counter() - started) * 1000
            # exception() logs the traceback for us; the user never sees it.
            logger.exception("Agent '%s' failed after %.0fms", self.name, elapsed)
            return {
                "messages": [AIMessage(content=FALLBACK_MESSAGE)],
                "error": f"{self.name}: {type(exc).__name__}: {exc}",
                "agent_trace": [
                    TraceEntry(
                        agent=self.name,
                        status="error",
                        latency_ms=round(elapsed, 1),
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                ],
            }

        elapsed = (perf_counter() - started) * 1000
        logger.info("Agent '%s' completed in %.0fms", self.name, elapsed)
        trace = TraceEntry(
            agent=self.name,
            status="ok",
            latency_ms=round(elapsed, 1),
            detail=self.trace_detail(update),
        )
        # Caller's trace entry would be overwritten by a subclass returning its own,
        # so ours goes last.
        return {**update, "agent_trace": [trace]}

    def trace_detail(self, update: dict[str, Any]) -> str:
        """One line for the trace, describing what this run produced.

        Default lists the keys written. Subclasses override to say something more
        useful, e.g. "4 docs retrieved, top distance 0.41".
        """
        keys = [k for k in update if k != "agent_trace"]
        return f"wrote: {', '.join(keys)}" if keys else "no state change"

    # ── shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _latest_question(state: AgentState) -> str:
        """The question this agent should answer.

        Prefers `resolved_question` -- the supervisor's rewrite, which has had
        references like "the second one" resolved into explicit names. Falls back
        to scanning backwards for the last human message, which is what happens
        when an agent is invoked directly (tests, the Portfolio tab's button) with
        no router ahead of it.

        Scanning backwards rather than taking messages[-1]: by the time a second
        agent runs in a composed turn (FR-003), the last message is the first
        agent's output, not the user's question.
        """
        resolved = (state.get("resolved_question") or "").strip()
        if resolved:
            return resolved
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content)
        raise ValueError("No HumanMessage in state; the agent has nothing to answer")

    # ── the part each agent implements ────────────────────────────────────────

    @abstractmethod
    def handle(self, state: AgentState) -> dict[str, Any]:
        """Do the agent's actual work and return a partial state update.

        Implementations may raise freely -- `run()` is the error boundary. They
        should return only the keys they changed, and must not return
        `agent_trace`, which `run()` owns.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
