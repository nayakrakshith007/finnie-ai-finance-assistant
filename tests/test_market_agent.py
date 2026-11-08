"""Acceptance tests for the Market Analysis Agent (PRD FR-011, FR-033).

Specification, not description: written before the implementation. Offline and
deterministic — a fake MarketDataService and `FakeListChatModel`, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.market import NO_SYMBOL_REPLY, MarketAnalysisAgent
from core.llm import build_fake_llm
from data.market import OutOfScopeError, Quote, QuoteSource, Trend
from workflow.state import new_state

NOW = datetime(2026, 11, 8, 10, 30, tzinfo=UTC)


# ── doubles ────────────────────────────────────────────────────────────────────


def quote(symbol="RELIANCE.NS", price=1500.0, previous=1480.0, source=QuoteSource.LIVE) -> Quote:
    return Quote(
        symbol=symbol,
        price=price,
        previous_close=previous,
        currency="INR",
        as_of=NOW.isoformat(),
        source=source,
        name=symbol,
    )


def trend(days=30, closes=(1400.0, 1450.0, 1500.0)) -> Trend:
    return Trend(symbol="RELIANCE.NS", days=days, closes=closes)


class FakeMarketService:
    """Answers with canned quotes/trends and records what was asked of it."""

    def __init__(
        self,
        quotes: dict[str, Quote] | None = None,
        trends: dict[int, Trend] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.quotes = quotes if quotes is not None else {"RELIANCE.NS": quote()}
        self.trends = trends if trends is not None else {}
        self.raises = raises
        self.quote_calls: list[str] = []
        self.trend_calls: list[str] = []

    def get_quote(self, raw_symbol: str, **_kw: Any) -> Quote:
        self.quote_calls.append(raw_symbol)
        if self.raises is not None:
            raise self.raises
        key = raw_symbol.upper()
        key = key if key in self.quotes else f"{key}.NS"
        if key not in self.quotes:
            raise OutOfScopeError(f"No Indian listing found for {key!r}.")
        return self.quotes[key]

    def get_trends(self, raw_symbol: str, windows: tuple[int, ...] = (30, 90)) -> dict[int, Trend]:
        self.trend_calls.append(raw_symbol)
        return self.trends


def agent_with(
    service: FakeMarketService, responses: list[str] | None = None
) -> MarketAnalysisAgent:
    return MarketAnalysisAgent(
        llm=build_fake_llm(responses or ["Reliance is up 1.35% today."]),
        service=service,
    )


# ── identity ───────────────────────────────────────────────────────────────────


def test_agent_declares_name_and_description():
    assert MarketAnalysisAgent.name == "market_analysis"
    assert len(MarketAnalysisAgent.description) > 40


# ── symbol extraction ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How is RELIANCE doing?", ["RELIANCE"]),
        ("what is the price of TCS", ["TCS"]),
        ("reliance price today", ["RELIANCE"]),
        ("How is the nifty today?", ["^NSEI"]),
        ("sensex update please", ["^BSESN"]),
        ("nifty 50 level", ["^NSEI"]),
        ("bank nifty", ["^NSEBANK"]),
        ("Compare TCS and INFY", ["TCS", "INFY"]),
        ("HDFCBANK.NS quote", ["HDFCBANK.NS"]),
    ],
)
def test_symbols_are_extracted_from_the_question(question, expected):
    assert MarketAnalysisAgent.extract_symbols(question) == expected


def test_common_words_are_not_mistaken_for_tickers():
    """'How is the market today' must not resolve HOW, IS or THE as a ticker."""
    assert MarketAnalysisAgent.extract_symbols("How is the market doing today?") == []


def test_extraction_is_capped():
    """A long list of symbols is a prompt-cost and latency hazard, not a feature."""
    many = " ".join(["RELIANCE", "TCS", "INFY", "WIPRO", "SBIN", "ITC"])
    assert len(MarketAnalysisAgent.extract_symbols(many)) <= 3


# ── the happy path ─────────────────────────────────────────────────────────────


def test_quote_is_written_to_state():
    service = FakeMarketService()
    update = agent_with(service).run(new_state("How is RELIANCE doing?"))

    data = update["market_data"]["RELIANCE.NS"]
    assert data["price"] == 1500.0
    assert data["change_pct"] == 1.35
    assert data["source"] == QuoteSource.LIVE
    assert data["currency"] == "INR"


def test_answer_is_returned_as_an_ai_message():
    update = agent_with(FakeMarketService()).run(new_state("RELIANCE price?"))
    assert isinstance(update["messages"][0], AIMessage)
    assert "1.35%" in update["messages"][0].content


def test_trend_windows_reach_state_and_the_prompt():
    service = FakeMarketService(trends={30: trend(30), 90: trend(90, (1200.0, 1500.0))})
    update = agent_with(service).run(new_state("How is RELIANCE doing?"))

    trends = update["market_data"]["RELIANCE.NS"]["trends"]
    assert set(trends) == {"30d", "90d"}
    assert trends["30d"]["change_pct"] == 7.14
    assert trends["90d"]["direction"] == "up"


def test_multiple_symbols_are_each_quoted():
    service = FakeMarketService(
        quotes={
            "TCS.NS": quote("TCS.NS", 2500.0, 2490.0),
            "INFY.NS": quote("INFY.NS", 1600.0, 1620.0),
        }
    )
    update = agent_with(service).run(new_state("Compare TCS and INFY"))

    assert set(update["market_data"]) == {"TCS.NS", "INFY.NS"}
    assert len(service.quote_calls) == 2


def test_uses_the_most_recent_question_in_a_multi_turn_state():
    service = FakeMarketService(quotes={"TCS.NS": quote("TCS.NS")})
    state = new_state("How is RELIANCE doing?")
    state["messages"].append(AIMessage(content="Reliance is up."))
    state["messages"].append(HumanMessage(content="And TCS?"))

    agent_with(service).run(state)
    assert service.quote_calls == ["TCS"]


# ── no symbol ──────────────────────────────────────────────────────────────────


def test_no_symbol_asks_for_one_without_calling_the_llm():
    class ExplodingLLM:
        def invoke(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("the LLM must not be called with no symbol")

    service = FakeMarketService()
    agent = MarketAnalysisAgent(llm=ExplodingLLM(), service=service)
    update = agent.run(new_state("How is the market doing today?"))

    assert update["messages"][0].content == NO_SYMBOL_REPLY
    assert service.quote_calls == []
    assert update["agent_trace"][0]["status"] == "ok", "asking for a ticker is not an error"


# ── out of scope (FR-011) ──────────────────────────────────────────────────────


def test_foreign_ticker_returns_a_clear_out_of_scope_message():
    service = FakeMarketService(quotes={})
    update = agent_with(service).run(new_state("How is AAPL doing?"))

    body = update["messages"][0].content
    assert "AAPL" in body
    assert "NSE" in body or "Indian" in body
    assert update.get("error") is None, "out of scope is an answer, not a failure"


def test_out_of_scope_does_not_reach_the_llm():
    class ExplodingLLM:
        def invoke(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("no LLM call for a symbol we cannot quote")

    agent = MarketAnalysisAgent(llm=ExplodingLLM(), service=FakeMarketService(quotes={}))
    agent.run(new_state("AAPL price?"))  # must not raise


def test_one_bad_symbol_does_not_sink_the_good_one():
    service = FakeMarketService(quotes={"TCS.NS": quote("TCS.NS", 2500.0, 2490.0)})
    update = agent_with(service).run(new_state("Compare TCS and AAPL"))

    assert set(update["market_data"]) == {"TCS.NS"}
    assert "AAPL" in update["messages"][0].content


# ── provenance (FR-033) ────────────────────────────────────────────────────────


def test_degraded_quote_is_labelled_for_the_user():
    service = FakeMarketService(quotes={"RELIANCE.NS": quote(source=QuoteSource.STALE_CACHE)})
    update = agent_with(service).run(new_state("RELIANCE price?"))

    assert "STALE" in update["messages"][0].content
    assert update["market_data"]["RELIANCE.NS"]["is_degraded"] is True


def test_mock_quote_is_never_presented_as_real():
    service = FakeMarketService(quotes={"RELIANCE.NS": quote(source=QuoteSource.MOCK)})
    update = agent_with(service).run(new_state("RELIANCE price?"))
    assert "SAMPLE DATA" in update["messages"][0].content


def test_freshness_reaches_the_prompt_not_only_the_suffix():
    """The model must know the data is stale, or it will narrate it as today's move."""
    service = FakeMarketService(quotes={"RELIANCE.NS": quote(source=QuoteSource.STALE_CACHE)})
    captured: list[Any] = []

    class CapturingLLM:
        def invoke(self, messages: Any, *a: Any, **k: Any) -> Any:
            captured.append(messages)
            return AIMessage(content="An answer.")

    MarketAnalysisAgent(llm=CapturingLLM(), service=service).run(new_state("RELIANCE?"))
    prompt = " ".join(str(m.content) for m in captured[0])
    assert "STALE" in prompt


