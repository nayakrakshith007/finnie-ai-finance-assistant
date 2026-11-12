"""Market tab (PRD §6.5a, FR-011, FR-033).

Layout: a ticker selector, a metric row, the trend line full width, the freshness
caption, and the interpretation below.

The selector offers the two indices, the configured default tickers, and anything
in the user's portfolio — the last of those because the holding someone actually
owns is the price they actually want, and making them retype `RELIANCE.NS` to see
it would be the kind of friction nobody forgives.

Freshness is shown in three places on purpose: in the metric row's caption, on
the chart title, and in the agent's own narration (FR-033). A stale price that
looks live is the single worst thing this tab could do, and three cheap
reminders are better than one that a user might scroll past.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from core import deep_dive_cache, premarket_cache
from web_app import session
from web_app.charts import price_trend_line
from web_app.formatting import format_inr, format_signed_pct
from web_app.tabs.chat import render_trace

_PM_DISCLAIMER = (
    "⚠️ **Disclaimer:** This briefing is generated from yfinance data (~15-min delayed from "
    "Yahoo Finance). It is provided for **educational purposes only** and does **not** "
    "constitute financial advice, a recommendation to buy or sell, or a forecast of future "
    "performance. Past performance does not guarantee future results. Always consult a "
    "SEBI-registered investment adviser before making any investment decision."
)

WINDOW_LABELS = {"30 days": "30d", "90 days": "90d"}

# Common NSE stocks with their full company names.
# Ticker → company name. Covers Nifty 50 + popular midcaps an Indian investor
# would recognise. Indices are kept separately (they don't get deep dives).
NSE_COMPANY_NAMES: dict[str, str] = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank",
    "INFY.NS": "Infosys",
    "ICICIBANK.NS": "ICICI Bank",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "SBIN.NS": "State Bank of India",
    "BHARTIARTL.NS": "Bharti Airtel",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "LT.NS": "Larsen & Toubro",
    "AXISBANK.NS": "Axis Bank",
    "ASIANPAINT.NS": "Asian Paints",
    "BAJFINANCE.NS": "Bajaj Finance",
    "WIPRO.NS": "Wipro",
    "NESTLEIND.NS": "Nestle India",
    "MARUTI.NS": "Maruti Suzuki",
    "POWERGRID.NS": "Power Grid Corporation",
    "NTPC.NS": "NTPC",
    "ULTRACEMCO.NS": "UltraTech Cement",
    "SUNPHARMA.NS": "Sun Pharmaceutical",
    "TITAN.NS": "Titan Company",
    "TECHM.NS": "Tech Mahindra",
    "HCLTECH.NS": "HCL Technologies",
    "BAJAJFINSV.NS": "Bajaj Finserv",
    "ONGC.NS": "Oil & Natural Gas Corporation",
    "ADANIENT.NS": "Adani Enterprises",
    "ADANIPORTS.NS": "Adani Ports & SEZ",
    "JSWSTEEL.NS": "JSW Steel",
    "COALINDIA.NS": "Coal India",
    "TATASTEEL.NS": "Tata Steel",
    "GRASIM.NS": "Grasim Industries",
    "CIPLA.NS": "Cipla",
    "BPCL.NS": "Bharat Petroleum",
    "HEROMOTOCO.NS": "Hero MotoCorp",
    "DRREDDY.NS": "Dr Reddy's Laboratories",
    "DIVISLAB.NS": "Divi's Laboratories",
    "BRITANNIA.NS": "Britannia Industries",
    "EICHERMOT.NS": "Eicher Motors",
    "SHREECEM.NS": "Shree Cement",
    "INDUSINDBK.NS": "IndusInd Bank",
    "TATACONSUM.NS": "Tata Consumer Products",
    "APOLLOHOSP.NS": "Apollo Hospitals",
    "TMCV.NS": "Tata Motors",
    "BAJAJ-AUTO.NS": "Bajaj Auto",
    "HINDALCO.NS": "Hindalco Industries",
    "TATAPOWER.NS": "Tata Power",

    "M&M.NS": "Mahindra & Mahindra",
    "VEDL.NS": "Vedanta",
    "ITC.NS": "ITC",
    "HDFCLIFE.NS": "HDFC Life Insurance",
    "SBILIFE.NS": "SBI Life Insurance",
    "ICICIPRULI.NS": "ICICI Prudential Life",
    "PIDILITIND.NS": "Pidilite Industries",
    "BERGEPAINT.NS": "Berger Paints",
    "HAVELLS.NS": "Havells India",
    "PAGEIND.NS": "Page Industries",
    "MUTHOOTFIN.NS": "Muthoot Finance",
    "MOTHERSON.NS": "Samvardhana Motherson",
    "ZOMATO.NS": "Zomato",
    "NYKAA.NS": "FSN E-Commerce (Nykaa)",
    "PAYTM.NS": "One 97 Communications (Paytm)",
    "IRCTC.NS": "Indian Railway Catering",
    "DMART.NS": "Avenue Supermarts (D-Mart)",
    "ICICIGI.NS": "ICICI Lombard General Insurance",
    "GODREJCP.NS": "Godrej Consumer Products",
    "DABUR.NS": "Dabur India",
    "MARICO.NS": "Marico",
    "COLPAL.NS": "Colgate-Palmolive India",
    "UBL.NS": "United Breweries",
    "TRENT.NS": "Trent (Tata)",
    "JUBLFOOD.NS": "Jubilant FoodWorks",
    "PNB.NS": "Punjab National Bank",
    "CANBK.NS": "Canara Bank",
    "BANKBARODA.NS": "Bank of Baroda",
    "FEDERALBNK.NS": "Federal Bank",
    "IDFCFIRSTB.NS": "IDFC First Bank",
    "BANDHANBNK.NS": "Bandhan Bank",
    "RBLBANK.NS": "RBL Bank",
    "LICHSGFIN.NS": "LIC Housing Finance",
    "BAJAJHLDNG.NS": "Bajaj Holdings",
    "CHOLAFIN.NS": "Cholamandalam Financial Holdings",
    "SBICARD.NS": "SBI Cards and Payment Services",
    "RECLTD.NS": "REC Limited",
    "PFC.NS": "Power Finance Corporation",
    "IOC.NS": "Indian Oil Corporation",
    "HINDPETRO.NS": "Hindustan Petroleum",
    "GAIL.NS": "GAIL India",
    "SAIL.NS": "Steel Authority of India",
    "NMDC.NS": "NMDC",
    "PIIND.NS": "PI Industries",
    "ALKEM.NS": "Alkem Laboratories",
    "TORNTPHARM.NS": "Torrent Pharmaceuticals",
    "BIOCON.NS": "Biocon",
    "LUPIN.NS": "Lupin",
    "AUROPHARMA.NS": "Aurobindo Pharma",
    "LTIM.NS": "LTIMindtree",
    "MPHASIS.NS": "Mphasis",
    "PERSISTENT.NS": "Persistent Systems",
    "COFORGE.NS": "Coforge",
    "LTTS.NS": "L&T Technology Services",
    "KPITTECH.NS": "KPIT Technologies",
    "TATAELXSI.NS": "Tata Elxsi",
}

# Map "Company Name (TICKER)" → ticker for the selectbox
_DISPLAY_TO_TICKER: dict[str, str] = {
    f"{name} ({ticker.replace('.NS', '')})": ticker
    for ticker, name in NSE_COMPANY_NAMES.items()
}
_INDICES: list[str] = [
    "^NSEI (Nifty 50)",
    "^BSESN (Sensex)",
    "^NSEBANK (Bank Nifty)",
    "^NSEMDCP50 (Nifty Midcap 50)",
    "^CRSLDX (Nifty Next 50)",
]
_INDEX_TICKER: dict[str, str] = {
    "^NSEI (Nifty 50)": "^NSEI",
    "^BSESN (Sensex)": "^BSESN",
    "^NSEBANK (Bank Nifty)": "^NSEBANK",
    "^NSEMDCP50 (Nifty Midcap 50)": "^NSEMDCP50",
    "^CRSLDX (Nifty Next 50)": "^CRSLDX",
}


def _symbol_options() -> list[str]:
    """Indices, the configured defaults, and the user's own holdings."""
    try:
        from core.config import load_config

        cfg = load_config()
        options = [*cfg.market.default_indices, *cfg.market.default_tickers]
    except Exception:  # noqa: BLE001 - a config problem must not empty the selector
        options = ["^NSEI", "^BSESN", "RELIANCE.NS", "TCS.NS"]

    from portfolio.holdings import MARKET_TRADED_CLASSES

    for row in session.holdings():
        symbol = str(row.get("symbol") or "").upper()
        tradeable = row.get("asset_class", "stock") in MARKET_TRADED_CLASSES
        if symbol and tradeable and symbol not in options:
            options.append(symbol)
    return options


