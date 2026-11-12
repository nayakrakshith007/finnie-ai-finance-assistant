"""Portfolio Analysis Agent — values holdings and delivers CA-level structural analysis.

How this works
--------------
Four steps: read holdings from state, get a price for each, hand both to the pure
`analyse()`, then narrate the result with sector concentration, asset-class gaps,
and an educational comparison to target allocations for the user's risk profile.

No arithmetic happens here. Every percentage, score and rupee figure comes from
`portfolio/metrics.py`, where each one is checked against a hand calculation —
because these are the numbers a user will act on.

Where prices come from
----------------------
Two sources, by asset class. A stock or ETF is looked up through
`MarketDataService`, inheriting its whole degradation chain and its provenance
label. A mutual fund, bond or cash balance has no ticker, so it carries the price
the user gave it, labelled `user`. Asking yfinance for "HDFCFLEXI" would be a
guaranteed miss, and a missed price silently drops a holding out of the total.

Privacy
-------
CLAUDE.md constraint 3: never log a user's full portfolio. So this module logs
counts and nothing else — no symbols, no quantities, no values. The same applies
to the trace entry, which is rendered in the UI and written to the log file. The
holdings do go into the prompt, because the model cannot narrate numbers it
cannot see; they do not go anywhere that persists.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base import BaseAgent
from core.config import load_config
from core.logging_setup import get_logger

# Module-level cache: base symbol → sector string.
# Avoids repeated yfinance info calls for the same ticker within a session.
_sector_cache: dict[str, str] = {}
from data.market import MarketDataService, OutOfScopeError
from portfolio.analysis import analyse
from portfolio.holdings import MARKET_TRADED_CLASSES, Holding, parse_holdings
from workflow.state import AgentState

logger = get_logger(__name__)

USER_PRICE_SOURCE = "user"

NO_HOLDINGS_REPLY = (
    "I do not have any holdings for you yet, so there is nothing to analyse. Add "
    "them in the Portfolio tab — you can upload a CSV with columns symbol, "
    "quantity and asset_class, enter them by hand, or load the sample portfolio "
    "to see what the analysis looks like."
)

# Sector mapping for common NSE-listed equities. Used to build sector
# concentration data without a live yfinance info call per holding.
_NSE_SECTOR_MAP: dict[str, str] = {
    "RELIANCE": "Energy / Consumer",
    "TCS": "Information Technology",
    "HDFCBANK": "Banking & Finance",
    "INFY": "Information Technology",
    "ICICIBANK": "Banking & Finance",
    "HINDUNILVR": "FMCG",
    "SBIN": "Banking & Finance",
    "BHARTIARTL": "Telecommunications",
    "KOTAKBANK": "Banking & Finance",
    "WIPRO": "Information Technology",
    "LT": "Infrastructure",
    "AXISBANK": "Banking & Finance",
    "BAJFINANCE": "Banking & Finance (NBFC)",
    "SUNPHARMA": "Pharmaceuticals",
    "MARUTI": "Automobile",
    "NESTLEIND": "FMCG",
    "NTPC": "Power & Energy",
    "POWERGRID": "Power & Energy",
    "ULTRACEMCO": "Cement",
    "TMCV": "Automobile",
    "TATASTEEL": "Steel & Metals",
    "ONGC": "Oil & Gas",
    "BPCL": "Oil & Gas",
    "CIPLA": "Pharmaceuticals",
    "DRREDDY": "Pharmaceuticals",
    "ADANIPORTS": "Infrastructure",
    "ADANIENT": "Diversified",
    "M&M": "Automobile",
    "TECHM": "Information Technology",
    "HCLTECH": "Information Technology",
    "ASIANPAINT": "Paints & Chemicals",
    "INDUSINDBK": "Banking & Finance",
    "JSWSTEEL": "Steel & Metals",
    "TITAN": "Luxury Goods & Jewellery",
    "BAJAJFINSV": "Banking & Finance",
    "COALINDIA": "Mining",
    "HINDALCO": "Metals & Mining",
    "GRASIM": "Diversified",
    "VEDL": "Metals & Mining",
    "HEROMOTOCO": "Automobile",
    "EICHERMOT": "Automobile",
    "APOLLOHOSP": "Healthcare",
    "DIVISLAB": "Pharmaceuticals",
    "SBILIFE": "Insurance",
    "HDFCLIFE": "Insurance",
    "ICICIPRULI": "Insurance",
    "ITC": "FMCG",
    "TATACONSUM": "FMCG",
    "PIDILITIND": "Paints & Chemicals",
    "DMART": "Retail",
    "ZOMATO": "Consumer Tech",
    "PAYTM": "Fintech",
    "NYKAA": "Consumer Tech",
    "IRFC": "Banking & Finance",
    "HAL": "Defence & Aerospace",
    "BHEL": "Capital Goods",
    "SAIL": "Steel & Metals",
    "NHPC": "Power & Energy",
    "RECLTD": "Banking & Finance",
    "PFC": "Banking & Finance",
}

# Asset class keywords → canonical portfolio category for gap analysis
_EQUITY_CLASSES = frozenset({"stock", "etf"})
_DEBT_CLASSES = frozenset({"bond", "mutual_fund"})
_GOLD_KEYWORDS = frozenset({"gold", "sgb", "goldbeees", "goldetf", "sovereign gold"})
_LIQUID_CLASSES = frozenset({"cash"})
_REAL_ESTATE_KEYWORDS = frozenset({"reit", "real estate", "property"})

PORTFOLIO_SYSTEM_PROMPT = """You are Finnie's Senior Portfolio Analyst — think like \
a CFA charterholder, CA, and experienced Indian hedge fund risk manager rolled into one.

