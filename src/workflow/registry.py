"""The one list of agents (PRD FR-002, FR-016).

The router prompt and the graph both need to know which agents exist. Two lists
would drift: an agent added to the graph but missing from the prompt is
unreachable, and one named in the prompt but absent from the graph routes to a
node that is not there. So both read this.

`agent_catalogue()` builds the router's menu from each agent's own `description`,
which is why those descriptions are written as prompt text rather than as
comments — `BaseAgent` says so, and this is where that pays off. Adding a
seventh agent means writing the class and adding it to `AGENT_CLASSES`; nothing
else changes.
"""

from __future__ import annotations

from agents.base import BaseAgent
from agents.goal import GoalPlanningAgent
from agents.market import MarketAnalysisAgent
from agents.news import NewsSynthesizerAgent
from agents.portfolio import PortfolioAnalysisAgent
from agents.qa import FinanceQAAgent
from agents.stock import StockDeepDiveAgent
from agents.tax import TaxEducationAgent

# Order matters only for the router prompt's readability: the general-purpose
# agent goes last so the specific ones are read first.
AGENT_CLASSES: tuple[type[BaseAgent], ...] = (
    MarketAnalysisAgent,
    StockDeepDiveAgent,
    PortfolioAnalysisAgent,
    GoalPlanningAgent,
    TaxEducationAgent,
    NewsSynthesizerAgent,
    FinanceQAAgent,
)

AGENT_NAMES: tuple[str, ...] = tuple(cls.name for cls in AGENT_CLASSES)

# Where an unroutable or unrecognised query goes. The Q&A agent is the right
# default because it is the only one that can honestly refuse: it retrieves, finds
# nothing relevant, and says so (FR-002).
DEFAULT_AGENT = FinanceQAAgent.name

# A turn runs at most this many agents. FR-003 asked for two; raised to three so
# that "current event + portfolio + goal" questions can chain all three in one
# turn without a second round trip. Each agent is at least one LLM call, so this
# is still a hard upper bound — an unbounded route is an unbounded bill.
MAX_AGENTS_PER_TURN = 3


def agent_catalogue() -> str:
    """The router's menu: each agent's name and its own description."""
    return "\n\n".join(f"- {cls.name}: {cls.description}" for cls in AGENT_CLASSES)


def build_agents() -> dict[str, BaseAgent]:
    """One instance of each agent, keyed by name.

    Cheap: every agent's `__init__` is deliberately lazy, so this builds six
    objects without an API key, a Chroma index or a network call. The graph can
    therefore be constructed at import time and in tests.
    """
    return {cls.name: cls() for cls in AGENT_CLASSES}
