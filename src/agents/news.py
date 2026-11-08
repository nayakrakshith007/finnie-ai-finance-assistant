"""News Synthesizer Agent — recent headlines, summarised (PRD FR-014).

Topic resolution, in order
--------------------------
1. A ticker or index alias in the question, reusing `MarketAnalysisAgent`'s
   extractor so "nifty" resolves to `^NSEI` in both agents rather than in two
   slightly different ways.
2. Otherwise the question's own content words as a free-text search, which is how
   FR-014's "or theme" gets a route at all.
3. Nothing usable — ask, rather than searching for "the news" and summarising
   whatever the world happened to be doing.

The two things appended in code
-------------------------------
**Source links.** FR-014 requires them on every bullet. They are concatenated
after the model returns, so an answer stays attributable even if the model drops
the URLs — which it does, because URLs are long and models compress.

**Headline age.** Yahoo mixes a story from this morning with one from six weeks
ago in the same response, so the age of each item goes into the prompt and the
oldest age goes into the answer. "Recent news" about a six-week-old story is a
lie the feed invites.

Sentiment
---------
FR-014 says to flag it as uncertain, and the prompt does. Inferring mood from
five headlines a wire service chose is not sentiment analysis, and a confident
"sentiment: positive" would be the most quotable wrong thing Finnie could say
about a stock.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.market import MarketAnalysisAgent
from core.logging_setup import get_logger
from data.market import OutOfScopeError, normalise_symbol
from data.news import DEFAULT_LIMIT, Headline, build_news_feed
from workflow.state import AgentState

logger = get_logger(__name__)

NO_TOPIC_REPLY = (
    "Which company, index or theme would you like the news on? I can look up "
    "headlines for an NSE or BSE listed company (Reliance, TCS), for NIFTY 50 or "
    "SENSEX, or for a topic like \"Indian IT sector\" or \"RBI rate decision\"."
)

NEWS_UNAVAILABLE_REPLY = (
    "I could not fetch any headlines just now — the news feed is not responding. "
    "This is a problem at my end rather than a quiet news day, so it is worth "
    "trying again shortly. I can still answer questions about prices, your "
    "portfolio, tax rules or financial concepts in the meantime."
)

# Words that carry no search value. A query of "what is the news about" returns
# the world's news, which is not what was asked.
_STOPWORD_TEXT = """
a an and any about are as at be been but by can could did do does for from
get give had has have how i if in into is it its latest me my news of on or
please recent said say see should show so some tell that the their there
these they this to told up update updates was what when where which who why
will with would you your
"""
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())  # noqa: SIM905 - prose is the readable form

NEWS_SYSTEM_PROMPT = """You are Finnie's news summariser, explaining recent \
Indian market headlines to a beginner.

You will be given headlines with their publisher and age. Work only from those.

Rules:
1. At most FIVE bullets. One fact per bullet, in plain English.
2. Summarise only what the headlines actually say. Do not add background from \
memory, and do not infer a cause the headline does not state.
3. Never predict. Do not say what a price will do, and do not describe news as \
good or bad for an investor.
4. If you describe the overall sentiment at all, flag it as UNCERTAIN and say \
why: five headlines chosen by a wire service are not a reliable read on \
sentiment, and a headline's tone often has nothing to do with a company's \
prospects.
5. Note the age of the headlines if any are more than a few days old. Do not \
call a three-week-old story recent.
6. Do NOT write a disclaimer or closing caveat. One is appended automatically.
7. No recommendation of any kind — not to buy, sell, hold or watch.

