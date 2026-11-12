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
            "genuinely needs both; three for complex questions that need current "
            "news plus portfolio context plus goal impact. Never more than three."
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
    sub_queries: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "A focused search or retrieval query for each agent you chose. "
            "news_synthesizer: 5-8 keywords covering the event AND its market "
            "angle (e.g. 'US Iran war 2026 India oil markets impact'). "
            "finance_qa / tax_education: the specific concept or rule to "
            "retrieve (e.g. 'Section 80C ELSS lock-in'). "
            "market_analysis: just the ticker or index name. "
            "portfolio_analysis / goal_planning: omit — they read the user's "
            "portfolio, not a knowledge base. "
            "Only include agents listed in `agents`."
        ),
    )
    needs_clarification: str = Field(
        default="",
        description=(
            "If the question is about the user's personal tax, portfolio or "
            "goal situation AND the user has not provided the required numbers "
            "(income, holdings, target amount, time horizon), write ONE focused "
            "question to ask them. Leave empty when the question is general, "
            "numbers were already given, or you can answer with reasonable "
            "assumptions. Ask sparingly — once per conversation topic at most."
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
- Pick TWO or THREE, in order, only when the question genuinely needs them all.

news_synthesizer examples (geopolitical / macro / "what is happening NOW"):
  · "how is the Iran war affecting Indian markets?" → news_synthesizer
  · "how is USA/Israel vs Iran impacting Indian stock market?" → news_synthesizer
  · "what is the outlook for Indian markets given the conflict?" → news_synthesizer
  · "what is the impact of [any current event] on Indian equities/currency/economy?" → news_synthesizer
  · "what is the latest news on RBI policy/elections/budget?" → news_synthesizer
  · "why did the market fall/rise today?" → news_synthesizer
  · "given the war, should I stay in equities?" → news_synthesizer, finance_qa
  · "given the war, is my portfolio ok?" → news_synthesizer, portfolio_analysis

finance_qa examples (conceptual / how-does-it-work / static knowledge):
  · "what is a SIP?" → finance_qa
  · "how does LTCG tax work?" → finance_qa (or tax_education)
  · "what is the difference between ELSS and PPF?" → finance_qa

- RULE: Any question that asks about the IMPACT or OUTLOOK of a named current \
event, conflict, geopolitical situation, policy or macro development on Indian \
markets → ALWAYS news_synthesizer. This includes "outlook", "impact", "effect", \
"what will happen", "how will markets react" when tied to a real-world event. \
Do NOT route these to finance_qa — the knowledge base has no live news.
- RULE: If the question mentions ANY current event or uses words like "war", \
"conflict", "sanctions", "elections", "RBI policy", "budget", "crash", "rally" \
in the context of CURRENT markets → ALWAYS start with news_synthesizer.
- Never pick more than three.
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

Writing sub_queries:
- For each agent you chose, write the best possible search or retrieval query \
for that agent's data source. This is NOT a rewrite of the question — it is a \
focused retrieval key. Examples:
  · User asks "how is the Iran war affecting Indian markets?" \
→ news_synthesizer sub_query: "US Israel Iran war 2026 India oil equity markets"
  · User asks "what is 80C?" \
→ finance_qa sub_query: "Section 80C deduction limit instruments ELSS PPF"
  · User asks "what is TCS price?" \
→ market_analysis sub_query: "TCS.NS"
- portfolio_analysis and goal_planning read the user's portfolio from state — \
give them no sub_query.

Asking for clarification:
- Only set needs_clarification when you genuinely cannot proceed: a tax \
calculation needs income, a goal feasibility check needs a target and horizon. \
Do NOT ask if the question is general knowledge. Do NOT ask if the user already \
gave numbers in this conversation. One question only, phrased simply.

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
            # OpenAI strict structured-output mode rejects dict[str,str] fields;
            # function_calling mode is flexible and handles arbitrary schemas.
            self._structured_llm = build_router_llm().with_structured_output(
                RouteDecision, method="function_calling"
            )
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
            # Apply the geo-override even on LLM failure so geopolitical questions
            # still reach news_synthesizer when the structured-output call errors out.
            fallback = self._apply_geo_override(question, [DEFAULT_AGENT])
            return {
                "route": fallback,
                "resolved_question": question,
                "sub_queries": {},
                "pending_clarification": "",
                "agent_trace": [
                    TraceEntry(
                        agent=ROUTER_NAME,
                        status="error",
                        latency_ms=round(elapsed, 1),
                        detail=f"{type(exc).__name__}: {exc}; defaulted to {fallback[0]}",
                    )
                ],
            }

        route = self._validate(decision)
        route = self._apply_geo_override(question, route)
        resolved = (getattr(decision, "standalone_question", "") or "").strip() or question
        sub_queries = dict(getattr(decision, "sub_queries", None) or {})
        clarification = (getattr(decision, "needs_clarification", "") or "").strip()
        elapsed = (perf_counter() - started) * 1000

        detail = f"routed to {', '.join(route)}"
        reasoning = (getattr(decision, "reasoning", "") or "").strip()
        if reasoning:
            detail += f" — {reasoning}"
        if resolved != question:
            detail += f'; rewrote as "{resolved}"'
        if sub_queries:
            detail += f"; sub_queries for {', '.join(sub_queries)}"
        if clarification:
            detail += "; needs clarification"

        logger.info("Supervisor routed to %s", route)
        return {
            "route": route,
            "resolved_question": resolved,
            "sub_queries": sub_queries,
            "pending_clarification": clarification,
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

    # Geopolitical context words that signal "current event" questions.
    _GEO_WORDS = frozenset({
        "war", "conflict", "iran", "israel", "russia", "ukraine", "sanctions",
        "ceasefire", "attack", "strike", "invasion", "tension", "geopolit",
        "us-china", "china-india", "border clash", "military",
    })
    # Phrases that signal the user wants impact/outlook analysis (not how-it-works).
    _IMPACT_WORDS = frozenset({
        "impact", "impacting", "affect", "affecting", "outlook",
        "effect on", "how will", "what will happen", "rally", "crash",
        "what is happening", "latest news", "current",
    })
    # Words that signal the user wants investment/sector advice — in those cases
    # finance_qa is also needed alongside news_synthesizer, so we don't override
    # to news_synthesizer alone; we let the LLM route to both.
    _INVESTMENT_WORDS = frozenset({
        "invest", "investing", "investment", "sector", "sectors", "stock",
        "stocks", "buy", "sell", "portfolio", "allocate", "allocation",
        "should i", "optimise", "optimize", "rebalance", "which", "strategy",
    })

    @classmethod
    def _apply_geo_override(cls, question: str, route: list[str]) -> list[str]:
        """Force news_synthesizer to the front when the question is a pure
        geopolitical-impact question that the LLM may misroute to finance_qa.

        Does NOT override when the question is about investment decisions or sector
        selection — those need finance_qa alongside news_synthesizer, and the LLM
        (now using function_calling mode) can make that call correctly.
        """
        q = question.lower()
        is_geo = any(w in q for w in cls._GEO_WORDS)
        is_impact = any(w in q for w in cls._IMPACT_WORDS)
        if not (is_geo and is_impact):
            return route
        # Investment/sector questions need finance_qa too — don't force a single agent.
        if any(w in q for w in cls._INVESTMENT_WORDS):
            logger.info("Geo-impact override skipped: investment/sector question detected")
            return route
        if "news_synthesizer" not in route:
            # LLM missed it entirely — override to news_synthesizer alone.
            logger.info("Geo-impact override: replacing %s with news_synthesizer", route)
            return ["news_synthesizer"]
        if route[0] != "news_synthesizer":
            # LLM found it but put it in the wrong position — promote it.
            logger.info("Geo-impact override: promoting news_synthesizer to front of %s", route)
            return ["news_synthesizer"] + [a for a in route if a != "news_synthesizer"]
        return route

    # ── prompt assembly ───────────────────────────────────────────────────────

    def _prompt(self, state: AgentState, question: str) -> list[Any]:
        profile = state.get("user_profile") or {}
        profile_text = (
            "What is known about this user: "
            + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in profile.items())
            if profile
            else "Nothing is known about this user yet."
        )

        session_summary = (state.get("session_summary") or "").strip()
        if session_summary:
            profile_text += f"\n\nConversation background (earlier turns, summarised): {session_summary}"

        retry_hint = (state.get("retry_hint") or "").strip()
        if retry_hint:
            profile_text += f"\n\nRETRY CONTEXT: {retry_hint}"

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