def _build_search_options() -> list[str]:
    """Full list of display strings for the search selectbox.

    Indices first, then portfolio holdings (by their display form), then the
    full NSE stock list sorted alphabetically.
    """
    # Indices always at the top
    options: list[str] = list(_INDICES)

    # Portfolio holdings come next so the user can find their own stocks first
    from portfolio.holdings import MARKET_TRADED_CLASSES

    for row in session.holdings():
        raw = str(row.get("symbol") or "").upper()
        tradeable = row.get("asset_class", "stock") in MARKET_TRADED_CLASSES
        if not tradeable:
            continue
        # Prefer the full company name if we have it
        display = f"{NSE_COMPANY_NAMES.get(raw, raw.replace('.NS', ''))} ({raw.replace('.NS', '')})"
        if display not in options:
            options.append(display)

    # Then the full NSE list (already sorted by company name via dict ordering)
    for display in sorted(_DISPLAY_TO_TICKER):
        if display not in options:
            options.append(display)

    return options


def _resolve_ticker(display: str) -> str:
    """Turn a display string back into a bare ticker."""
    if display in _INDEX_TICKER:
        return _INDEX_TICKER[display]
    if display in _DISPLAY_TO_TICKER:
        return _DISPLAY_TO_TICKER[display]
    # Fallback: treat the display string itself as a ticker
    return display.upper()


