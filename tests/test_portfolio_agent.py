"""Acceptance tests for the Portfolio Analysis Agent (PRD FR-012, FR-033).

Specification, not description: written before the implementation. Offline —
a fake market service and `FakeListChatModel`, no network and no API key.

The agent's job is narrow by design: read holdings out of state, get a price for
each one, hand both to the pure `analyse()` function, and narrate the result. All
the arithmetic lives in `portfolio/metrics.py` where it is checked against hand
calculations, so what is tested here is the plumbing and the judgement calls —
which prices it asks for, what it does when one is missing, and what it refuses
to put in a log line.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from agents.portfolio import NO_HOLDINGS_REPLY, PortfolioAnalysisAgent
from core.llm import build_fake_llm
from data.market import OutOfScopeError, Quote, QuoteSource
from workflow.state import new_state

NOW = datetime(2026, 11, 8, 10, 30, tzinfo=UTC)

ROWS = [
    {"symbol": "RELIANCE", "quantity": 50, "asset_class": "stock", "avg_cost": 800},
    {"symbol": "TCS", "quantity": 20, "asset_class": "stock"},
    {"symbol": "HDFCFLEXI", "quantity": 20, "asset_class": "mutual_fund",
     "price": 1000, "expense_ratio": 1.2},
    {"symbol": "LIQUIDCASH", "quantity": 10, "asset_class": "cash", "price": 1000},
]


class FakeMarketService:
    """Prices market-traded symbols; records which ones it was asked for."""

    def __init__(self, prices: dict[str, float] | None = None, source=QuoteSource.LIVE):
        self.prices = prices if prices is not None else {"RELIANCE.NS": 1000.0, "TCS.NS": 1000.0}
        self.source = source
        self.asked: list[str] = []

    def get_quote(self, symbol: str, **_kw: Any) -> Quote:
        self.asked.append(symbol)
        if symbol not in self.prices:
            raise OutOfScopeError(f"No Indian listing found for {symbol!r}.")
        return Quote(
            symbol=symbol,
            price=self.prices[symbol],
            previous_close=self.prices[symbol],
            currency="INR",
            as_of=NOW.isoformat(),
            source=self.source,
            name=symbol,
        )


def state_with(rows, question="How is my portfolio doing?"):
    state = new_state(question)
    state["portfolio"] = {"holdings": list(rows)}
    return state


def agent_with(service=None, responses=None) -> PortfolioAnalysisAgent:
    return PortfolioAnalysisAgent(
        llm=build_fake_llm(responses or ["Your portfolio leans heavily on equity."]),
        service=service or FakeMarketService(),
    )


# ── identity ───────────────────────────────────────────────────────────────────


def test_agent_declares_name_and_description():
    assert PortfolioAnalysisAgent.name == "portfolio_analysis"
    assert len(PortfolioAnalysisAgent.description) > 40


# ── the happy path ─────────────────────────────────────────────────────────────


def test_analysis_is_written_to_state():
    update = agent_with().run(state_with(ROWS))
    analysis = update["portfolio"]["analysis"]

    # 50x1000 + 20x1000 + 20x1000 + 10x1000 = 1,00,000
    assert analysis["total_value"] == 100_000.0
    assert analysis["holding_count"] == 4
    assert analysis["risk_band"] == "moderate"
    assert analysis["diversification_score"] == 60


def test_the_users_own_rows_are_preserved_in_state():
    """`portfolio.holdings` is input and `portfolio.analysis` is output.

    Overwriting the input with the analysis would mean a second turn had nothing
    left to re-analyse after a price moved.
    """
    update = agent_with().run(state_with(ROWS))
    assert len(update["portfolio"]["holdings"]) == 4
    assert update["portfolio"]["holdings"][0]["symbol"] == "RELIANCE"


def test_an_answer_is_returned_as_an_ai_message():
    update = agent_with().run(state_with(ROWS))
    assert isinstance(update["messages"][0], AIMessage)
    assert "equity" in update["messages"][0].content


# ── which prices it asks for ───────────────────────────────────────────────────


def test_only_market_traded_holdings_are_looked_up():
    """The fund and the cash balance carry their own price, so asking yfinance
    for 'HDFCFLEXI' would be a guaranteed miss and a wasted call."""
    service = FakeMarketService()
    agent_with(service).run(state_with(ROWS))
    assert service.asked == ["RELIANCE.NS", "TCS.NS"]


def test_a_user_supplied_price_is_used_and_labelled():
    update = agent_with().run(state_with(ROWS))
    rows = {r["symbol"]: r for r in update["portfolio"]["analysis"]["holdings"]}
    assert rows["HDFCFLEXI"]["price"] == 1000.0
    assert rows["HDFCFLEXI"]["source"] == "user"


def test_a_user_supplied_price_is_not_treated_as_degraded():
    """It is not stale market data; it is what the user told us their fund is worth."""
    update = agent_with().run(state_with(ROWS))
    assert update["portfolio"]["analysis"]["is_degraded"] is False


def test_each_symbol_is_priced_once_even_if_asked_about_twice():
    rows = [
        {"symbol": "RELIANCE", "quantity": 10, "asset_class": "stock"},
        {"symbol": "RELIANCE", "quantity": 15, "asset_class": "stock"},
    ]
    service = FakeMarketService()
    agent_with(service).run(state_with(rows))
    assert service.asked == ["RELIANCE.NS"], "duplicates merge before pricing"


# ── missing prices ─────────────────────────────────────────────────────────────


def test_an_unpriceable_holding_is_excluded_and_named():
    service = FakeMarketService(prices={"RELIANCE.NS": 1000.0})
    update = agent_with(service).run(state_with(ROWS))
    analysis = update["portfolio"]["analysis"]

    assert analysis["unpriced"] == ["TCS.NS"]
    assert analysis["total_value"] == 80_000.0, "TCS must not be valued at zero"
    assert "TCS.NS" in update["messages"][0].content


def test_a_price_failure_does_not_sink_the_whole_analysis():
    class BrokenService:
        def get_quote(self, symbol, **kw):
            raise ConnectionError("feed down")

    update = agent_with(BrokenService()).run(state_with(ROWS))
    analysis = update["portfolio"]["analysis"]

    # The fund and cash still have their own prices, so there is still an answer.
    assert analysis["total_value"] == 30_000.0
    assert sorted(analysis["unpriced"]) == ["RELIANCE.NS", "TCS.NS"]
    assert update["agent_trace"][0]["status"] == "ok"


# ── empty and malformed input ──────────────────────────────────────────────────


def test_no_portfolio_in_state_asks_for_one_without_calling_the_llm():
    class ExplodingLLM:
        def invoke(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("nothing to analyse, nothing to pay for")

    agent = PortfolioAnalysisAgent(llm=ExplodingLLM(), service=FakeMarketService())
    update = agent.run(new_state("How is my portfolio doing?"))

    assert update["messages"][0].content == NO_HOLDINGS_REPLY
    assert update["agent_trace"][0]["status"] == "ok", "an empty portfolio is not an error"


def test_an_empty_holdings_list_asks_for_holdings():
    update = agent_with().run(state_with([]))
    assert update["messages"][0].content == NO_HOLDINGS_REPLY


def test_malformed_rows_are_reported_specifically():
    rows = [
        {"symbol": "RELIANCE", "quantity": 50, "asset_class": "stock"},
        {"symbol": "TCS", "quantity": "ten"},
    ]
    update = agent_with().run(state_with(rows))

    body = update["messages"][0].content
    assert "row 2" in body
    assert "ten" in body
    assert update["portfolio"]["analysis"]["holding_count"] == 1, "the good row still counts"


def test_every_row_malformed_reports_errors_and_calls_no_llm():
    class ExplodingLLM:
        def invoke(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("no valid holdings means nothing to narrate")

    agent = PortfolioAnalysisAgent(llm=ExplodingLLM(), service=FakeMarketService())
    update = agent.run(state_with([{"symbol": "", "quantity": "x"}]))
    assert "row 1" in update["messages"][0].content


# ── privacy: CLAUDE.md constraint 3 ────────────────────────────────────────────


def test_the_portfolio_is_never_written_to_the_log(caplog):
    """"Never log a user's full portfolio." Counts and totals are fine; symbols,
    quantities and rupee values are not — logs outlive the session and get shipped
    to places the holdings should not go."""
    with caplog.at_level(logging.DEBUG):
        agent_with().run(state_with(ROWS))

    logged = " ".join(record.getMessage() for record in caplog.records)
    for leak in ("RELIANCE", "HDFCFLEXI", "100000", "1,00,000", "50"):
        assert leak not in logged, f"{leak!r} leaked into the log"


def test_the_prompt_carries_the_portfolio_but_the_trace_does_not():
    """The model needs the numbers; the trace is rendered in the UI and logged."""
    update = agent_with().run(state_with(ROWS))
    detail = update["agent_trace"][0]["detail"]

    assert "RELIANCE" not in detail
    assert "4 holdings" in detail


# ── provenance (FR-033) ────────────────────────────────────────────────────────


def test_a_stale_price_is_surfaced_to_the_user():
    service = FakeMarketService(source=QuoteSource.STALE_CACHE)
    update = agent_with(service).run(state_with(ROWS))

    assert update["portfolio"]["analysis"]["is_degraded"] is True
    assert "stale" in update["messages"][0].content.lower()


def test_freshness_reaches_the_prompt():
    service = FakeMarketService(source=QuoteSource.MOCK)
    captured: list[Any] = []

    class CapturingLLM:
        def invoke(self, messages, *a: Any, **k: Any):
            captured.append(messages)
            return AIMessage(content="An answer.")

    PortfolioAnalysisAgent(llm=CapturingLLM(), service=service).run(state_with(ROWS))
    prompt = " ".join(str(m.content) for m in captured[0])
    assert "mock" in prompt.lower() or "sample" in prompt.lower()


# ── education, not advice ──────────────────────────────────────────────────────


def test_prompt_forbids_recommending_trades():
    from agents.portfolio import PORTFOLIO_SYSTEM_PROMPT

    lowered = PORTFOLIO_SYSTEM_PROMPT.lower()
    assert "recommend" in lowered or "advice" in lowered
    assert "rebalance" in lowered, "the one word a portfolio agent is most tempted by"


def test_agent_does_not_append_the_disclaimer():
    update = agent_with(responses=["Plain answer."]).run(state_with(ROWS))
    assert update["messages"][0].content.startswith("Plain answer.")
    assert "not financial advice" not in update["messages"][0].content.lower()


# ── the error boundary ─────────────────────────────────────────────────────────


def test_an_unexpected_failure_degrades_instead_of_raising(monkeypatch):
    def explode(*a: Any, **k: Any):
        raise RuntimeError("metrics blew up")

    monkeypatch.setattr("agents.portfolio.analyse", explode)
    update = agent_with().run(state_with(ROWS))

    assert update["agent_trace"][0]["status"] == "error"
    assert "RuntimeError" in update["error"]
    assert "metrics blew up" not in update["messages"][0].content


# ── laziness ───────────────────────────────────────────────────────────────────


def test_constructing_the_agent_builds_no_service(monkeypatch):
    def explode(*a: Any, **k: Any):
        raise AssertionError("MarketDataService must not be built during __init__")

    monkeypatch.setattr("agents.portfolio.MarketDataService", explode)
    PortfolioAnalysisAgent()


@pytest.mark.parametrize("key", ["concentration_warning_pct", "risk_weights"])
def test_policy_comes_from_config_not_the_agent(key):
    """Thresholds live in config.yaml; the agent must read them, not define them."""
    import inspect

    import agents.portfolio as module

    source = inspect.getsource(module)
    assert f"cfg.portfolio.{key}" in source or f"portfolio.{key}" in source