Your job: deliver a thorough, structured portfolio review. You may describe structural \
characteristics, explain what they mean, compare the portfolio to typical allocations \
for the user's risk profile, and highlight gaps — all in educational terms.

**What you MAY do (education):**
- State what the portfolio IS structurally (100% equity, 3 sectors, no debt, no gold)
- Compare to typical Indian portfolio allocations for the stated risk profile
- Explain the purpose of each asset class (what debt provides, what gold hedges)
- Name sector concentration risks (60% IT is a sector-cycle risk)
- Highlight tax-efficiency considerations (LTCG thresholds, dividend tax, ELSS benefits)
- Say what a well-structured portfolio of this risk profile typically includes
- Note if the portfolio lacks liquidity buffers, inflation hedges, or downside cushions

**What you must NOT do (advice):**
- Tell the user to buy, sell, switch or rebalance any specific holding
- Recommend a specific fund, scheme, or instrument by name
- Promise or project any return
- Write a disclaimer (one is appended automatically)

**Analysis structure — cover ALL of these:**
1. **Portfolio Overview**: Total value, holding count, risk band, 1-line structural summary
2. **Asset Allocation vs Target**: Compare current allocation to the target for \
the user's risk profile. Be specific: "You hold X% equity vs a typical Y% for a \
moderate investor."
3. **Sector Concentration** (equity holdings only): Name dominant sectors, \
flag any sector above 30% of equity, explain what sector concentration means
4. **What's Missing**: Identify absent asset classes (debt, gold, liquid/cash, \
international, REITs) and explain what each typically provides in an Indian portfolio
5. **Tax Efficiency**: Comment on the tax character of the portfolio \
(LTCG vs STCG, dividend income, ELSS/PPF wrappers if present, expense ratios)
6. **Risk & Diversification**: HHI, effective holdings, concentration flags
7. **One Follow-up Question**: Offer to drill into whichever area the data \
makes most interesting

LENGTH & FORMAT — apply to every answer:
- **Very first line — always**: print this note exactly as shown (replace nothing): \
> ⚠️ _For accurate sector data, stock symbols must be valid on Yahoo Finance \
(e.g. RELIANCE, TCS, HDFCBANK). Unknown symbols will show as "Other/Unknown"._
- **Second line — portfolio snapshot in bold**: total value, number of holdings, \
risk band (e.g. "**Portfolio: ₹X across N holdings — Moderate risk**").
- Present the asset allocation as a Markdown table immediately after: \
one row per asset class, columns for weight % and typical target %.
- Use `###` headers for each of the 7 analysis sections — mandatory, every time.
- **Bold** every key figure: values, percentages, HHI, diversification score.
- Bullets within each section — no prose paragraphs longer than 2 sentences.
- Sector concentration: use a table (sector | % of equity | flag).
- Gaps section: one bullet per missing class with a 1-line explanation.
- Be thorough within this structure — the user wants depth, not brevity.