def _quote_for(symbol: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """The quote this tab asked for, matched loosely on the suffix.

    The agent normalises `TCS` to `TCS.NS`, so the key in state may not be the
    string the selector held.
    """
    for key, value in data.items():
        if key in ("news", "news_query") or not isinstance(value, dict):
            continue
        if key == symbol or key.split(".")[0] == symbol.split(".")[0]:
            return value
    return None


def _stock_deep_dive_section(symbol: str) -> None:
    """Deep dive panel for a stock, with 3-tier cache (session → file → LLM)."""
    st.divider()
    st.markdown(f"#### 🔬 Stock Deep Dive — {symbol}")

    dd_key = f"dd_result_{symbol}"

    # Layer 1: session state
    result = st.session_state.get(dd_key)

    # Layer 2: file cache (15-min TTL)
    if result is None:
        result = deep_dive_cache.get(symbol)
        if result is not None:
            st.session_state[dd_key] = result
            ttl = deep_dive_cache.ttl_remaining(symbol)
            st.caption(f"⚡ Loaded from cache · refreshes in {ttl // 60}m {ttl % 60}s")

    # Layer 3: live LLM fetch
    if result is None:
        with st.spinner(f"Fetching fundamentals, technicals and analyst data for {symbol}…"):
            result = session.run_turn(
                f"Give me a full deep dive analysis on {symbol}",
                record_in_chat=False,
            )
            if result and result.get("answer"):
                deep_dive_cache.set(symbol, result)
                st.session_state[dd_key] = result
            else:
                stale = deep_dive_cache.get_stale(symbol)
                if stale:
                    result, age_minutes = stale
                    st.session_state[dd_key] = result
                    st.warning(
                        f"⚠️ **Yahoo Finance is currently unavailable.** "
                        f"Showing cached data from **{age_minutes} minute{'s' if age_minutes != 1 else ''} ago**. "
                        "Numbers may be outdated — refresh once the feed recovers."
                    )
                else:
                    st.session_state[dd_key] = result

    result = result or {}
    if result.get("answer"):
        st.markdown(result["answer"])
        render_trace(result.get("trace") or [])
    else:
        st.warning(
            f"Could not fetch deep-dive data for **{symbol}**. "
            "Make sure the ticker is listed on Yahoo Finance (e.g. RELIANCE, TCS, HDFCBANK)."
        )


# ── Pre-market data helpers ────────────────────────────────────────────────────

def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 2:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_g / avg_l), 2)


def _calc_pivots(h: float, l: float, c: float) -> dict[str, float]:
    p = (h + l + c) / 3
    return {
        "pivot": round(p, 2),
        "r1": round(2 * p - l, 2),
        "r2": round(p + (h - l), 2),
        "s1": round(2 * p - h, 2),
        "s2": round(p - (h - l), 2),
    }


def _fetch_one(ticker: str, period: str = "1y") -> dict | None:
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty or len(hist) < 3:
            return None
        closes = hist["Close"].tolist()
        last = closes[-1]
        prev = closes[-2]
        change = last - prev
        change_pct = change / prev * 100 if prev else 0.0
        prev_h = float(hist["High"].iloc[-2])
        prev_l = float(hist["Low"].iloc[-2])
        return {
            "last": last,
            "prev": prev,
            "open": float(hist["Open"].iloc[-1]),
            "high": float(hist["High"].iloc[-1]),
            "low": float(hist["Low"].iloc[-1]),
            "change": change,
            "change_pct": change_pct,
            "week52_high": float(hist["High"].max()),
            "week52_low": float(hist["Low"].min()),
            "ma20":  float(hist["Close"].tail(20).mean())  if len(closes) >= 20  else None,
            "ma200": float(hist["Close"].tail(200).mean()) if len(closes) >= 200 else None,
            "rsi": _calc_rsi(closes),
            "prev_open":  float(hist["Open"].iloc[-2]),
            "prev_high":  prev_h,
            "prev_low":   prev_l,
            "prev_close": prev,
            "pivots": _calc_pivots(prev_h, prev_l, prev),
        }
    except Exception:  # noqa: BLE001
        return None


