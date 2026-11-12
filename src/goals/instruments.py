"""Instrument recommendation for Indian goal planning — the CA layer.

Returns the appropriate investment vehicle category for a goal based on its
horizon and type, with tax treatment and Section 80C eligibility.

All recommendations are *categories* (Liquid Fund, ELSS, NPS), never specific
fund names — consistent with the education-not-advice constraint. The CA notes
explain how the instruments work and their tax treatment under Indian tax law.
"""
from __future__ import annotations

from dataclasses import dataclass

# Horizon thresholds (years)
_SHORT = 3
_MEDIUM = 7


@dataclass(frozen=True)
class InstrumentRec:
    vehicle: str
    ca_note: str
    tax_note: str
    sec_80c: bool


def recommend(
    horizon_years: float,
    goal_type: str = "general",
    risk: str = "moderate",
) -> InstrumentRec:
    """Return the instrument category and CA note for a goal.

    Priority: goal_type overrides horizon for specific cases (home, retirement).
    For general goals, horizon drives the selection.
    """
    gtype = goal_type.lower().strip()

    if gtype == "emergency":
        return InstrumentRec(
            vehicle="Liquid Mutual Fund or Sweep-in FD",
            ca_note=(
                "Emergency funds must be instantly accessible — same-day or next-day "
                "redemption is non-negotiable. Liquid funds typically yield 4–5% with "
                "T+1 redemption. A sweep-in FD auto-converts your savings balance above "
                "a threshold into an FD, earning ~6–7% while staying liquid. "
                "Target: 6 months of fixed expenses before funding any other goal."
            ),
            tax_note="Interest / STCG taxed at your income-tax slab rate. No special rate.",
            sec_80c=False,
        )

    if gtype in ("home", "house", "property"):
        if horizon_years <= _SHORT:
            return InstrumentRec(
                vehicle="Arbitrage Fund or Short-Duration Debt Fund",
                ca_note=(
                    "Down payment in 1–3 years: keep it in debt/arbitrage funds — "
                    "no equity risk close to the goal date. "
                    "Home loan tax benefits once the purchase happens: "
                    "Section 80C covers principal repayment (up to ₹1.5L/yr under the "
                    "aggregate 80C ceiling); Section 24B allows up to ₹2L/yr on interest "
                    "for a self-occupied property. Combined saving at 30% slab: ~₹1.05L/yr. "
                    "Stamp duty and registration fees are NOT claimable under 80C."
                ),
                tax_note="Arbitrage fund LTCG (>1 yr holding): 12.5% above ₹1.25L threshold.",
                sec_80c=False,
            )
        return InstrumentRec(
            vehicle="Balanced Advantage Fund → shift to Debt in last 2 years",
            ca_note=(
                "Down payment in 3–7 years: start in a Balanced Advantage Fund (BAF) "
                "which auto-reduces equity when markets are expensive. "
                "Run a Systematic Transfer Plan (STP) into a debt fund 18–24 months "
                "before the purchase date to protect the corpus from a last-minute crash. "
                "Home loan Section 80C + 24B benefits apply after purchase (see above)."
            ),
            tax_note="Equity LTCG (>1 yr): 12.5% above ₹1.25L; Debt fund gains: slab rate.",
            sec_80c=False,
        )

    if gtype in ("education", "children", "child"):
        if horizon_years >= _MEDIUM:
            return InstrumentRec(
                vehicle="ELSS + Nifty 50 Index Fund",
                ca_note=(
                    "7+ years is a strong equity horizon for education savings. "
                    "ELSS gives a 3-year lock-in and Section 80C benefit (up to ₹1.5L/yr) — "
                    "the shortest lock-in of all 80C instruments. "
                    "Sukanya Samriddhi Yojana (SSY): mandatory mention if the beneficiary "
                    "is a girl child — 8.2% government-guaranteed, fully EEE tax status "
                    "(contribution, growth, and withdrawal all tax-free), matures at age 21, "
                    "partial withdrawal allowed at age 18 for education."
                ),
                tax_note="ELSS LTCG (>1 yr): 12.5% above ₹1.25L threshold.",
                sec_80c=True,
            )
        return InstrumentRec(
            vehicle="Balanced Advantage Fund or Short-Duration Debt Fund",
            ca_note=(
                "Horizon under 7 years: hybrid/debt preferred over pure equity. "
                "SSY (for girl child): government-guaranteed at 8.2%, Section 80C "
                "eligible, partial withdrawal allowed for education at age 18. "
                "Consider whether the education goal is firm (fixed year) or flexible — "
                "a firm date means more debt; a flexible date allows more equity."
            ),
            tax_note="Debt/hybrid fund gains taxed at income-tax slab rate.",
            sec_80c=False,
        )

    if gtype in ("retirement", "retire"):
        return InstrumentRec(
            vehicle="NPS Tier-1 + ELSS + PPF (three-layer approach)",
            ca_note=(
                "Three tax layers, stacked for maximum efficiency: "
                "PPF — EEE status (contribution, growth, withdrawal all tax-free), "
                "Section 80C, 15-year lock-in with partial withdrawal from year 7. "
                "ELSS — Section 80C, 3-year lock-in, equity growth potential. "
                "NPS Tier-1 — Section 80C (within ₹1.5L ceiling) PLUS an additional "
                "₹50,000 under Section 80CCD(1B) — the only deduction that breaches "
                "the ₹1.5L ceiling, saving ₹15,000 at the 30% slab. "
                "NPS at retirement: 60% withdrawn tax-free, 40% must be used to buy "
                "an annuity (annuity income is taxed at slab rate)."
            ),
            tax_note="NPS: 60% withdrawal tax-free; annuity taxed at slab. PPF: fully tax-free.",
            sec_80c=True,
        )

    # General goal — horizon-driven
    if horizon_years < _SHORT:
        return InstrumentRec(
            vehicle="Liquid Fund / FD / Recurring Deposit",
            ca_note=(
                "Short horizon: preserve capital first, grow second. "
                "Liquid funds offer ~4–5% with T+1 redemption. "
                "Bank FDs offer ~6–7% at major banks and are deposit-insured up to ₹5L. "
                "Recurring Deposits (RDs) build SIP discipline into a fixed return — "
                "useful if you want to commit a fixed monthly amount."
            ),
            tax_note="Interest taxed at income-tax slab rate. TDS applies on FD interest >₹40K/yr.",
            sec_80c=False,
        )

    if horizon_years < _MEDIUM:
        return InstrumentRec(
            vehicle="Balanced Advantage Fund (BAF) or Multi-Asset Fund",
            ca_note=(
                "Medium horizon: hybrid funds auto-manage the equity/debt mix. "
                "BAFs use valuation signals (P/E, P/B) to reduce equity when markets "
                "are expensive and increase it when cheap — lower volatility than pure equity. "
                "Multi-asset funds add gold, reducing correlation with equity."
            ),
            tax_note="Equity LTCG (>1 yr holding): 12.5% above ₹1.25L threshold.",
            sec_80c=False,
        )

    return InstrumentRec(
        vehicle="Nifty 50 Index Fund + ELSS (if 80C headroom exists)",
        ca_note=(
            "Long horizon: equity index funds are the workhorse of Indian retail investing. "
            "ELSS doubles as a Section 80C instrument (up to ₹1.5L/yr) with a 3-year "
            "lock-in — the shortest lock-in of all 80C options. "
            "Step up the SIP by 10–15% each year (Step-up SIP) to match salary increments — "
            "a ₹10,000 SIP stepped up 10% annually becomes ₹25,937 by year 10, compounding "
            "the compounding."
        ),
        tax_note="LTCG (>1 yr): 12.5% on gains above ₹1.25L threshold per financial year.",
        sec_80c=True,
    )
