"""Market Analysis Agent — yfinance quotes, interpreted (PRD FR-011, FR-033).

Terminology
-----------
Call it **yfinance data**, never "NSE data" or "exchange data". yfinance reads
Yahoo Finance, which redistributes the exchange feed with a delay of roughly 15
minutes. The listings covered are NSE and BSE ones, but the *source* is Yahoo via
yfinance, and the difference is the whole reason `Quote` carries `as_of` and a
provenance label: Finnie is fit for education and unfit for trading.

The division of labour
----------------------
`data/market.py` decides *what the number is* and how trustworthy it is. This
agent decides *what to say about it*. Nothing here retries, caches or falls back:
that is the service's job, and duplicating it would mean two places to fix when a
degradation rule changes.

Three design decisions worth defending
--------------------------------------
1. **Symbol extraction is deterministic, not an LLM call.** Sending every market
   question to `gpt-4o-mini` first to pull out tickers would cost a round trip and
   a few paise per turn to answer a question a regex and a lexicon answer exactly.
   It is also *testable*: `extract_symbols` is a pure function with a parametrised
   table, so "bank nifty resolves to ^NSEBANK" is a unit test rather than a hope
   about model behaviour. The trade-off is recall on symbols outside the lexicon —
   `RELIANCE` in caps always works, an obscure small cap in lower case may not.

2. **Every number the narration uses is precomputed.** The model receives
   "+1.35%" and "30d: up +7.14%", never a list of closes to do arithmetic on.
   Language models are unreliable calculators and this is a finance product; the
   percentages come from tested properties on `Quote` and `Trend`.

3. **Provenance is appended by code, not requested in the prompt.** The freshness
   label is concatenated after the model returns, so a stale price cannot be
   presented as live even if the model ignores its instructions (FR-033). The
   label is *also* put in the prompt, so the narration itself does not describe a
   three-day-old close as "today's move".
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base import BaseAgent
from core.logging_setup import get_logger
from data.market import MarketDataService, OutOfScopeError, Quote, Trend
from workflow.state import AgentState

logger = get_logger(__name__)

MAX_SYMBOLS = 3

NO_SYMBOL_REPLY = (
    "I can look up prices for NSE and BSE listed companies and for the Indian "
    "indices — NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT, NIFTY MIDCAP 50 and "
    "NIFTY NEXT 50. Which one would you like? You can give me a name (Reliance, "
    "TCS) or a ticker (RELIANCE.NS, ^NSEI)."
)

# Spoken forms of the Indian indices. Longest first, so "bank nifty" is not
# consumed by the "nifty" entry.
INDEX_ALIASES: tuple[tuple[str, str], ...] = (
    ("bank nifty", "^NSEBANK"),
    ("nifty bank", "^NSEBANK"),
    ("nifty midcap 50", "^NSEMDCP50"),
    ("midcap 50", "^NSEMDCP50"),
    ("nifty next 50", "^CRSLDX"),
    ("next 50", "^CRSLDX"),
    ("nifty it", "^CNXIT"),
    ("nifty 50", "^NSEI"),
    ("nifty50", "^NSEI"),
    ("sensex", "^BSESN"),
    ("bse sensex", "^BSESN"),
    ("india vix", "^INDIAVIX"),
    ("nifty", "^NSEI"),
)

# Lower-case company names that should resolve without the user typing a ticker.
# Deliberately short: the NSE has ~2,000 listings and a full registry belongs in
# data, not in a source file. These are the names a beginner actually types.
NAME_LEXICON: dict[str, str] = {
    "reliance": "RELIANCE",
    "tcs": "TCS",
    "infosys": "INFY",
    "infy": "INFY",
    "hdfc bank": "HDFCBANK",
    "hdfcbank": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "icicibank": "ICICIBANK",
    "sbi": "SBIN",
    "state bank": "SBIN",
    "itc": "ITC",
    "wipro": "WIPRO",
    "airtel": "BHARTIARTL",
    "bharti airtel": "BHARTIARTL",
    "tata motors": "TMCV",
    "tata steel": "TATASTEEL",
    "maruti": "MARUTI",
    "asian paints": "ASIANPAINT",
    "larsen": "LT",
    "hindustan unilever": "HINDUNILVR",
    "axis bank": "AXISBANK",
    "kotak": "KOTAKBANK",
    "bajaj finance": "BAJFINANCE",
    "bajaj auto": "BAJAJ-AUTO",
    "bajajauto": "BAJAJ-AUTO",
    "adani": "ADANIENT",
    "zomato": "ZOMATO",
    "paytm": "PAYTM",
    # Jio Financial Services (JIOFIN.NS) — demerged from Reliance, listed Aug 2023.
    # Jio the telecom arm is not separately listed; JIOFIN is the only listed Jio entity.
    "jio financial services": "JIOFIN",
    "jio financial": "JIOFIN",
    "jio": "JIOFIN",
}

# Upper-case words that are finance vocabulary, not tickers. Without this list
# "What is the LTCG on ITC?" asks the market feed for a quote on LTCG.
NOT_TICKERS = frozenset(
    {
        "A", "I", "AN", "AM", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS",
        "IT", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
        "AI", "AMC", "AMFI", "API", "ATM", "BSE", "CAGR", "CIBIL", "DICGC", "ELSS",
        "EMI", "EPF", "ETF", "FAQ", "FD", "FY", "GST", "HRA", "IPO", "IRR", "KYC",
        "LTCG", "NAV", "NFO", "NPS", "NRI", "NSE", "OK", "PE", "PPF", "RBI", "ROI",
        "SEBI", "SIP", "STCG", "TDS", "UPI", "USA", "USD", "VPF", "XIRR", "INR",
        "UK", "EU", "WHO", "WHY", "HOW",
        # JIO as all-caps is blocked here so the lexicon pass resolves it to JIOFIN
        # instead of sending yfinance after the non-existent JIO.NS listing.
        "JIO",
    }
)

# A ticker-shaped token: 2–12 upper-case letters/digits, optional exchange suffix.
# The first alternative captures ^-prefixed index tickers (^NSEI, ^NSEMDCP50, ^CRSLDX…)
# that _TICKER_RE would otherwise strip the ^ from at a \b boundary.
_TICKER_RE = re.compile(r"(\^[A-Z][A-Z0-9]{1,11}|\b[A-Z][A-Z0-9&]{1,11}(?:-[A-Z0-9]{1,6})?(?:\.(?:NS|BO))?\b)")

MARKET_SYSTEM_PROMPT = """You are Finnie's market analyst, explaining Indian \
market data to a beginner.