def _fetch_premarket_data() -> dict:
    """Fetch all 8-section data for the pre-market briefing."""
    import yfinance as yf
    from datetime import datetime, timedelta, timezone

    _IST = timezone(timedelta(hours=5, minutes=30))

    india_tickers = {
        "^NSEI":     "Nifty 50",
        "^BSESN":    "Sensex",
        "^NSEBANK":  "Bank Nifty",
        "^CNXIT":    "Nifty IT",
        "^NSEMDCP50":"Nifty Midcap 50",
        "^CRSLDX":   "Nifty Next 50",
    }
    us_tickers = {
        "^GSPC": "S&P 500",
        "^DJI":  "Dow Jones",
        "^IXIC": "Nasdaq",
    }
    commodity_tickers = {
        "USDINR=X": "USD/INR",
        "BZ=F":     "Brent Crude ($/bbl)",
        "GC=F":     "Gold (COMEX $/oz)",
        "SI=F":     "Silver (COMEX $/oz)",
    }

    india: dict = {}
    for t, name in india_tickers.items():
        d = _fetch_one(t)
        if d:
            d["name"] = name
        else:
            d = {"name": name, "error": "No data from yfinance"}
        india[t] = d

    vix = _fetch_one("^INDIAVIX", period="6mo")
    if vix:
        vix["name"] = "India VIX"

    us: dict = {}
    for t, name in us_tickers.items():
        d = _fetch_one(t)
        if d:
            d["name"] = name
        else:
            d = {"name": name, "error": "No data"}
        us[t] = d

    commodities: dict = {}
    for t, name in commodity_tickers.items():
        d = _fetch_one(t)
        if d:
            d["name"] = name
        else:
            d = {"name": name, "error": "No data"}
        commodities[t] = d

    # Use Google News RSS (stdlib only, no API key) — Yahoo news endpoint is
    # intermittently down and direct yf.Ticker.news raises when it is.
    from data.news import GoogleNewsFeed as _GNF
    news: list = []
    try:
        for h in _GNF().headlines("NIFTY NSE India stock market", limit=6):
            news.append({"title": h.title, "publisher": h.publisher, "link": h.url})
    except Exception:  # noqa: BLE001
        pass

    # Best-effort NSE India data for F&O and FII/DII sections.
    # Returns None on any network/parsing failure — renderers handle None gracefully.
    from core.nse_fetcher import fetch_fii_dii
    fii_dii = fetch_fii_dii()

    return {
        "fetched_at": datetime.now(_IST).strftime("%I:%M %p IST, %d %b %Y"),
        "india": india,
        "vix": vix,
        "us": us,
        "commodities": commodities,
        "news": news,
        "fii_dii": fii_dii,
    }


# ── Pre-market section renderers (one per expander) ───────────────────────────

def _pm_index_row(ticker: str, row: dict) -> None:
    """Render one index row: name, level, change, MA badges."""
    if "error" in row:
        st.caption(f"**{row['name']}** (`{ticker}`) — _{row['error']}_")
        return
    name = row["name"]
    last, chg, pct = row["last"], row["change"], row["change_pct"]
    arrow = "▲" if chg >= 0 else "▼"
    col = "green" if chg >= 0 else "red"
    ma20, ma200 = row.get("ma20"), row.get("ma200")
    ma_tags = []
    if ma20 is not None:
        ma_tags.append(("🟢" if last > ma20 else "🔴") + f" {'above' if last>ma20 else 'below'} MA20 ({ma20:,.0f})")
    if ma200 is not None:
        ma_tags.append(("🟢" if last > ma200 else "🔴") + f" {'above' if last>ma200 else 'below'} MA200 ({ma200:,.0f})")
    badges = "  ·  ".join(ma_tags)
    st.markdown(
        f"**{name}** &nbsp; :{col}[{arrow} **{last:,.2f}** &nbsp; ({chg:+,.2f} &nbsp; {pct:+.2f}%)]"
        + (f"  \n<sub>{badges}</sub>" if badges else ""),
        unsafe_allow_html=True,
    )