# ── interpretation, not prediction ─────────────────────────────────────────────


def test_prompt_forbids_prediction_and_recommendation():
    from agents.market import MARKET_SYSTEM_PROMPT

    lowered = MARKET_SYSTEM_PROMPT.lower()
    assert "predict" in lowered
    assert "recommend" in lowered or "advice" in lowered


def test_agent_does_not_append_the_disclaimer():
    """Compliance is one terminal graph node (FR-006); applying it here double-injects."""
    update = agent_with(FakeMarketService(), responses=["Plain answer."]).run(
        new_state("RELIANCE?")
    )
    assert update["messages"][0].content.startswith("Plain answer.")
    assert "not financial advice" not in update["messages"][0].content.lower()


# ── trace ──────────────────────────────────────────────────────────────────────


def test_trace_names_the_symbols_and_the_provenance():
    service = FakeMarketService(trends={30: trend()})
    detail = agent_with(service).run(new_state("RELIANCE?"))["agent_trace"][0]["detail"]
    assert "RELIANCE.NS" in detail
    assert QuoteSource.LIVE in detail


# ── the error boundary ─────────────────────────────────────────────────────────


def test_service_failure_degrades_instead_of_raising():
    service = FakeMarketService(raises=ConnectionError("yfinance exploded"))
    update = agent_with(service).run(new_state("RELIANCE?"))

    assert update["agent_trace"][0]["status"] == "error"
    assert "ConnectionError" in update["error"]
    assert "yfinance" not in update["messages"][0].content.lower()


# ── laziness ───────────────────────────────────────────────────────────────────


def test_constructing_the_agent_builds_no_service(monkeypatch):
    def explode(*a: Any, **k: Any):
        raise AssertionError("MarketDataService must not be built during __init__")

    monkeypatch.setattr("agents.market.MarketDataService", explode)
    MarketAnalysisAgent()  # must not raise