You will be given quotes and trend summaries that have ALREADY been computed. Use \
those numbers exactly as given.

Rules:
1. Interpret, do not predict. Explain what a move does and does not tell the \
reader. Never say where a price is heading, and never forecast.
2. Do not recommend. No buying, selling, holding or timing. You are giving \
education, not advice.
3. Never invent a number. Every figure in your answer must appear in the data \
below. Do no arithmetic of your own.
4. If the data is marked STALE or SAMPLE DATA, say so plainly in your first \
sentence and do not describe it as today's movement.
5. Add one sentence of context a beginner would not know — that a single day's \
move is noise, that an index move reflects its heaviest constituents, that a \
percentage on a small base is not comparable to one on a large base.
6. Do NOT write a disclaimer or closing caveat. One is appended automatically.
7. Plain English, no jargon without a gloss. Four to six sentences, or a short \
bullet per company when several are compared.
8. If the user's question hints at a personal decision (mentions "should I", "my \
shares", "is it a good time", "worth buying/selling"), after explaining the data \
ask one clarifying question to understand their actual need. Examples: "Are you \
trying to understand this move in the context of a holding you already have, or \
are you considering whether to start a position?" or "What specifically about \
the trend is useful for you — the direction, the magnitude, or how it compares \
to the index?" One question only; do not ask if the question is purely factual.

FORMAT — apply to every answer:
- **Lead with the price and day's change in bold** on the very first line \
(e.g. "**TCS — ₹3,420 | +1.2% today**"). Skip this only when no price was found.
- When comparing two or more symbols, use a Markdown table: one row per symbol, \
columns for price, day change, 30d trend, 90d trend.
- Bullet points for the interpretation — one bullet per insight, not a paragraph.
- **Bold** every figure the user will act on: price, change %, trend direction.
- 4–6 sentences of narration max (or the equivalent in bullets). Be concise.
- No filler openers or closing summaries. Lead with the data, end with the insight.