def _pm_section_opening(india: dict, vix: dict | None) -> None:
    with st.expander("① Opening Brief — Indian Indices & VIX", expanded=True):
        for ticker, row in india.items():
            _pm_index_row(ticker, row)
            st.divider()
        if vix and "error" not in vix:
            v = vix["last"]
            chg = vix["change"]
            pct = vix["change_pct"]
            arrow = "▲" if chg >= 0 else "▼"
            tone = "😰 Elevated fear" if v > 20 else ("😐 Some nervousness" if v > 15 else "😌 Low fear")
            col = "red" if chg >= 0 else "green"  # VIX up = bad, VIX down = good
            st.markdown(
                f"**India VIX** &nbsp; :{col}[{arrow} **{v:.2f}** &nbsp; ({chg:+.2f} &nbsp; {pct:+.2f}%)]  \n"
                f"<sub>{tone} · VIX < 15 = calm · 15–20 = cautious · > 20 = fear</sub>",
                unsafe_allow_html=True,
            )
        elif vix is None:
            st.caption("India VIX — No data from yfinance")


def _pm_section_global(us: dict, commodities: dict) -> None:
    with st.expander("② Global Markets — US Indices & Macro"):
        st.markdown("##### 🇺🇸 US Markets")
        for ticker, row in us.items():
            if "error" in row:
                st.caption(f"**{row['name']}** — _{row['error']}_")
                continue
            last, chg, pct = row["last"], row["change"], row["change_pct"]
            arrow, col = ("▲", "green") if chg >= 0 else ("▼", "red")
            w52h, w52l = row.get("week52_high"), row.get("week52_low")
            rng = f" · 52w: {w52l:,.0f}–{w52h:,.0f}" if w52h else ""
            st.markdown(
                f"**{row['name']}** &nbsp; :{col}[{arrow} {last:,.2f} ({chg:+,.2f} · {pct:+.2f}%)]"
                + (f"<sub>{rng}</sub>" if rng else ""),
                unsafe_allow_html=True,
            )
        st.divider()
        st.markdown("##### 💱 USD/INR & Crude")
        for ticker in ("USDINR=X", "BZ=F"):
            row = commodities.get(ticker, {})
            if "error" in row:
                st.caption(f"**{row.get('name', ticker)}** — _{row['error']}_")
                continue
            last, chg, pct = row["last"], row["change"], row["change_pct"]
            arrow, col = ("▲", "green") if chg >= 0 else ("▼", "red")
            # Invert colour semantics: strong USD = bad for India, cheap crude = good for India
            if ticker == "USDINR=X":
                col = "red" if chg >= 0 else "green"
            elif ticker == "BZ=F":
                col = "red" if chg >= 0 else "green"
            st.markdown(
                f"**{row['name']}** &nbsp; :{col}[{arrow} {last:,.2f} ({chg:+.2f} · {pct:+.2f}%)]",
                unsafe_allow_html=True,
            )
        st.caption("Note: US markets close ~1:30 AM IST; Asian and European data may lag.")


def _pm_section_india_levels(india: dict) -> None:
    nsei = india.get("^NSEI", {})
    with st.expander("③ India Levels — OHLC, RSI & Pivot Points"):
        if "error" in nsei:
            st.warning("Nifty 50 data unavailable.")
            return
        # Previous session OHLC
        st.markdown("##### Previous Session — Nifty 50")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Prev Open",  f"{nsei['prev_open']:,.2f}")
        c2.metric("Prev High",  f"{nsei['prev_high']:,.2f}")
        c3.metric("Prev Low",   f"{nsei['prev_low']:,.2f}")
        c4.metric("Prev Close", f"{nsei['prev_close']:,.2f}")

        st.divider()
        # RSI
        rsi = nsei.get("rsi")
        st.markdown("##### RSI-14 (Daily)")
        if rsi is not None:
            rsi_label = "🔴 Overbought" if rsi > 70 else ("🟢 Oversold" if rsi < 30 else "🟡 Neutral")
            st.markdown(f"**{rsi:.1f}** &nbsp; {rsi_label}  \n<sub>RSI < 30 = oversold · 30–70 = neutral · > 70 = overbought</sub>", unsafe_allow_html=True)
        else:
            st.caption("RSI — insufficient data")

        st.divider()
        # Pivot levels
        pvt = nsei.get("pivots")
        if pvt:
            st.markdown("##### Pivot Levels (calculated from previous OHLC)")
            import pandas as pd
            pvt_df = pd.DataFrame([
                {"Level": "R2 (Resistance 2)", "Value": f"{pvt['r2']:,.2f}", "Signal": "🔴"},
                {"Level": "R1 (Resistance 1)", "Value": f"{pvt['r1']:,.2f}", "Signal": "🔴"},
                {"Level": "Pivot",             "Value": f"{pvt['pivot']:,.2f}", "Signal": "⚪"},
                {"Level": "S1 (Support 1)",    "Value": f"{pvt['s1']:,.2f}", "Signal": "🟢"},
                {"Level": "S2 (Support 2)",    "Value": f"{pvt['s2']:,.2f}", "Signal": "🟢"},
            ])
            st.dataframe(pvt_df, use_container_width=True, hide_index=True)

        st.divider()
        # MAs
        st.markdown("##### Moving Averages — Nifty 50")
        ma20, ma200 = nsei.get("ma20"), nsei.get("ma200")
        last = nsei["last"]
        mc1, mc2 = st.columns(2)
        if ma20 is not None:
            mc1.metric("20-Day MA", f"{ma20:,.2f}", "🟢 Above" if last > ma20 else "🔴 Below")
        if ma200 is not None:
            mc2.metric("200-Day MA", f"{ma200:,.2f}", "🟢 Above" if last > ma200 else "🔴 Below")