{risk_profile_context}

Portfolio data:
{data}"""

PORTFOLIO_USER_TEMPLATE = "{question}"


class PortfolioAnalysisAgent(BaseAgent):
    """Values a user's holdings and explains their structure."""

    name = "portfolio_analysis"
    description = (
        "Analyses the user's OWN holdings: total value, what each position is "
        "worth, allocation by holding and by asset class, concentration risk, a "
        "diversification score, fund expense costs, unrealised profit and loss, "
        "and an overall risk band. Use this whenever the user asks about 'my "
        "portfolio', 'my holdings', 'my investments' or how their own money is "
        "allocated. Do NOT use it for the price of a company they do not own "
        "(that is market analysis) or for how an instrument works (finance Q&A)."
    )

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        service: Any | None = None,
    ) -> None:
        super().__init__(llm=llm)
        self._service = service

    @property
    def service(self) -> Any:
        """Built on first use, so constructing the agent needs no config or network."""
        if self._service is None:
            self._service = MarketDataService()
        return self._service

    # ── the work ──────────────────────────────────────────────────────────────

    def handle(self, state: AgentState) -> dict[str, Any]:
        existing = dict(state.get("portfolio") or {})
        rows = existing.get("holdings") or []

        if not rows:
            logger.info("No holdings in state; asking the user to add some")
            return {"messages": [AIMessage(content=NO_HOLDINGS_REPLY)]}

        holdings, errors = parse_holdings(rows)
        if not holdings:
            # Nothing valid to value. Report precisely what was wrong and spend no
            # tokens narrating an empty analysis.
            logger.info("All %d holding rows rejected", len(rows))
            return {"messages": [AIMessage(content=self._error_reply(errors))]}

        prices = self._price(holdings)
        cfg = load_config()
        analysis = analyse(
            holdings,
            prices,
            risk_weights=cfg.portfolio.risk_weights,
            concentration_pct=cfg.portfolio.concentration_warning_pct,
            currency=cfg.market.currency,
        )

        user_profile = state.get("user_profile") or {}
        risk_appetite = str(user_profile.get("risk_appetite") or "moderate")
        horizon_years = int(user_profile.get("horizon_years") or 10)

        risk_profile_context = self._risk_profile_context(
            risk_appetite, horizon_years, cfg.portfolio.allocation_targets
        )
        sector_data = self._sector_breakdown(analysis["holdings"])
        gap_data = self._asset_class_gaps(analysis["class_breakdown"])

        prompt_data = self._for_prompt(analysis, sector_data, gap_data)
        system = PORTFOLIO_SYSTEM_PROMPT.format(
            data=prompt_data,
            risk_profile_context=risk_profile_context,
        )
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=PORTFOLIO_USER_TEMPLATE.format(question=self._question(state))),
        ]
        body = str(self.llm.invoke(messages).content).rstrip()

        # Appended by code, not left to the model: an excluded holding and a
        # parse error are both things the user must see even if rule 5 is ignored.
        if analysis["is_degraded"]:
            # Appended by code for the same reason the market agent does it: a
            # stale price shown as current is the exact failure the degradation
            # chain exists to prevent, and prompt rule 5 is a request to the
            # model rather than a guarantee (FR-033).
            body += f"\n\n{self._degraded_note(analysis)}"
        if analysis["unpriced"]:
            body += (
                f"\n\nI could not get a price for {', '.join(analysis['unpriced'])}, "
                "so the total above excludes them."
            )
        if errors:
            body += f"\n\n{self._error_reply(errors)}"

        body += (
            "\n\n---\n💡 **For a full portfolio breakdown** — pie chart, asset-class bar, "
            "per-stock Deep Dive buttons, and concentration flags — head to the **Portfolio tab**."
        )

        return {
            "messages": [AIMessage(content=body)],
            # `holdings` stays as the user's input; `analysis` is this turn's output.
            "portfolio": {**existing, "analysis": analysis},
        }

    def trace_detail(self, update: dict[str, Any]) -> str:
        analysis = (update.get("portfolio") or {}).get("analysis")
        if not analysis:
            return "no holdings to analyse"
        # Counts and bands only. No symbols, no values -- the trace is logged and
        # rendered, and constraint 3 applies to both.
        parts = [
            f"{analysis['holding_count']} holdings",
            f"{len(analysis['class_breakdown'])} asset classes",
            f"risk {analysis['risk_band']}",
            f"diversification {analysis['diversification_score']}/100",
        ]
        if analysis["unpriced"]:
            parts.append(f"{len(analysis['unpriced'])} unpriced")
        if analysis["is_degraded"]:
            parts.append("degraded prices")
        return ", ".join(parts)

    # ── pricing ───────────────────────────────────────────────────────────────

    def _price(self, holdings: list[Holding]) -> dict[str, tuple[float, str]]:
        """Build symbol -> (price, source) for every holding that can be priced.

        A holding's own `price` wins over a lookup: the user knows their fund's
        NAV and Finnie cannot look it up. A symbol that cannot be priced is simply
        absent from the map, and `analyse()` excludes it and names it rather than
        valuing it at zero.
        """
        prices: dict[str, tuple[float, str]] = {}
        for holding in holdings:
            if holding.price is not None:
                prices[holding.symbol] = (holding.price, USER_PRICE_SOURCE)
                continue
            if holding.asset_class not in MARKET_TRADED_CLASSES:
                # No ticker and no price given: nothing to look up.
                continue
            try:
                quote = self.service.get_quote(holding.symbol)
            except OutOfScopeError:
                logger.info("No listing for a holding; it will be excluded from the total")
                continue
            except Exception as exc:  # noqa: BLE001 - one bad price must not sink the analysis
                logger.warning("Price lookup failed (%s); holding excluded", type(exc).__name__)
                continue
            prices[holding.symbol] = (quote.price, quote.source)
        return prices

    # ── helpers ───────────────────────────────────────────────────────────────

    def _question(self, state: AgentState) -> str:
        """The user's question, or a default when the UI invoked this directly.

        The Portfolio tab can run the analysis from a button rather than a typed
        question, in which case there is no HumanMessage to find.
        """
        try:
            return self._latest_question(state)
        except ValueError:
            return "Analyse my portfolio."

    @staticmethod
    def _fetch_sector_yfinance(ticker: str) -> str:
        """Try to get the sector for a ticker from yfinance info.

        Tries both .NS and .BO suffixes (NSE first). Returns the sector string
        from yfinance, or "Other / Unknown" if unavailable or on any error.
        Keeps the lookup out of the hot path — called only when the static map
        has no entry.
        """
        import yfinance as yf  # noqa: PLC0415 — deferred import, only used here
        for suffix in (".NS", ".BO"):
            try:
                info = yf.Ticker(ticker + suffix).info
                sector = info.get("sector") or info.get("industryDisp") or ""
                if sector:
                    return sector
            except Exception:  # noqa: BLE001
                continue
        return "Other / Unknown"

    @staticmethod
    def _sector_breakdown(holdings_rows: list[dict[str, Any]]) -> dict[str, float]:
        """Compute sector weights as % of total equity value.

        Static map (fast) → yfinance info (network, cached) → "Other / Unknown".
        Only stock/ETF holdings are included; debt, gold, cash have no sector.
        """
        sector_values: dict[str, float] = {}
        for row in holdings_rows:
            if row.get("asset_class") not in ("stock", "etf"):
                continue
            ticker = row["symbol"].upper().split(".")[0]

            if ticker in _NSE_SECTOR_MAP:
                sector = _NSE_SECTOR_MAP[ticker]
            elif ticker in _sector_cache:
                sector = _sector_cache[ticker]
            else:
                sector = PortfolioAnalysisAgent._fetch_sector_yfinance(ticker)
                _sector_cache[ticker] = sector
                logger.info("Sector for %s resolved via yfinance: %s", ticker, sector)

            sector_values[sector] = sector_values.get(sector, 0.0) + row["value"]

        total = sum(sector_values.values())
        if not total:
            return {}
        return {s: round(v / total * 100, 2) for s, v in sorted(
            sector_values.items(), key=lambda x: -x[1]
        )}

    @staticmethod
    def _asset_class_gaps(class_breakdown: dict[str, float]) -> dict[str, str]:
        """Identify missing or underweight asset classes and explain what each provides.

        Returns a dict of {gap_name: educational_explanation} for each gap found.
        """
        present = {k.lower() for k in class_breakdown}
        gaps: dict[str, str] = {}

        has_equity = any(c in present for c in _EQUITY_CLASSES)
        has_debt = any(c in present for c in _DEBT_CLASSES)
        has_gold = any(any(kw in c for kw in _GOLD_KEYWORDS) for c in present)
        has_liquid = any(c in present for c in _LIQUID_CLASSES)
        has_reit = any(any(kw in c for kw in _REAL_ESTATE_KEYWORDS) for c in present)

        equity_pct = sum(v for k, v in class_breakdown.items() if k.lower() in _EQUITY_CLASSES)

        if not has_debt:
            gaps["Debt / Fixed Income"] = (
                "No debt allocation detected. Debt instruments (government securities, "
                "corporate bonds, debt mutual funds, PPF, NPS) provide capital preservation, "
                "regular income, and reduce portfolio drawdowns during equity bear markets. "
                "In Indian portfolios they also offer indexation benefits on LTCG."
            )
        if not has_gold:
            gaps["Gold"] = (
                "No gold allocation detected. Gold has historically had low or negative "
                "correlation with Indian equities, acting as an inflation hedge and a "
                "safe-haven asset during market stress. Sovereign Gold Bonds (SGBs) offer "
                "2.5% annual interest + capital appreciation with no capital gains tax on maturity."
            )
        if not has_liquid:
            gaps["Cash / Liquid Buffer"] = (
                "No cash or liquid fund allocation detected. A liquid buffer of 3–6 months' "
                "expenses prevents being forced to sell equity in a down market. Liquid mutual "
                "funds deliver better returns than savings accounts with same-day redemption."
            )
        if not has_reit:
            gaps["Real Estate / REITs"] = (
                "No real-estate exposure detected. REITs (Real Estate Investment Trusts) "
                "listed on NSE/BSE allow fractional ownership of commercial real estate "
                "with SEBI-mandated 90% dividend distribution, providing income diversification."
            )
        if equity_pct > 90 and has_debt:
            gaps["International Equity"] = (
                "Portfolio is very equity-heavy (%.1f%% equity) but all in Indian markets. "
                "International equity (via feeder funds or FoFs, within RBI LRS limits) "
                "reduces home-country bias and adds currency diversification." % equity_pct
            )

        return gaps

    @staticmethod
    def _risk_profile_context(
        risk_appetite: str,
        horizon_years: int,
        allocation_targets: dict[str, dict[str, int]],
    ) -> str:
        """Build the risk-profile section of the system prompt."""
        targets = allocation_targets.get(risk_appetite, {})
        if not targets:
            return f"User risk profile: {risk_appetite}, {horizon_years}-year horizon."

        target_text = ", ".join(f"{k.replace('_', ' ')} {v}%" for k, v in targets.items())
        return (
            f"User risk profile: {risk_appetite.upper()}, {horizon_years}-year investment horizon.\n"
            f"Typical target allocation for a {risk_appetite} investor: {target_text}.\n"
            "When comparing the user's current allocation to this target, name the gaps "
            "explicitly (e.g. 'You hold X% equity but a typical moderate investor targets Y%')."
        )

    @staticmethod
    def _for_prompt(
        analysis: dict[str, Any],
        sector_data: dict[str, float] | None = None,
        gap_data: dict[str, str] | None = None,
    ) -> str:
        """The data block the model sees. Finished numbers, provenance included."""
        a = analysis
        cur = a["currency"]
        lines = [
            f"Total value: {cur} {a['total_value']:,.2f} across {a['holding_count']} holdings",
        ]
        if a["unrealised_pnl"] is not None:
            lines.append(
                f"Unrealised P&L: {cur} {a['unrealised_pnl']:+,.2f} "
                f"({a['unrealised_pnl_pct']:+.2f}%) on a cost of {cur} {a['total_cost']:,.2f}"
            )
        elif not a["cost_basis_complete"]:
            lines.append("Unrealised P&L: not available (purchase prices not given for every holding)")

        lines.append("Asset class allocation: " + ", ".join(
            f"{name} {pct:.2f}%" for name, pct in a["class_breakdown"].items()
        ))
        lines.append(
            f"Concentration: HHI {a['hhi']:.4f}, behaves like "
            f"{a['effective_holdings']:.2f} equally-weighted holdings; "
            f"diversification score {a['diversification_score']}/100 "
            "(0-100 composite of evenness, breadth and asset-class spread)"
        )
        if a["concentration_flags"]:
            lines.append("Above the concentration limit: " + ", ".join(
                f"{f['symbol']} at {f['weight_pct']:.2f}%" for f in a["concentration_flags"]
            ))
        else:
            lines.append("No single holding is above the concentration limit")

        lines.append(f"Risk: score {a['risk_score']:.2f}/5, band {a['risk_band']}")
        if a["annual_expense_cost"]:
            lines.append(
                f"Fund fees: {cur} {a['annual_expense_cost']:,.2f} per year — "
                f"{a['fund_weighted_expense_ratio']:.2f}% of the fund holdings, "
                f"{a['blended_expense_ratio']:.2f}% of the whole portfolio"
            )
        else:
            lines.append("Fund fees: none of the holdings charge an expense ratio")

        # Sector breakdown (equity only)
        if sector_data:
            lines.append("\nSector concentration (% of equity value):")
            for sector, pct in sector_data.items():
                flag = " ⚠ HIGH" if pct > 30 else ""
                lines.append(f"  {sector}: {pct:.1f}%{flag}")
        else:
            lines.append("Sector breakdown: not available (no equity holdings mapped)")

        # Asset class gaps
        if gap_data:
            lines.append("\nMissing / underweight asset classes:")
            for asset_class, explanation in gap_data.items():
                lines.append(f"  {asset_class}: {explanation}")
        else:
            lines.append("\nAsset class gaps: none detected (portfolio has equity, debt, gold and liquid)")

        lines.append("\nHoldings:")
        for row in a["holdings"]:
            ticker = row["symbol"].upper().split(".")[0]
            sector_tag = _NSE_SECTOR_MAP.get(ticker, "")
            sector_str = f", sector: {sector_tag}" if sector_tag else ""
            line = (
                f"  {row['symbol']} ({row['name']}, {row['asset_class']}{sector_str}): "
                f"{row['quantity']:g} x {cur} {row['price']:,.2f} = "
                f"{cur} {row['value']:,.2f}, {row['weight_pct']:.2f}% "
                f"[price source: {row['source']}]"
            )
            if row["unrealised_pnl"] is not None:
                line += f", P&L {cur} {row['unrealised_pnl']:+,.2f} ({row['unrealised_pnl_pct']:+.2f}%)"
            lines.append(line)

        lines.append("Price sources present: " + ", ".join(a["sources"]))
        if a["is_degraded"]:
            lines.append(
                "WARNING: at least one price is STALE or SAMPLE DATA, not current. "
                "Say so in your answer."
            )
        if a["unpriced"]:
            lines.append(
                f"Could not be priced and is EXCLUDED from the total: {', '.join(a['unpriced'])}"
            )
        return "\n".join(lines)

    @staticmethod
    def _degraded_note(analysis: dict[str, Any]) -> str:
        """Name the holdings whose price is not current, and say what that means."""
        labels = {
            "stale_cache": "a STALE cached price, the live feed was unavailable",
            "mock": "SAMPLE DATA, not a real price",
        }
        affected = "; ".join(
            f"{row['symbol']} — {labels.get(row['source'], row['source'])}"
            for row in analysis["holdings"]
            if row["is_degraded"]
        )
        return (
            f"Note on freshness: {affected}. The total above is therefore not a "
            "current valuation."
        )

    @staticmethod
    def _error_reply(errors: list[str]) -> str:
        """Report rejected rows verbatim — they already name the row and the value."""
        heading = (
            "I could not read some of your holdings:"
            if len(errors) > 1
            else "I could not read one of your holdings:"
        )
        bullets = "\n".join(f"- {e}" for e in errors)
        return f"{heading}\n{bullets}"
