"""Acceptance tests for the news feed and the News Synthesizer (PRD FR-014).

Offline. The two payload fixtures below are the two shapes yfinance has shipped —
flat up to ~0.2.40, nested under "content" from ~0.2.50 — because pinning to one
means a version bump silently returns zero headlines, which is indistinguishable
from a quiet news day.

Yahoo's news endpoint was down on 2026-11-08 (quotes were fine), so the outage
path here is the one that was observed live and the parsing is checked against
fixtures rather than a live response.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from agents.news import NEWS_UNAVAILABLE_REPLY, NO_TOPIC_REPLY, NewsSynthesizerAgent
from core.llm import build_fake_llm
from data.news import Headline, YFinanceNewsFeed, _normalise
from workflow.state import new_state

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

# yfinance <= ~0.2.40
FLAT_ITEM: dict[str, Any] = {
    "title": "Reliance Q2 profit rises 9% on retail strength",
    "publisher": "Business Standard",
    "link": "https://example.com/reliance-q2",
    "providerPublishTime": 1762560000,  # 2025-11-08 UTC
    "type": "STORY",
}

# yfinance >= ~0.2.50
NESTED_ITEM: dict[str, Any] = {
    "id": "abc123",
    "content": {
        "title": "TCS wins multi-year deal with European retailer",
        "summary": "The contract runs for five years.",
        "pubDate": "2026-11-07T09:30:00Z",
        "provider": {"displayName": "Mint"},
        "canonicalUrl": {"url": "https://example.com/tcs-deal"},
    },
}


class FakeNewsFeed:
    def __init__(self, headlines=None, raises=None):
        self._headlines = headlines if headlines is not None else [
            Headline("Reliance Q2 profit rises 9%", "Business Standard",
                     "https://example.com/a", "2026-11-07T09:00:00+00:00"),
            Headline("Refining margins steady", "Mint",
                     "https://example.com/b", "2026-11-06T09:00:00+00:00"),
        ]
        self.raises = raises
        self.queries: list[str] = []

    def headlines(self, query: str, limit: int = 5) -> list[Headline]:
        self.queries.append(query)
        if self.raises:
            raise self.raises
        return self._headlines[:limit]


def agent(feed=None, responses=None) -> NewsSynthesizerAgent:
    return NewsSynthesizerAgent(
        llm=build_fake_llm(responses or ["- Profit rose 9%.\n- Margins steady."]),
        feed=feed or FakeNewsFeed(),
    )


# ── parsing both payload shapes ────────────────────────────────────────────────


def test_the_flat_payload_shape_is_parsed():
    headline = _normalise(FLAT_ITEM)
    assert headline.title == "Reliance Q2 profit rises 9% on retail strength"
    assert headline.publisher == "Business Standard"
    assert headline.url == "https://example.com/reliance-q2"
    assert headline.published.startswith("2025-11-08")


def test_the_nested_payload_shape_is_parsed():
    headline = _normalise(NESTED_ITEM)
    assert headline.title == "TCS wins multi-year deal with European retailer"
    assert headline.publisher == "Mint"
    assert headline.url == "https://example.com/tcs-deal"
    assert headline.published == "2026-11-07T09:30:00Z"


def test_an_item_with_no_link_is_dropped():
    """FR-014 wants every bullet attributable; an unciteable bullet is worse than
    one fewer bullet, because the link is what makes the summary checkable."""
    assert _normalise({"title": "Something happened", "publisher": "X"}) is None


def test_an_item_with_no_title_is_dropped():
    assert _normalise({"link": "https://example.com/x"}) is None


def test_a_nested_item_falls_back_to_the_click_through_url():
    item = {"content": {"title": "T", "clickThroughUrl": {"url": "https://example.com/c"}}}
    assert _normalise(item).url == "https://example.com/c"


def test_a_missing_publisher_is_named_rather_than_blank():
    assert _normalise({"title": "T", "link": "https://e.com"}).publisher == "unknown source"


def test_junk_is_rejected_without_raising():
    for junk in (None, "a string", 42, [], {}):
        assert _normalise(junk) is None


def test_an_unparseable_date_is_not_fatal():
    item = {"content": {"title": "T", "canonicalUrl": {"url": "https://e.com"},
                        "pubDate": "not a date"}}
    assert _normalise(item).age_days() is None


# ── headline age ───────────────────────────────────────────────────────────────


def test_age_in_days_is_computed():
    headline = Headline("T", "P", "https://e.com", "2026-11-06T12:00:00+00:00")
    assert headline.age_days(NOW) == 2.0


def test_age_is_none_without_a_date():
    assert Headline("T", "P", "https://e.com").age_days(NOW) is None


def test_a_naive_timestamp_is_assumed_utc_not_rejected():
    headline = Headline("T", "P", "https://e.com", "2026-11-06T12:00:00")
    assert headline.age_days(NOW) == 2.0


# ── the feed's own resilience ───────────────────────────────────────────────────


def test_the_feed_returns_empty_when_yahoo_is_down(monkeypatch):
    """Observed live on 2026-11-08: Ticker.news raised "YAHOO! FINANCE IS
    CURRENTLY DOWN". A news outage must not end a turn the other agents could
    still have answered."""

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***")

    monkeypatch.setattr("yfinance.Ticker", Boom)
    monkeypatch.setattr("yfinance.Search", Boom)
    assert YFinanceNewsFeed().headlines("RELIANCE.NS") == []


def test_the_feed_deduplicates_the_same_wire_story():
    """Yahoo repeats one wire story across providers; five identical bullets are
    not five bullets."""
    items = [FLAT_ITEM, dict(FLAT_ITEM, publisher="Another Paper"), NESTED_ITEM]
    feed = YFinanceNewsFeed()
    feed._fetch_raw = lambda *a, **k: items  # noqa: SLF001
    assert len(feed.headlines("RELIANCE.NS")) == 2


def test_the_feed_respects_the_limit():
    feed = YFinanceNewsFeed()
    feed._fetch_raw = lambda *a, **k: [  # noqa: SLF001
        dict(FLAT_ITEM, link=f"https://example.com/{i}") for i in range(20)
    ]
    assert len(feed.headlines("RELIANCE.NS", limit=5)) == 5


def test_an_empty_query_fetches_nothing():
    assert YFinanceNewsFeed().headlines("   ") == []


# ── the agent ──────────────────────────────────────────────────────────────────


def test_agent_declares_name_and_description():
    assert NewsSynthesizerAgent.name == "news_synthesizer"
    assert len(NewsSynthesizerAgent.description) > 40


def test_a_ticker_in_the_question_is_used_as_the_query():
    feed = FakeNewsFeed()
    agent(feed).run(new_state("Any news on RELIANCE?"))
    assert feed.queries == ["RELIANCE.NS"]


def test_an_index_alias_resolves_before_searching():
    feed = FakeNewsFeed()
    agent(feed).run(new_state("What is the news on nifty?"))
    assert feed.queries == ["^NSEI"]


def test_a_theme_with_no_ticker_is_searched_as_text():
    """FR-014 covers "a ticker or theme", so a themed question still gets a route."""
    feed = FakeNewsFeed()
    agent(feed).run(new_state("Any news about Indian IT sector hiring?"))
    assert feed.queries and feed.queries[0] != ""
    assert "nifty" not in feed.queries[0].lower()


def test_headlines_are_written_to_state():
    update = agent().run(new_state("Any news on RELIANCE?"))
    items = update["market_data"]["news"]

    assert len(items) == 2
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["publisher"] == "Business Standard"


def test_the_answer_is_an_ai_message():
    update = agent().run(new_state("Any news on RELIANCE?"))
    assert isinstance(update["messages"][0], AIMessage)


def test_source_links_are_appended_by_code():
    """FR-014 requires source links on every bullet. Appending them means a model
    that ignores the instruction still produces an attributable answer."""
    update = agent(responses=["- Profit rose 9%."]).run(new_state("news on RELIANCE"))
    body = update["messages"][0].content
    assert "https://example.com/a" in body
    assert "https://example.com/b" in body


def test_at_most_five_headlines_are_requested():
    feed = FakeNewsFeed(headlines=[
        Headline(f"H{i}", "P", f"https://example.com/{i}") for i in range(10)
    ])
    update = agent(feed).run(new_state("news on RELIANCE"))
    assert len(update["market_data"]["news"]) <= 5


# ── no news ────────────────────────────────────────────────────────────────────


def test_no_headlines_says_so_without_calling_the_llm():
    class ExplodingLLM:
        def invoke(self, *a: Any, **k: Any) -> Any:
            raise AssertionError("nothing to summarise, nothing to pay for")

    update = NewsSynthesizerAgent(llm=ExplodingLLM(), feed=FakeNewsFeed(headlines=[])).run(
        new_state("news on RELIANCE")
    )
    assert update["messages"][0].content == NEWS_UNAVAILABLE_REPLY
    assert update["agent_trace"][0]["status"] == "ok", "an outage is not an agent error"


def test_a_feed_that_raises_is_handled_as_an_outage():
    update = agent(FakeNewsFeed(raises=RuntimeError("yahoo down"))).run(
        new_state("news on RELIANCE")
    )
    assert update["messages"][0].content == NEWS_UNAVAILABLE_REPLY
    assert "yahoo" not in update["messages"][0].content.lower()


def test_a_question_with_no_topic_at_all_asks_for_one():
    update = agent().run(new_state("What is the news?"))
    assert update["messages"][0].content == NO_TOPIC_REPLY


# ── sentiment must be flagged uncertain (FR-014) ───────────────────────────────


def test_the_prompt_requires_sentiment_to_be_flagged_uncertain():
    from agents.news import NEWS_SYSTEM_PROMPT

    lowered = NEWS_SYSTEM_PROMPT.lower()
    assert "sentiment" in lowered
    assert "uncertain" in lowered or "not reliable" in lowered


def test_the_prompt_caps_the_bullets_at_five():
    from agents.news import NEWS_SYSTEM_PROMPT

    assert "five" in NEWS_SYSTEM_PROMPT.lower() or "5 " in NEWS_SYSTEM_PROMPT


def test_the_prompt_forbids_prediction():
    from agents.news import NEWS_SYSTEM_PROMPT

    assert "predict" in NEWS_SYSTEM_PROMPT.lower()


def test_headline_age_reaches_the_prompt():
    """A six-week-old story narrated as "recent news" is a lie Yahoo invites, as
    it mixes ages freely in one response."""
    captured: list[Any] = []

    class CapturingLLM:
        def invoke(self, messages, *a, **k):
            captured.append(messages)
            return AIMessage(content="- A bullet.")

    feed = FakeNewsFeed(headlines=[
        Headline("Old story", "P", "https://e.com/old", "2026-09-01T09:00:00+00:00")
    ])
    NewsSynthesizerAgent(llm=CapturingLLM(), feed=feed).run(new_state("news on RELIANCE"))
    prompt = " ".join(str(m.content) for m in captured[0])
    assert "days old" in prompt or "age" in prompt.lower()


def test_agent_does_not_append_the_disclaimer():
    update = agent(responses=["- A bullet."]).run(new_state("news on RELIANCE"))
    assert "not financial advice" not in update["messages"][0].content.lower()


# ── trace ──────────────────────────────────────────────────────────────────────


def test_trace_records_the_query_and_the_count():
    detail = agent().run(new_state("news on RELIANCE"))["agent_trace"][0]["detail"]
    assert "RELIANCE.NS" in detail
    assert "2" in detail


# ── laziness ───────────────────────────────────────────────────────────────────


def test_constructing_the_agent_builds_no_feed(monkeypatch):
    def explode(*a: Any, **k: Any):
        raise AssertionError("build_news_feed must not run during __init__")

    monkeypatch.setattr("agents.news.build_news_feed", explode)
    NewsSynthesizerAgent()


@pytest.mark.parametrize("question", ["news on TCS", "latest on nifty", "updates about INFY"])
def test_a_range_of_phrasings_find_a_topic(question):
    feed = FakeNewsFeed()
    agent(feed).run(new_state(question))
    assert feed.queries, f"no topic found in {question!r}"


# ── acronyms are not stopwords (found live 2026-11-08) ────────────────────────


@pytest.mark.parametrize(
    ("question", "must_contain"),
    [
        ("news about Indian IT sector hiring", "IT"),
        ("any news on the RBI rate decision", "RBI"),
        ("latest on GST changes", "GST"),
        ("news about NAV reporting rules", "NAV"),
    ],
)
def test_an_acronym_survives_stopword_filtering(question, must_contain):
    """IT the sector is not "it" the pronoun.

    Lowercasing before the stopword check turned "Indian IT sector hiring" into
    "Indian sector hiring" — losing the only word that identified the sector. The
    same collision waits for RBI, GST, FD and NAV.
    """
    topic = NewsSynthesizerAgent.resolve_topic(question)
    assert must_contain in topic.split(), f"{must_contain!r} was dropped from {topic!r}"


def test_ordinary_stopwords_are_still_dropped():
    topic = NewsSynthesizerAgent.resolve_topic("what is the latest news about banking")
    assert "the" not in topic.lower().split()
    assert "banking" in topic.lower()


# ── the equity cap is stated, not inferred (found live 2026-11-08) ────────────


def test_a_long_horizon_states_that_equity_was_not_capped():
    """gpt-4o told a user with a 12-year horizon that "equity is capped at 50%
    because the horizon is relatively short". The cap had not fired and 12 years
    is not short; the conditional prompt rule was applied unconditionally. The
    cap status is now a fact in the data block."""
    from agents.goal import GoalPlanningAgent
    from workflow.state import new_state as fresh

    captured: list[Any] = []

    class CapturingLLM:
        def invoke(self, messages, *a, **k):
            captured.append(messages)
            return AIMessage(content="A plan.")

    GoalPlanningAgent(llm=CapturingLLM()).run(fresh("I need 50 lakh in 12 years"))
    prompt = " ".join(str(m.content) for m in captured[0])
    assert "Horizon equity cap: not applied" in prompt


def test_a_short_horizon_states_that_equity_was_capped():
    from agents.goal import GoalPlanningAgent
    from workflow.state import new_state as fresh

    captured: list[Any] = []

    class CapturingLLM:
        def invoke(self, messages, *a, **k):
            captured.append(messages)
            return AIMessage(content="A plan.")

    GoalPlanningAgent(llm=CapturingLLM()).run(
        fresh("I need 5 lakh in 2 years", profile={"risk_appetite": "aggressive"})
    )
    prompt = " ".join(str(m.content) for m in captured[0])
    assert "Horizon equity cap: applied" in prompt