Headlines:
{data}"""

NEWS_USER_TEMPLATE = "{question}"


class NewsSynthesizerAgent(BaseAgent):
    """Fetches recent headlines for a ticker or theme and summarises them."""

    name = "news_synthesizer"
    description = (
        "Fetches and summarises recent news headlines for an Indian company, an "
        "index, or a market theme, with a source link for each item. Use this "
        "when the user asks what is happening with a company, what the latest "
        "news or updates are, or why something has moved. Do NOT use it for the "
        "price itself (that is market analysis) or for how an instrument works "
        "(finance Q&A)."
    )

    limit = DEFAULT_LIMIT

    def __init__(self, llm: BaseChatModel | None = None, feed: Any | None = None) -> None:
        super().__init__(llm=llm)
        self._feed = feed

    @property
    def feed(self) -> Any:
        """Built on first use, so constructing the agent touches no network."""
        if self._feed is None:
            self._feed = build_news_feed()
        return self._feed

    # ── the work ──────────────────────────────────────────────────────────────

    def handle(self, state: AgentState) -> dict[str, Any]:
        question = self._latest_question(state)
        query = self.resolve_topic(question)

        if not query:
            logger.info("No news topic found in the question; asking for one")
            return {"messages": [AIMessage(content=NO_TOPIC_REPLY)]}

        try:
            headlines = self.feed.headlines(query, limit=self.limit)
        except Exception as exc:  # noqa: BLE001 - an outage is an answer, not an error
            logger.warning("News feed failed for %r: %s", query, type(exc).__name__)
            headlines = []

        if not headlines:
            # No LLM call: there is nothing to summarise, and the honest reply is
            # a fixed string rather than a generated apology.
            return {"messages": [AIMessage(content=NEWS_UNAVAILABLE_REPLY)]}

        messages = [
            SystemMessage(content=NEWS_SYSTEM_PROMPT.format(data=self._for_prompt(headlines))),
            HumanMessage(content=NEWS_USER_TEMPLATE.format(question=question)),
        ]
        body = str(self.llm.invoke(messages).content).rstrip()
        body += "\n\n" + self._sources_block(headlines)

        return {
            "messages": [AIMessage(content=body)],
            # Under `market_data` rather than a new state key: this is external
            # market information, and FR-001 fixes the declared keys.
            "market_data": {
                "news": [
                    {
                        "title": h.title,
                        "publisher": h.publisher,
                        "url": h.url,
                        "published": h.published,
                        "age_days": h.age_days(),
                    }
                    for h in headlines
                ],
                "news_query": query,
            },
        }

    def trace_detail(self, update: dict[str, Any]) -> str:
        data = update.get("market_data") or {}
        items = data.get("news")
        if not items:
            return "no headlines retrieved"
        ages = [i["age_days"] for i in items if i["age_days"] is not None]
        detail = f"{len(items)} headlines for {data.get('news_query', '?')}"
        if ages:
            detail += f", newest {min(ages):.1f}d old, oldest {max(ages):.1f}d"
        return detail

    # ── topic resolution ──────────────────────────────────────────────────────

    @classmethod
    def resolve_topic(cls, question: str) -> str:
        """A ticker if the question names one, otherwise its content words.

        Reusing `MarketAnalysisAgent.extract_symbols` on purpose: "nifty" must
        mean `^NSEI` in both agents, and two independent alias tables would
        eventually disagree.
        """
        symbols = MarketAnalysisAgent.extract_symbols(question)
        if symbols:
            # The extractor returns a bare ticker -- the market service
            # normalises at fetch time. The news feed has no such step, and
            # yf.Ticker("RELIANCE") resolves to a non-existent US listing rather
            # than failing, so the suffix has to be applied here.
            try:
                return normalise_symbol(symbols[0])
            except OutOfScopeError:
                return symbols[0]

        words = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z&-]+", question or "")
            if not cls._is_stopword(word)
        ]
        return " ".join(words[:6])

    @staticmethod
    def _is_stopword(word: str) -> bool:
        """Stopword matching that spares acronyms.

        An all-caps token is an acronym, not the English word that happens to
        share its letters. Without this, "Indian IT sector hiring" searches for
        "Indian sector hiring" -- because IT the sector collides with "it" the
        pronoun. The same trap waits for RBI, GST, FD and NAV. Found live on
        2026-11-08.
        """
        if word.isupper() and len(word) >= 2:
            return False
        return word.lower() in _STOPWORDS

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _for_prompt(headlines: list[Headline]) -> str:
        lines = []
        for index, headline in enumerate(headlines, start=1):
            age = headline.age_days()
            stamp = f"{age:.1f} days old" if age is not None else "age unknown"
            lines.append(f"{index}. \"{headline.title}\" — {headline.publisher} ({stamp})")
        return "\n".join(lines)

    @staticmethod
    def _sources_block(headlines: list[Headline]) -> str:
        """Links appended in code, because FR-014 makes them non-optional."""
        lines = ["**Sources**"]
        for headline in headlines:
            age = headline.age_days()
            stamp = f", {age:.0f}d ago" if age is not None else ""
            lines.append(f"- [{headline.title}]({headline.url}) — {headline.publisher}{stamp}")
        return "\n".join(lines)
