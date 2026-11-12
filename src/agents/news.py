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

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Max headlines per individual search query.
_PER_QUERY_LIMIT = 5
# Max total headlines passed to the LLM after fan-out and deduplication.
_FANOUT_LIMIT = 12
# Minimum word count in the query to trigger LLM decomposition.
_DECOMPOSE_THRESHOLD = 4

_DECOMPOSE_SYSTEM = """You are a search query generator for a financial news tool.
Given a topic and original question, produce 2-3 short search queries that together
give comprehensive news coverage from different angles.

Rules:
- Each query must be 3-7 words, specific and directly searchable
- Cover different angles: the event itself, the market/economic impact, specific entities
- For India-focused questions always include an India-angle query
- Return ONLY a JSON array of strings — no explanation, no markdown fence

Example input: topic="US Iran war 2026 India oil markets", question="how is the Iran war affecting Indian markets"
Example output: ["US Iran war 2026 latest", "Iran war crude oil prices", "India stock market geopolitical risk"]"""

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

NEWS_SYSTEM_PROMPT = """You are Finnie's market intelligence desk — a senior \
analyst with a hedge fund macro background. You read news the way a fund manager \
reads the overnight tape: strip out noise, identify what actually moves money, \
surface the second-order effects most retail investors miss, and frame every \
development in terms of capital flows, sector rotation and risk/reward shifts.

You will be given headlines with their publisher and age. These may come from \
multiple searches covering different angles of the same topic.

ANALYSIS FRAMEWORK:

0. **Direct Answer** — ALWAYS open with 2–5 sentences that DIRECTLY answer the \
question, written from your financial domain knowledge, INDEPENDENT of the \
headlines. These sentences must be complete even if the headlines were removed. \
**Comparison rule (critical):** if the question uses "vs", "versus", "increases \
vs decreases", "hike vs cut", "if X / if Y", or asks about two scenarios, you \
MUST explain BOTH scenarios from domain knowledge — the headlines will only cover \
whichever is currently in the news, so you must supply the other side yourself. \
Example for a "rate hike vs cut" question:\
 "When the Fed **raises** rates, US yields climb — FPIs pull money OUT of Indian \
equities to capture higher US returns, the INR weakens, and India's import bill in \
INR terms rises (especially crude oil). When the Fed **cuts** rates, US yields fall \
and EMs become relatively attractive again — FPIs push money INTO Indian equities \
(risk-on), the INR strengthens, equities and bonds rally, and cheaper crude in INR \
reduces India's current account deficit." After the domain-knowledge answer, \
transition to what the current headlines show about the scenario in the news.

1. **Lead line** — one bold sentence: the single most market-relevant development \
and its directional effect on Indian markets. No hedging, no filler. \
Example: "**US Fed holds but signals one more hike — EM outflow pressure builds, \
INR at risk.**"

2. For macro / geopolitical questions, use THREE sections:

### What is happening
3–4 bullets — facts only from the headlines. What event, what numbers, who \
decided what. No inference here.

### Market impact analysis
3–5 bullets. Think like a portfolio manager: what does this mean for money flows, \
prices and risk? Cover:
- **FPI/DII flows** — direction and magnitude of pressure (why hot money moves)
- **INR pressure** — USD/INR direction and import cost implications
- **Sector rotation** — which sectors face tailwinds vs headwinds (IT exporters \
vs oil importers, rate-sensitives, defensives, etc.)
- **Second-order effects** — the non-obvious chain reactions. Example for a Fed \
hike: USD strengthens → crude oil expensive in USD → India's import bill rises → \
current account deficit widens → more INR depreciation pressure → imported \
inflation. Mark inferences clearly as "Implication:".
- **Bond / commodity linkage** — crude oil, gold, bond yields if relevant

### What to watch next
2–3 bullets: the specific data prints, policy decisions or price levels that \
would change this picture materially. Gives the reader an actionable mental model.

For a **company or sector** question: skip the three sections. Use labelled bullets \
but apply the same rigour — earnings catalysts, margin drivers, peer comparisons, \
valuation context if the headlines mention it.

RULES:
3. Two sources of knowledge — use both:
   - **Headlines** = what is happening RIGHT NOW. For current-events bullets, only \
use facts from the provided headlines. Mark inferences from headlines with "Implication:".
   - **Domain knowledge** = how markets work (mechanisms, relationships, theory). \
You MUST use this for conceptual questions and for the Direct Answer (step 0). \
Label domain-knowledge sentences with "Domain knowledge:" when they appear inside \
the headline-based sections, so the reader knows what is established fact vs. \
general financial principle.
   - For compound questions ("hike vs. cut", "India vs. US", "before and after"), \
address EVERY scenario or side — do not answer only the half covered by headlines.
4. Never predict specific prices or index levels.
5. Sentiment: if you characterise it, label it UNCERTAIN and explain the basis — \
a handful of wire headlines is not a reliable sentiment read.
6. Note headline age when any item is more than 5 days old.
7. Do NOT write a disclaimer or closing caveat. One is appended automatically.
8. No recommendation of any kind — not to buy, sell, hold or watch.
9. Use proper finance vocabulary without over-explaining: FPI, DII, risk-off, \
duration risk, yield curve, basis points, forward guidance, spread widening, \
current account deficit. The reader is learning — the terminology itself teaches.
10. If fewer than three headlines directly address the question, say so and ask \
what specific angle to dig into.

FORMAT:
- **Direct Answer** (plain prose, 1–3 sentences) first — no section header needed, \
no preamble like "Certainly!" or "Great question"
- **Bold lead summary line** next
- Each bullet: **bold 3–5 word label** — then 1–2 dense sentences
- **Bold** all company names, index names, key figures (%, bps, price levels)
- Use `###` section headers exactly as shown above for macro questions

Headlines:
{data}"""

