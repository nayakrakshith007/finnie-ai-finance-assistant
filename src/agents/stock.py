"""Stock Deep-Dive Agent — comprehensive single-stock analysis (PRD FR-035).

What it does
------------
Six-section deep dive on one NSE/BSE-listed stock, all sourced from yfinance:

1. Fundamental  — valuation ratios, revenue/margin, 52-wk range (ticker.info)
2. Technical    — MA20/50/200, RSI-14, trend context (ticker.history 1y)
3. Sectoral     — sector, industry, sector position vs peers
4. Future Outlook — analyst target prices, recommendation consensus (ticker.info)
5. Sentiment    — recent headlines summary (ticker.news → news agent logic)
6. Verdict      — synthesis framed as "what the data shows", never buy/sell

Design decisions
----------------
All arithmetic is done here in Python. The model receives finished labels —
"above MA200: bullish", "RSI 72: overbought territory" — not raw numbers to
interpret. This is the same discipline as the market agent: a language model
is not a reliable calculator, and finance figures need tested computation.

The compliance node appends the disclaimer automatically; this agent MUST NOT
write one. The verdict section is framed educationally ("the data suggests…")
to stay on the right side of the advice boundary.
"""

from __future__ import annotations

import math
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base import BaseAgent
from agents.market import MarketAnalysisAgent
from core.logging_setup import get_logger
from data.market import OutOfScopeError, normalise_symbol
from workflow.state import AgentState

logger = get_logger(__name__)

NO_SYMBOL_REPLY = (
    "Which stock would you like a deep-dive on? Give me a name (Reliance, TCS) "
    "or an NSE ticker (RELIANCE, HDFCBANK) and I will run a full fundamental, "
    "technical and sectoral analysis."
)

OUT_OF_SCOPE_TEMPLATE = (
    "I could not find **{symbol}** on an Indian exchange. "
    "Finnie covers NSE and BSE equities only — not US or other foreign listings. "
    "Try the NSE ticker without the exchange suffix (e.g. RELIANCE, not RELIANCE.NS)."
)

STOCK_SYSTEM_PROMPT = """You are Finnie's equity research analyst, delivering a \
comprehensive single-stock deep dive to a beginner investor.

All numbers below have already been computed. Use them exactly as given — do \
no arithmetic of your own and do not invent any figure that does not appear in \
the data block.

**Rules:**
1. Never predict a price or guarantee a return.
2. Never recommend buying, selling, or holding the stock.
3. Do NOT write a disclaimer — one is appended automatically.
4. The Verdict section must say "what the data shows", not what the investor \
should do. Use phrases like "the fundamentals indicate…", "the technical \
picture suggests…", "the consensus among analysts is…".
5. If any section's data is marked UNAVAILABLE, say so in one line and skip \
that section's details.
6. Bold every key number the reader will act on: ratios, prices, percentages.

**Output structure — use these exact `###` headers, in this order:**

### Fundamental Analysis
- Valuation: P/E, P/B, EV/EBITDA
- Profitability: ROE, profit margin, revenue growth
- Balance sheet highlights: debt/equity, cash position
- 52-week range and where the current price sits

### Technical Analysis
- Moving averages: MA20, MA50, MA200 and what they signal
- RSI reading and what the zone means (oversold <30, neutral 30–70, overbought >70)
- Trend summary: direction, momentum, support/resistance context

### Sectoral Analysis
- Sector and industry classification
- Sector tailwinds / headwinds at the time of the data
- How this stock's P/E compares to its sector median (if available)

### Future Outlook
- Analyst consensus recommendation (Strong Buy → Strong Sell scale)
- 12-month target price range (low / median / high)
- Upside / downside implied by the median target vs current price

### Sentiment
- Dominant theme from recent headlines (1–2 sentences)
- Any specific catalysts or risk events mentioned in the news

### Verdict
- Bullish signals from the data (list as bullets)
- Bearish signals from the data (list as bullets)
- Summary: what the overall data picture shows in 2–3 sentences
  (frame as observation, NOT as a recommendation)

Stock data:
{data}"""

STOCK_USER_TEMPLATE = "{question}"