def _pm_section_fii(fii_dii: dict | None) -> None:
    with st.expander("⑤ FII / DII Flows"):
        if fii_dii is None:
            st.info(
                "**FII / DII data unavailable right now.**  \n"
                "NSE India publishes provisional data after ~6 PM IST each session.  \n\n"
                "👉 Live sources:  \n"
                "• [NSE FII/DII Daily](https://www.nseindia.com/reports/fii-statistics)  \n"
                "• [Tapetide FII Tracker](https://tapetide.com)"
            )
            st.caption(
                "FII net buy → bullish · FII net sell → cautious · "
                "DII buying on FII sell days = domestic support"
            )
            return

        def _flow_row(label: str, entry: dict) -> None:
            buy = entry.get("buy_value")
            sell = entry.get("sell_value")
            net = entry.get("net_value")
            date = entry.get("date", "")
            caption = f" · {date}" if date else ""
            if net is not None:
                col = "green" if net >= 0 else "red"
                arrow = "▲" if net >= 0 else "▼"
                st.markdown(
                    f"**{label}** &nbsp; :{col}[{arrow} Net ₹{net:,.2f} Cr]"
                    + (f"  \n<sub>Buy ₹{buy:,.2f} Cr · Sell ₹{sell:,.2f} Cr{caption}</sub>" if buy and sell else ""),
                    unsafe_allow_html=True,
                )
            else:
                st.caption(f"**{label}** — data not available")

        fii = fii_dii.get("fii")
        dii = fii_dii.get("dii")
        if fii:
            _flow_row("FII / FPI (Cash)", fii)
        if dii:
            _flow_row("DII (Cash)", dii)
        if fii and dii and fii.get("net_value") is not None and dii.get("net_value") is not None:
            combined = (fii["net_value"] or 0) + (dii["net_value"] or 0)
            col = "green" if combined >= 0 else "red"
            st.markdown(f"Combined net: :{col}[**₹{combined:,.2f} Cr**]", unsafe_allow_html=True)
        st.caption(
            "Source: NSE India FII/DII feed (provisional, cash segment only) · "
            "FII net buy → bullish · FII net sell → cautious · "
            "DII buying on FII sell days = domestic institutional support"
        )


def _pm_section_commodities(commodities: dict) -> None:
    with st.expander("⑥ Commodities & Forex"):
        order = ["USDINR=X", "BZ=F", "GC=F", "SI=F"]
        for ticker in order:
            row = commodities.get(ticker, {})
            if "error" in row:
                st.caption(f"**{row.get('name', ticker)}** — _{row['error']}_")
                continue
            last, chg, pct = row["last"], row["change"], row["change_pct"]
            arrow, col = ("▲", "green") if chg >= 0 else ("▼", "red")
            # USD/INR and Crude: rising is negative for India
            if ticker in ("USDINR=X", "BZ=F"):
                col = "red" if chg >= 0 else "green"
            w52h, w52l = row.get("week52_high"), row.get("week52_low")
            rng = f" · 52w: {w52l:,.2f}–{w52h:,.2f}" if w52h else ""
            st.markdown(
                f"**{row['name']}** &nbsp; :{col}[{arrow} {last:,.2f} ({chg:+.2f} · {pct:+.2f}%)]"
                + (f"  \n<sub>{rng}</sub>" if rng else ""),
                unsafe_allow_html=True,
            )
            st.write("")
        st.caption(
            "Note: Gold/Silver are COMEX international prices in USD/oz — not MCX INR prices. "
            "For MCX prices visit [mcxindia.com](https://www.mcxindia.com)."
        )