NEWS_USER_TEMPLATE = "{question}"


class NewsSynthesizerAgent(BaseAgent):
    """Fetches recent headlines for a ticker or theme and summarises them."""

    name = "news_synthesizer"
    description = (
        "Fetches and summarises recent news headlines for an Indian company, a "
        "market index, a sector, or a macro/geopolitical event affecting Indian "
        "markets — war, elections, RBI policy, budget, global risk-off events. "
        "Use this when the user asks what is happening, what the latest news is, "
        "why markets have moved, or how a current event is affecting equities, "
        "mutual funds or the economy. Do NOT use it for the price itself (that "
        "is market analysis) or for how an instrument works in general (finance Q&A)."
    )

    limit = _PER_QUERY_LIMIT

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
        primary_query = self.resolve_topic(question)

        if not primary_query:
            logger.info("No news topic found in the question; asking for one")
            return {"messages": [AIMessage(content=NO_TOPIC_REPLY)]}

        # Fan out into multiple parallel searches for complex topics.
        # Simple queries (single ticker, short phrase) stay as one search.
        headlines = self._fan_out_search(primary_query, question)

        if not headlines:
            return {"messages": [AIMessage(content=NEWS_UNAVAILABLE_REPLY)]}

        # Pass the original user question (not the sub-query) to the LLM so the
        # answer addresses what the user actually asked, not just the search terms.
        original_question = (state.get("resolved_question") or "").strip() or question
        messages = [
            SystemMessage(content=NEWS_SYSTEM_PROMPT.format(data=self._for_prompt(headlines))),
            HumanMessage(content=NEWS_USER_TEMPLATE.format(question=original_question)),
        ]
        body = str(self.llm.invoke(messages).content).rstrip()
        body += "\n\n" + self._sources_block(headlines)

        return {
            "messages": [AIMessage(content=body)],
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
                "news_query": primary_query,
            },
        }

    # ── fan-out search ────────────────────────────────────────────────────────

    def _fan_out_search(self, primary_query: str, original_question: str) -> list[Headline]:
        """Run multiple targeted searches in parallel and merge the results.

        Simple queries (a ticker symbol, ≤3 words) make one search — backward
        compatible with tests and fast for the common case. Complex queries
        (macro events, geopolitical situations) are decomposed into 2-3 search
        variants that cover different angles, then run concurrently.
        """
        queries = self._generate_search_queries(primary_query, original_question)
        logger.info("News fan-out: %d queries for %r", len(queries), primary_query)

        if len(queries) == 1:
            try:
                return self.feed.headlines(queries[0], limit=self.limit)
            except Exception as exc:  # noqa: BLE001 - an outage is an answer, not an error
                logger.warning("News feed failed for %r: %s", queries[0], type(exc).__name__)
                return []

        seen_urls: set[str] = set()
        merged: list[Headline] = []

        with ThreadPoolExecutor(max_workers=len(queries)) as executor:
            futures = {
                executor.submit(self.feed.headlines, q, self.limit): q
                for q in queries
            }
            for future in as_completed(futures):
                try:
                    for h in future.result():
                        if h.url not in seen_urls:
                            seen_urls.add(h.url)
                            merged.append(h)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Fan-out query failed: %s", type(exc).__name__)

        # Sort by recency (freshest first) and cap the total
        merged.sort(key=lambda h: h.published or "", reverse=True)
        return merged[:_FANOUT_LIMIT]

    def _generate_search_queries(self, primary_query: str, original_question: str) -> list[str]:
        """Return 1-3 search queries for the topic.

        A ticker or short query returns a single-element list (no extra LLM
        call). A complex multi-word query uses a cheap LLM call to generate
        angle-specific variants, with a fallback to the primary query if the
        call fails or the response is malformed.
        """
        is_ticker = "." in primary_query or primary_query.startswith("^")
        word_count = len(primary_query.split())

        if is_ticker or word_count < _DECOMPOSE_THRESHOLD:
            return [primary_query]

        try:
            return self._llm_decompose(primary_query, original_question)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Query decomposition failed (%s); falling back to single search",
                type(exc).__name__,
            )
            return [primary_query]

    def _llm_decompose(self, primary_query: str, original_question: str) -> list[str]:
        """Use gpt-4o-mini to generate 2-3 angle-specific search queries.

        Returns the primary_query as a single-element fallback if the response
        cannot be parsed as a JSON list of strings.
        """
        from langchain_core.messages import HumanMessage as HM, SystemMessage as SM
        from langchain_openai import ChatOpenAI

        from core.config import load_config

        cfg = load_config()
        cheap_llm = ChatOpenAI(
            model=cfg.llm.router_model,
            temperature=0.0,
            api_key=cfg.secrets.openai_api_key,
        )

        user_msg = (
            f'topic="{primary_query}"\n'
            f'question="{original_question}"'
        )
        response = str(
            cheap_llm.invoke([SM(content=_DECOMPOSE_SYSTEM), HM(content=user_msg)]).content
        ).strip()

        # Strip any accidental markdown code fences the model adds
        response = re.sub(r"^```[a-z]*\s*|\s*```$", "", response).strip()

        queries = json.loads(response)
        if isinstance(queries, list) and all(isinstance(q, str) and q.strip() for q in queries):
            result = [q.strip() for q in queries[:3]]
            logger.debug("Decomposed %r into %d queries: %s", primary_query, len(result), result)
            return result

        return [primary_query]

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