Data:
{data}"""

MARKET_USER_TEMPLATE = "{question}"


class MarketAnalysisAgent(BaseAgent):
    """Quotes Indian equities and indices, and explains what the numbers mean."""

    name = "market_analysis"
    description = (
        "Looks up prices (via yfinance, delayed), daily percentage change and "
        "30/90-day trends for "
        "NSE and BSE listed companies and for the Indian indices (NIFTY 50, SENSEX, "
        "BANK NIFTY, NIFTY IT, NIFTY MIDCAP 50, NIFTY NEXT 50), then explains "
        "what the movement means. Use this whenever a "
        "specific company or index is named and the user wants its price, "
        "performance or recent direction. Do NOT use it for a user's own holdings "
        "(that is portfolio analysis) or for how an instrument works in general "
        "(that is finance Q&A)."
    )

    #: Trend windows requested per symbol. FR-011 specifies 30 and 90 days.
    windows: ClassVar[tuple[int, ...]] = (30, 90)

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        service: Any | None = None,
    ) -> None:
        super().__init__(llm=llm)
        self._service = service

    @property
    def service(self) -> Any:
        """Built on first use: constructing the agent must not read config or net."""
        if self._service is None:
            self._service = MarketDataService()
        return self._service

    # ── the work ──────────────────────────────────────────────────────────────

    def handle(self, state: AgentState) -> dict[str, Any]:
        question = self._latest_question(state)
        symbols = self.extract_symbols(question)

        if not symbols:
            # Nothing to look up. Asking which ticker costs nothing; guessing one
            # would produce a confident answer about a company nobody asked about.
            logger.info("No symbol found in %r; asking for one", question[:60])
            return {"messages": [AIMessage(content=NO_SYMBOL_REPLY)], "market_data": {}}

        quotes: dict[str, tuple[Quote, dict[int, Trend]]] = {}
        rejected: list[str] = []
        for raw in symbols:
            try:
                quote = self.service.get_quote(raw)
            except OutOfScopeError as exc:
                # Not a failure — the feeds answered, and the answer is "no such
                # Indian listing". One foreign ticker in a comparison must not
                # discard the Indian one beside it.
                logger.info("Symbol %s rejected as out of scope: %s", raw, exc)
                rejected.append(raw)
                continue
            quotes[quote.symbol] = (quote, self.service.get_trends(raw, self.windows))

        if not quotes:
            return {
                "messages": [AIMessage(content=self._out_of_scope_reply(rejected))],
                "market_data": {},
            }

        market_data = {sym: self._payload(q, tr) for sym, (q, tr) in quotes.items()}

        messages = [
            SystemMessage(content=MARKET_SYSTEM_PROMPT.format(data=self._for_prompt(quotes))),
            HumanMessage(content=MARKET_USER_TEMPLATE.format(question=question)),
        ]
        body = str(self.llm.invoke(messages).content).rstrip()

        if rejected:
            body += f"\n\n{self._out_of_scope_reply(rejected)}"
        # Provenance is appended here rather than trusted to the model (FR-033).
        body += "\n\n" + " · ".join(
            f"{sym} — {q.freshness_label()}" for sym, (q, _) in quotes.items()
        )
        body += (
            "\n\n---\n💡 **For a full deep dive** — price chart, 30/90-day trends, "
            "volume, and stock-specific analysis — head to the **Market tab**."
        )

        return {"messages": [AIMessage(content=body)], "market_data": market_data}

    def trace_detail(self, update: dict[str, Any]) -> str:
        data = update.get("market_data") or {}
        if not data:
            return "no symbol identified in the question"
        return "; ".join(
            f"{sym} {d['price']:,.2f} ({d['change_pct']:+.2f}%) [{d['source']}]"
            + (f" {len(d['trends'])} trend windows" if d["trends"] else " no history")
            for sym, d in data.items()
        )

    # ── symbol extraction ─────────────────────────────────────────────────────

    @staticmethod
    def extract_symbols(question: str) -> list[str]:
        """Pull up to MAX_SYMBOLS tickers out of a question, in order of appearance.

        Three passes, each claiming the text it matches so a later pass cannot
        match it again: indices by spoken alias, explicit upper-case tickers, then
        company names in lower case. Claiming spans is what keeps "HDFCBANK.NS"
        from also matching the lexicon entry "hdfcbank" and yielding the symbol
        twice.
        """
        text = question or ""
        lowered = text.lower()
        claimed: list[tuple[int, int]] = []
        found: list[tuple[int, str]] = []

        def free(start: int, end: int) -> bool:
            return not any(s < end and start < e for s, e in claimed)

        def claim(start: int, end: int, symbol: str) -> None:
            claimed.append((start, end))
            found.append((start, symbol))

        for alias, symbol in INDEX_ALIASES:
            for match in re.finditer(rf"\b{re.escape(alias)}\b", lowered):
                if free(*match.span()):
                    claim(match.start(), match.end(), symbol)

        for match in _TICKER_RE.finditer(text):
            token = match.group(1)
            if token in NOT_TICKERS or not free(*match.span()):
                continue
            # A bare capitalised word ("How", "Compare") is not a ticker; a ticker
            # is written in full caps or carries an exchange suffix.
            if token.upper() != token:
                continue
            claim(match.start(), match.end(), token)

        for name, symbol in sorted(NAME_LEXICON.items(), key=lambda kv: -len(kv[0])):
            for match in re.finditer(rf"\b{re.escape(name)}\b", lowered):
                if free(*match.span()):
                    claim(match.start(), match.end(), symbol)

        ordered: list[str] = []
        for _, symbol in sorted(found):
            if symbol not in ordered:
                ordered.append(symbol)
        # Capped: each symbol costs a quote call, a history call and prompt tokens.
        return ordered[:MAX_SYMBOLS]

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _payload(quote: Quote, trends: dict[int, Trend]) -> dict[str, Any]:
        """Flatten a quote and its trends into the shape state and the UI consume.

        Plain JSON-able types, not the dataclasses: `market_data` is state, and
        state should survive serialisation for checkpointing and for the trace
        viewer without needing Finnie's classes to unpickle it.
        """
        return {
            "symbol": quote.symbol,
            "name": quote.name,
            "price": quote.price,
            "previous_close": quote.previous_close,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "currency": quote.currency,
            "as_of": quote.as_of,
            "source": quote.source,
            "is_degraded": quote.is_degraded,
            "freshness": quote.freshness_label(),
            "trends": {
                f"{days}d": {
                    "days": days,
                    "direction": t.direction,
                    "change_pct": t.change_pct,
                    "start_price": t.start_price,
                    "end_price": t.end_price,
                    "high": t.high,
                    "low": t.low,
                    "closes": list(t.closes),
                }
                for days, t in sorted(trends.items())
            },
        }

    @staticmethod
    def _for_prompt(quotes: dict[str, tuple[Quote, dict[int, Trend]]]) -> str:
        """The data block the model sees. Numbers finished, provenance included."""
        lines = []
        for symbol, (quote, trends) in quotes.items():
            lines.append(
                f"{symbol} ({quote.name or symbol}): {quote.currency} {quote.price:,.2f}, "
                f"change {quote.change:+,.2f} ({quote.change_pct:+.2f}%) vs previous close "
                f"{quote.previous_close:,.2f} | freshness: {quote.freshness_label()}"
            )
            if trends:
                lines.extend(f"    {t.summary()}" for _, t in sorted(trends.items()))
            else:
                lines.append("    no price history available for trend windows")
        return "\n".join(lines)

    @staticmethod
    def _out_of_scope_reply(rejected: list[str]) -> str:
        names = ", ".join(rejected)
        plural = "those symbols" if len(rejected) > 1 else "that symbol"
        return (
            f"I could not find {names} on an Indian exchange, so I have no price for "
            f"{plural}. Finnie covers NSE and BSE equities and the Indian indices "
            "(NIFTY 50, SENSEX, BANK NIFTY) only — not US or other foreign listings."
        )