def _pm_section_news(news: list) -> None:
    with st.expander("⑦ News — Nifty 50 Headlines"):
        if not news:
            st.info("No news fetched from yfinance. Yahoo Finance news availability varies.")
            return
        for item in news:
            title = item.get("title", "")
            pub = item.get("publisher", "")
            link = item.get("link", "")
            if link:
                st.markdown(f"• [{title}]({link}) — *{pub}*")
            else:
                st.markdown(f"• **{title}** — *{pub}*")
        st.caption("Source: yfinance / Yahoo Finance. Headlines may be delayed.")


def _pm_section_verdict(india: dict, vix: dict | None) -> None:
    with st.expander("⑧ Verdict — Market Tone"):
        nsei = india.get("^NSEI", {})
        if "error" in nsei:
            st.warning("Cannot compute verdict — Nifty 50 data unavailable.")
            return
        last = nsei["last"]
        ma20, ma200 = nsei.get("ma20"), nsei.get("ma200")
        rsi = nsei.get("rsi")
        chg_pct = nsei.get("change_pct", 0)
        pvt = nsei.get("pivots", {})

        # Determine trend
        above20 = (last > ma20) if ma20 else None
        above200 = (last > ma200) if ma200 else None
        if above20 and above200:
            trend = "🟢 Bullish"
            trend_note = "Nifty is above both 20-day and 200-day MAs — primary trend is up."
        elif above200 and not above20:
            trend = "🟡 Cautious"
            trend_note = "Nifty is above 200-day MA but below 20-day MA — short-term pullback in a longer-term uptrend."
        elif not above200:
            trend = "🔴 Bearish"
            trend_note = "Nifty is below the 200-day MA — primary trend is down."
        else:
            trend = "⚪ Neutral"
            trend_note = "Insufficient moving average data."

        # RSI signal
        if rsi is not None:
            if rsi > 70:
                rsi_note = f"RSI {rsi:.1f} — 🔴 Overbought. Profit-booking possible at resistance."
            elif rsi < 30:
                rsi_note = f"RSI {rsi:.1f} — 🟢 Oversold. Watch for a bounce."
            else:
                rsi_note = f"RSI {rsi:.1f} — 🟡 Neutral range. No extreme reading."
        else:
            rsi_note = "RSI — insufficient data."

        # VIX signal
        if vix and "error" not in vix:
            v = vix["last"]
            vix_note = f"India VIX {v:.2f} — {'🔴 Elevated fear' if v > 20 else ('🟡 Some nervousness' if v > 15 else '🟢 Calm')}"
        else:
            vix_note = "India VIX — unavailable."

        # Key levels
        support = pvt.get("s1")
        resistance = pvt.get("r1")

        st.markdown(f"#### Overall Trend: {trend}")
        st.markdown(trend_note)
        st.divider()

        col1, col2 = st.columns(2)
        col1.markdown(f"**RSI Signal**  \n{rsi_note}")
        col2.markdown(f"**Volatility (VIX)**  \n{vix_note}")

        if support and resistance:
            st.divider()
            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("Today's Support (S1)", f"{support:,.2f}")
            kc2.metric("Today's Close",        f"{last:,.2f}", f"{chg_pct:+.2f}%")
            kc3.metric("Today's Resistance (R1)", f"{resistance:,.2f}")

        st.divider()
        st.info(
            "📋 **Educational use only.** This verdict is a mechanical read of price, MAs "
            "and RSI. It does not account for F&O data, FII flows, news, or macro context. "
            "Consult a SEBI-registered adviser before making any investment decision."
        )


def _render_premarket_report(data: dict) -> None:
    """Render all 8 collapsible sections of the pre-market briefing."""
    # Disclaimer at the very top
    st.warning(_PM_DISCLAIMER)
    fetched_at = data.get("fetched_at", "")
    if fetched_at:
        st.caption(f"Data as of **{fetched_at}** · yfinance (~15-min delayed from Yahoo Finance)")
    st.divider()

    india = data.get("india") or {}
    vix = data.get("vix")
    us = data.get("us") or {}
    commodities = data.get("commodities") or {}
    news = data.get("news") or []
    fii_dii = data.get("fii_dii")

    _pm_section_opening(india, vix)
    _pm_section_global(us, commodities)
    _pm_section_india_levels(india)
    _pm_section_fii(fii_dii)
    _pm_section_commodities(commodities)
    _pm_section_news(news)
    _pm_section_verdict(india, vix)

    st.divider()
    st.info(
        "📋 **Educational use only.** This report is not a recommendation to buy or sell. "
        "Data sourced from yfinance / Yahoo Finance (~15-min delayed). "
        "Consult a SEBI-registered investment adviser before acting on any information above."
    )