class StockDeepDiveAgent(BaseAgent):
    """Runs a 6-section deep analysis on a single NSE/BSE-listed stock."""

    name = "stock_deep_dive"
    description = (
        "Runs a comprehensive single-stock deep dive covering fundamental "
        "analysis (P/E, margins, revenue), technical analysis (moving averages, "
        "RSI, trend), sectoral positioning, analyst outlook, news sentiment, and "
        "a data-driven verdict. Use this when the user asks for a detailed analysis "
        "of ONE specific stock — 'analyse TCS', 'deep dive on Reliance', 'is HDFC "
        "Bank fundamentally strong?', 'what does the technicals say about Infosys'. "
        "Do NOT use it for quick price checks (market analysis) or for how "
        "instruments work in general (finance Q&A)."
    )

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        super().__init__(llm=llm)

    # ── the work ──────────────────────────────────────────────────────────────

    def handle(self, state: AgentState) -> dict[str, Any]:
        question = self._latest_question(state)
        symbols = MarketAnalysisAgent.extract_symbols(question)

        if not symbols:
            return {"messages": [AIMessage(content=NO_SYMBOL_REPLY)]}

        # Use only the first symbol — this is a single-stock deep dive.
        raw = symbols[0]
        try:
            ticker_sym = normalise_symbol(raw)
        except OutOfScopeError:
            return {
                "messages": [AIMessage(content=OUT_OF_SCOPE_TEMPLATE.format(symbol=raw))]
            }

        data = self._fetch_all(ticker_sym)
        if data.get("error"):
            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"I was unable to fetch data for **{raw}** right now. "
                            "The yfinance feed may be temporarily unavailable. "
                            "Try again shortly, or use the Market tab for a quick price check."
                        )
                    )
                ]
            }

        prompt_data = self._for_prompt(data)
        messages = [
            SystemMessage(content=STOCK_SYSTEM_PROMPT.format(data=prompt_data)),
            HumanMessage(content=STOCK_USER_TEMPLATE.format(question=question)),
        ]
        body = str(self.llm.invoke(messages).content).rstrip()
        # Append provenance — same discipline as the market agent (FR-033).
        body += f"\n\n_Data sourced from yfinance (Yahoo Finance), ~15-min delayed. As of {data.get('as_of', 'unknown')}._"

        return {"messages": [AIMessage(content=body)], "stock_data": data}

    def trace_detail(self, update: dict[str, Any]) -> str:
        d = update.get("stock_data") or {}
        if not d:
            return "no symbol found or fetch failed"
        return (
            f"{d.get('symbol', '?')} — P/E {d.get('pe_ratio', 'n/a')}, "
            f"RSI {d.get('rsi', 'n/a')}, "
            f"analyst: {d.get('recommendation', 'n/a')}"
        )

    # ── data fetching ─────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_all(ticker_sym: str) -> dict[str, Any]:
        """Gather all 5 data dimensions from yfinance. Returns {} on hard failure."""
        import yfinance as yf

        try:
            t = yf.Ticker(ticker_sym)
            info = t.info or {}
            hist = t.history(period="1y")
            news = []
            try:
                raw_news = t.news or []
                for item in raw_news[:5]:
                    # Handle both yfinance payload shapes (pre/post 0.2.50)
                    if isinstance(item, dict) and "content" in item:
                        content = item["content"]
                        title = content.get("title", "")
                        url = (content.get("canonicalUrl") or {}).get("url", "")
                    else:
                        title = item.get("title", "")
                        url = item.get("link", "")
                    if title:
                        news.append({"title": title, "url": url})
            except Exception:
                pass

            # ── Fundamentals ──────────────────────────────────────────────────
            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
            week52_high = info.get("fiftyTwoWeekHigh") or 0.0
            week52_low = info.get("fiftyTwoWeekLow") or 0.0
            pct_from_52w_high = (
                round((price - week52_high) / week52_high * 100, 2)
                if week52_high else None
            )
            pct_from_52w_low = (
                round((price - week52_low) / week52_low * 100, 2)
                if week52_low else None
            )

            # ── Technicals ────────────────────────────────────────────────────
            ma20 = ma50 = ma200 = rsi = None
            trend_label = "UNAVAILABLE"
            if not hist.empty and "Close" in hist.columns:
                closes = hist["Close"]
                n = len(closes)
                if n >= 20:
                    ma20 = round(float(closes.iloc[-20:].mean()), 2)
                if n >= 50:
                    ma50 = round(float(closes.iloc[-50:].mean()), 2)
                if n >= 200:
                    ma200 = round(float(closes.iloc[-200:].mean()), 2)

                rsi = StockDeepDiveAgent._compute_rsi(closes.tolist())

                # Simple trend: price vs MA200 (or MA50 if no MA200)
                ref_ma = ma200 or ma50 or ma20
                if ref_ma:
                    if price > ref_ma * 1.05:
                        trend_label = "Above key moving average — broadly bullish"
                    elif price < ref_ma * 0.95:
                        trend_label = "Below key moving average — broadly bearish"
                    else:
                        trend_label = "Near key moving average — neutral / transitional"

            # ── Analyst / outlook ─────────────────────────────────────────────
            rec = info.get("recommendationKey", "").replace("_", " ").title() or "UNAVAILABLE"
            target_mean = info.get("targetMeanPrice")
            target_low = info.get("targetLowPrice")
            target_high = info.get("targetHighPrice")
            upside = None
            if target_mean and price:
                upside = round((target_mean - price) / price * 100, 1)

            return {
                "symbol": ticker_sym,
                "name": info.get("longName") or info.get("shortName") or ticker_sym,
                "as_of": str(hist.index[-1].date()) if not hist.empty else "unknown",
                "price": price,
                "currency": info.get("currency", "INR"),
                # Fundamentals
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "roe": info.get("returnOnEquity"),
                "profit_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "debt_to_equity": info.get("debtToEquity"),
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),
                "market_cap": info.get("marketCap"),
                "week52_high": week52_high,
                "week52_low": week52_low,
                "pct_from_52w_high": pct_from_52w_high,
                "pct_from_52w_low": pct_from_52w_low,
                # Technicals
                "ma20": ma20,
                "ma50": ma50,
                "ma200": ma200,
                "rsi": rsi,
                "trend_label": trend_label,
                # Sector
                "sector": info.get("sector") or "UNAVAILABLE",
                "industry": info.get("industry") or "UNAVAILABLE",
                "sector_pe": None,  # yfinance doesn't provide sector median PE
                # Outlook
                "recommendation": rec,
                "target_low": target_low,
                "target_mean": target_mean,
                "target_high": target_high,
                "upside_pct": upside,
                "num_analysts": info.get("numberOfAnalystOpinions"),
                # Sentiment
                "news_headlines": news,
            }
        except Exception as exc:
            logger.warning("StockDeepDive fetch failed for %s: %s", ticker_sym, exc)
            return {"error": str(exc)}

    @staticmethod
    def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
        """Wilder RSI-14 from a list of closing prices."""
        if len(closes) < period + 1:
            return None
        deltas = [closes[i + 1] - closes[i] for i in range(len(closes) - 1)]
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - 100 / (1 + rs), 1)

    @staticmethod
    def _for_prompt(d: dict[str, Any]) -> str:
        """Flatten the fetched data into labelled text the model can narrate."""

        def fmt_pct(v: float | None) -> str:
            return f"{v * 100:.1f}%" if v is not None else "UNAVAILABLE"

        def fmt_cr(v: float | None) -> str:
            if v is None:
                return "UNAVAILABLE"
            cr = v / 1e7
            if cr >= 100:
                return f"₹{cr / 100:.2f} lakh crore"
            return f"₹{cr:.2f} crore"

        def fmt_num(v: float | None, decimals: int = 2) -> str:
            return f"{v:.{decimals}f}" if v is not None else "UNAVAILABLE"

        lines = [
            f"Company: {d['name']} ({d['symbol']})",
            f"Current price: {d['currency']} {d['price']:,.2f}",
            f"As of: {d.get('as_of', 'unknown')}",
            "",
            "=== FUNDAMENTALS ===",
            f"Market cap: {fmt_cr(d.get('market_cap'))}",
            f"Trailing P/E: {fmt_num(d.get('pe_ratio'))}",
            f"Forward P/E: {fmt_num(d.get('forward_pe'))}",
            f"Price/Book: {fmt_num(d.get('pb_ratio'))}",
            f"EV/EBITDA: {fmt_num(d.get('ev_ebitda'))}",
            f"ROE: {fmt_pct(d.get('roe'))}",
            f"Profit margin: {fmt_pct(d.get('profit_margin'))}",
            f"Revenue growth (YoY): {fmt_pct(d.get('revenue_growth'))}",
            f"Debt/Equity: {fmt_num(d.get('debt_to_equity'))}",
            f"52-week high: {d['currency']} {d.get('week52_high', 0):,.2f} "
            f"(current is {fmt_num(d.get('pct_from_52w_high'))}% from high)",
            f"52-week low:  {d['currency']} {d.get('week52_low', 0):,.2f} "
            f"(current is +{fmt_num(d.get('pct_from_52w_low'))}% above low)",
            "",
            "=== TECHNICALS ===",
            f"MA20:  {fmt_num(d.get('ma20'))} "
            f"({'price above' if d.get('price', 0) > (d.get('ma20') or 0) else 'price below'} MA20)",
            f"MA50:  {fmt_num(d.get('ma50'))} "
            f"({'price above' if d.get('price', 0) > (d.get('ma50') or 0) else 'price below'} MA50)",
            f"MA200: {fmt_num(d.get('ma200'))} "
            f"({'price above' if d.get('price', 0) > (d.get('ma200') or 0) else 'price below'} MA200)",
            f"RSI-14: {fmt_num(d.get('rsi'), 1)} "
            + (
                "(oversold — below 30)" if (d.get("rsi") or 50) < 30
                else "(overbought — above 70)" if (d.get("rsi") or 50) > 70
                else "(neutral range 30–70)"
            ),
            f"Trend context: {d.get('trend_label', 'UNAVAILABLE')}",
            "",
            "=== SECTORAL ===",
            f"Sector: {d.get('sector', 'UNAVAILABLE')}",
            f"Industry: {d.get('industry', 'UNAVAILABLE')}",
            "Sector median P/E: UNAVAILABLE (yfinance does not provide this)",
            "",
            "=== ANALYST OUTLOOK ===",
            f"Consensus recommendation: {d.get('recommendation', 'UNAVAILABLE')} "
            f"(based on {d.get('num_analysts', '?')} analysts)",
            f"12-month target — Low: {fmt_num(d.get('target_low'))} | "
            f"Median: {fmt_num(d.get('target_mean'))} | "
            f"High: {fmt_num(d.get('target_high'))}",
            f"Implied upside from median target: {fmt_num(d.get('upside_pct'), 1)}%",
            "",
            "=== SENTIMENT (recent headlines) ===",
        ]
        news = d.get("news_headlines") or []
        if news:
            for item in news:
                lines.append(f'- "{item["title"]}"')
        else:
            lines.append("No recent headlines available from yfinance.")

        return "\n".join(lines)
