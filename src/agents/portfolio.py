"""Portfolio Analysis Agent — values holdings and explains them (PRD FR-012).

How thin this deliberately is
-----------------------------
Four steps: read holdings from state, get a price for each, hand both to the pure
`analyse()`, narrate the result. No arithmetic happens here. Every percentage,
score and rupee figure comes from `portfolio/metrics.py`, where each one is
checked against a hand calculation — because these are the numbers a user will
act on, and "the model worked it out" is not a standard of proof.

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

PORTFOLIO_SYSTEM_PROMPT = """You are Finnie's portfolio analyst, explaining a \
beginner's own holdings to them.

Every figure below has already been calculated. Use those numbers exactly as \
given and do no arithmetic of your own.

Rules:
1. Describe what the portfolio *is*, not what to do about it. You may say a \
portfolio is concentrated in one holding, heavily weighted to equity, or paying \
a certain amount in fund fees. You may not tell them to buy, sell, switch or \
rebalance, and you must not recommend a target allocation. Explaining what \
concentration means is education; telling someone to reduce it is advice.
2. Never invent a number. Every figure in your answer must appear in the data.
3. Lead with the total value and the single most notable structural fact.
4. Explain one metric in plain words rather than listing them all. The \
diversification score and effective-holdings count mean nothing to a beginner \
unless you say what they measure.
5. If any price is marked stale, sample or user-supplied, say so and say which \
holdings it affects. If any holding could not be priced, state that the total \
excludes it.
6. Do NOT write a disclaimer or closing caveat. One is appended automatically.
7. Six sentences at most, or a short bullet per point. Plain English, no jargon \
without a gloss.

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

        messages = [
            SystemMessage(content=PORTFOLIO_SYSTEM_PROMPT.format(data=self._for_prompt(analysis))),
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

    @staticmethod
    def _question(state: AgentState) -> str:
        """The user's question, or a default when the UI invoked this directly.

        The Portfolio tab can run the analysis from a button rather than a typed
        question, in which case there is no HumanMessage to find.
        """
        try:
            return BaseAgent._latest_question(state)
        except ValueError:
            return "Analyse my portfolio."

    @staticmethod
    def _for_prompt(analysis: dict[str, Any]) -> str:
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

        lines.append("Asset classes: " + ", ".join(
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

        lines.append("Holdings:")
        for row in a["holdings"]:
            line = (
                f"  {row['symbol']} ({row['name']}, {row['asset_class']}): "
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