def _premarket_section() -> None:
    """Pre-market briefing panel — cached once per calendar day (IST).

    The first user who clicks the button pays the yfinance fetch cost;
    every subsequent visitor reads the same cached result at zero cost.
    """
    with st.expander("📊 Pre-Market Briefing", expanded=False):
        cached_at = premarket_cache.generated_at()

        col_left, col_right = st.columns([3, 1])
        if cached_at:
            col_left.caption(f"⚡ Cached briefing from **{cached_at}** · same for all users today")
            if col_right.button("🔄 Refresh", key="pm_refresh", use_container_width=True):
                premarket_cache.invalidate()
                st.session_state.pop("pm_result", None)
                st.rerun()
        else:
            col_left.caption(
                "Fetches EOD data for Nifty 50, Sensex, Bank Nifty, Nifty Midcap 50 "
                "and Nifty Next 50. Result is shared for all users today."
            )
            if col_right.button("Get Briefing", key="pm_fetch", type="primary", use_container_width=True):
                with st.spinner("Fetching data for all major indices…"):
                    data = _fetch_premarket_data()
                premarket_cache.set(data)
                st.session_state.pm_result = data
                st.rerun()

        # On load: pull from file cache into session state.
        # If the cached entry is in the old LLM format (has "answer" key), discard it
        # so the user sees "Get Briefing" rather than a blank panel.
        if "pm_result" not in st.session_state:
            cached = premarket_cache.get()
            if cached and "india" in cached:
                st.session_state.pm_result = cached
            elif cached and ("answer" in cached or "indices" in cached):
                premarket_cache.invalidate()

        data = st.session_state.get("pm_result")
        if data and "india" in data:
            _render_premarket_report(data)
        elif not cached_at:
            st.info("Press **Get Briefing** to generate today's pre-market summary.")


def render() -> None:
    _premarket_section()
    st.divider()
    search_options = _build_search_options()
    left, middle, right = st.columns([3, 1, 1])
    display = left.selectbox(
        "Search by company name or ticker",
        search_options,
        index=0,
        help="Start typing a company name or ticker symbol to filter the list.",
    )
    window_label = middle.selectbox("Window", list(WINDOW_LABELS), index=0)
    fetch = right.button("Get quote", type="primary", use_container_width=True)

    symbol = _resolve_ticker(display)
    is_index = symbol.startswith("^")

    # Only ever on an explicit click, or when the user changes ticker *after*
    # having asked once. Nothing here may fire on a bare page load.
    #
    # `st.tabs` renders every tab's body on every rerun — Streamlit shows one and
    # runs them all. An auto-fetch here therefore spent an LLM call and a price
    # lookup for someone who opened the app and stayed in Chat. Found in the
    # browser on 2026-11-08; invisible to the tests, which never render a tab.
    asked_before = "market_result" in st.session_state
    changed_ticker = asked_before and st.session_state.get("market_symbol") != symbol

    if fetch or changed_ticker:
        with st.spinner(f"Fetching {symbol}…"):
            st.session_state.market_result = session.run_turn(
                f"How is {symbol} doing?", record_in_chat=False
            )
            st.session_state.market_symbol = symbol
            # Clear any stale deep dive for a new ticker
            if changed_ticker:
                st.session_state.pop(f"dd_result_{symbol.split('.')[0]}", None)
    elif not asked_before:
        st.info(f"Press **Get quote** to fetch {display}.")
        return

    result = st.session_state.get("market_result") or {}
    data = session.market_data()
    quote = _quote_for(symbol, data)

    if quote is None:
        st.warning(result.get("answer") or f"No data available for {symbol}.")
        return

    a, b, c = st.columns(3)
    a.metric("Price", format_inr(quote["price"], paise=True))
    b.metric("Change", format_inr(quote["change"], paise=True),
             format_signed_pct(quote["change_pct"]))
    c.metric("Previous close", format_inr(quote["previous_close"], paise=True))

    freshness = quote.get("freshness", "")
    if quote.get("is_degraded"):
        st.warning(f"⚠ {freshness} — this is not a current price.")
    else:
        st.caption(f"{quote['symbol']} · {freshness} · source: {quote.get('source', '—')}")

    st.plotly_chart(
        price_trend_line(
            quote["symbol"],
            quote.get("trends") or {},
            window=WINDOW_LABELS[window_label],
            freshness=freshness if quote.get("is_degraded") else "",
        ),
        use_container_width=True,
    )

    if result.get("answer"):
        st.markdown("##### Market overview")
        st.markdown(result["answer"])
        render_trace(result.get("trace") or [])

    # Deep dive is only meaningful for individual stocks, not indices
    if not is_index:
        base_ticker = symbol.split(".")[0]
        _stock_deep_dive_section(base_ticker)
