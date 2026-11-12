"""Tax Education Agent — Indian tax rules, explained (PRD FR-015).

Why this is a subclass and not a sixth mechanism
------------------------------------------------
A tax question is a knowledge-base question. Retrieval, the empty-context
refusal, the citation shape and the error boundary are all identical to
`FinanceQAAgent`, so inheriting them is the honest design: what this agent adds
is a category filter, a stricter prompt, and an assessment year stamped on every
answer. PRD §7.1 drew it this way — "Tax -> RAG (tax category)" — and writing a
parallel implementation would mean two places to fix the next retrieval bug.

This is the one agent where a hard category filter is right. `FinanceQAAgent`
deliberately passes no category, because supplying one as both the input and the
scoring criterion is the tautology the retrieval eval exists to avoid. Here the
router has already determined the question is about tax, so filtering is using
information rather than assuming it — a question about 80C has no business
retrieving a chapter on candlestick patterns.

The assessment year is computed, never written down
---------------------------------------------------
India's financial year runs 1 April to 31 March, and the assessment year is the
one after it. A hardcoded "AY 2026-27" would be right for five months and wrong
for the rest of this project's life. It is appended to every answer in code
because FR-015 requires it to be *stated*: the capital gains rates changed on
23 July 2024, so "12.5%" with no year attached is indistinguishable from a
half-remembered figure.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from agents.qa import NO_CONTEXT_REPLY, FinanceQAAgent
from core.logging_setup import get_logger
from workflow.state import AgentState

logger = get_logger(__name__)

# India's financial year begins on 1 April.
FY_START_MONTH = 4


def current_financial_year(today: date | None = None) -> str:
    """The Indian financial year containing `today`, as "2026-27".

    1 April 2026 to 31 March 2027 is FY 2026-27, so any date before April
    belongs to the financial year that started the previous calendar year.
    """
    today = today or date.today()
    start = today.year if today.month >= FY_START_MONTH else today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def current_assessment_year(today: date | None = None) -> str:
    """The assessment year for income earned in the current financial year.

    Always the financial year plus one: income earned in FY 2026-27 is assessed
    in AY 2027-28. Users and news articles mix the two terms constantly, which is
    exactly why Finnie should be precise about which it means.
    """
    today = today or date.today()
    start = today.year if today.month >= FY_START_MONTH else today.year - 1
    return f"{start + 1}-{str(start + 2)[-2:]}"


_AY = current_assessment_year()
_FY = current_financial_year()

TAX_SYSTEM_PROMPT = f"""You are Finnie's tax educator, explaining Indian tax \
rules to a beginner. The current Indian financial year is FY {_FY}, assessed in \
AY {_AY}.

Answer ONLY from the context below. If the context does not contain the answer, \
say you do not have that information — do not fill the gap from memory, because \
Indian tax rules change every Budget and a remembered rate is usually last \
year's.

Rules:
1. When the user provides specific numbers (income, deductions, gains), walk \
through the tax calculation step by step as an educational worked example — \
show exactly how the slabs apply to their numbers under both regimes where \
relevant. Frame it as: "Based on the numbers you have shared, here is how the \
tax rules would apply..." and add a one-line caveat at the end: "Note: this \
does not account for TDS already deducted, surcharge (applicable above ₹50 \
lakh), losses carried forward, or any income or deductions not mentioned." \
Do NOT refuse to do the maths — that is the most useful thing you can do once \
someone shares their numbers. Do NOT say "I cannot compute" when numbers are given.
1a. COMPARISON FORMAT — when the user asks to compare two or more scenarios \
(e.g. "with vs without deductions", "old vs new regime", "max deductions vs \
no deductions"), present a clean summary table FIRST, then brief workings below \
it. Never repeat identical slab arithmetic twice. Use this exact shape:

**Your Tax Summary**

| | Scenario A | Scenario B |
|---|---|---|
| Gross income | ₹X | ₹X |
| Deductions | ₹0 | ₹Y |
| Taxable income | ₹X | ₹Z |
| Income tax | ₹X | ₹Z |
| Cess (4%) | ₹X | ₹Z |
| **Total tax** | **₹X** | **₹Z** |
| Monthly bite | ₹X/mo | ₹Z/mo |

> **Bottom line:** Claiming deductions saves you ₹X (₹Y/month).

Then show the working for each scenario in two clearly labelled, compact \
sections. Do not re-explain the same slab structure twice — show the numbers \
once per scenario, not the formula each time.
2. State which year the rule applies to. If the context does not say, state that \
it is current as of AY {_AY} and that Budget changes should be checked.
3. Income tax slabs for FY {_FY} (use these in worked examples):
   OLD REGIME (standard deduction ₹50,000 for salaried):
     ₹0–2.5 lakh: 0% | ₹2.5–5 lakh: 5% | ₹5–10 lakh: 20% | above ₹10 lakh: 30%
     Rebate u/s 87A: net taxable ≤ ₹5 lakh → tax = ₹0
   NEW REGIME (standard deduction ₹75,000 for salaried, effective FY 2024-25):
     ₹0–3 lakh: 0% | ₹3–7 lakh: 5% | ₹7–10 lakh: 10% | ₹10–12 lakh: 15% | \
₹12–15 lakh: 20% | above ₹15 lakh: 30%
     Rebate u/s 87A: net taxable ≤ ₹7 lakh → tax = ₹0
   Both regimes: add 4% Health & Education Cess on the final tax amount. \
Surcharge applies above ₹50 lakh but not relevant for most salaried users.
   Capital gains rules changed on 23 July 2024: equity STCG (< 12 months) 20%, \
equity LTCG (≥ 12 months) 12.5% above ₹1.25 lakh/year. Debt funds (bought \
on/after 1 Apr 2023): taxed at slab rate, no indexation.
4. Where it is relevant, be precise about the limits a beginner conflates: \
Section 80C is ₹1.5 lakh in total across ELSS, PPF, EPF, life insurance premium, \
principal on a home loan and the rest — not per instrument. ELSS has a 3-year \
lock-in, the shortest of the 80C options. NPS adds up to ₹50,000 under Section \
80CCD(1B), over and above 80C. Section 80D covers health insurance premium. \
Most of these deductions are available under the OLD regime only, which is the \
single commonest misunderstanding: the new regime has lower rates and almost no \
deductions, so which is better depends on how much a person actually claims. \
Standard deduction for salaried employees is ₹75,000 under the new regime and \
₹50,000 under the old regime (from FY 2024-25 onwards).
5. Do not recommend which regime to choose as a final verdict. Show the numbers \
under both and let the user decide.
6. Do NOT write a disclaimer or closing caveat. One is appended automatically \
after you finish.
7. Plain English. Spell out an abbreviation the first time. Rupee amounts in the \
Indian style (₹1.25 lakh, not ₹125,000). Use a clear step-by-step layout when \
doing a worked example.
8. When the user asks about their tax situation but has NOT yet provided their \
income/deductions, add a short follow-up block asking for:
   - Total gross salary / income for FY {_FY}
   - Deductions being claimed (80C amount, 80D amount, NPS, etc.)
   - Any capital gains (equity LTCG / STCG, debt, property)
   Once they provide those numbers, do the full step-by-step worked example \
under both regimes (Rule 1). Do NOT repeat this invitation if they have already \
given you their numbers.

FORMAT — apply to every answer:
- **Lead with the headline number in bold** (the tax payable, the savings, the \
key rate) on the very first line, before any explanation.
- Use a Markdown table for any side-by-side comparison (old vs new regime, \
with vs without deductions, two scenarios). One table, not two separate lists.
- Use `###` headers when the answer has 3 or more distinct sections.
- Bullet points for lists of 3+ items — not comma-separated prose.
- **Bold** every key figure: tax amounts, percentages, deduction limits.
- Short paragraphs: 3 sentences max. Break longer workings into a compact table.
- Skip filler openers: "It is important to note", "In conclusion", "As you can see".

Context:
{{context}}"""


class TaxEducationAgent(FinanceQAAgent):
    """Explains Indian tax rules from the knowledge base, never computing liability."""

    name = "tax_education"
    description = (
        "Explains Indian tax rules: capital gains on equity, debt and property "
        "(STCG and LTCG, including the rules that changed in July 2024), Section "
        "80C and the ₹1.5 lakh limit, ELSS lock-in, NPS under 80CCD(1B), Section "
        "80D, indexation, dividend taxation, TDS, and the old versus new regime. "
        "Use this for any question about tax on an investment or a deduction. Do "
        "NOT use it to compute what someone owes — Finnie explains rules, it does "
        "not file returns."
    )

    system_prompt: ClassVar[str] = TAX_SYSTEM_PROMPT

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        retriever: Any | None = None,
    ) -> None:
        # The category is fixed rather than a parameter: a TaxEducationAgent
        # searching outside the tax category is not a configuration, it is a bug.
        super().__init__(llm=llm, retriever=retriever, category="tax")

    def handle(self, state: AgentState) -> dict[str, Any]:
        update = super().handle(state)
        messages = update.get("messages") or []

        # Stamp the year on a real answer, but not on a refusal: "I do not have
        # that information, as of AY 2027-28" implies the refusal was itself a
        # tax position.
        if messages and str(messages[0].content) != NO_CONTEXT_REPLY:
            body = str(messages[0].content).rstrip()
            update["messages"] = [AIMessage(content=f"{body}\n\n{self._year_note()}")]
        return update

    def trace_detail(self, update: dict[str, Any]) -> str:
        return f"{super().trace_detail(update)}; stated for AY {current_assessment_year()}"

    @staticmethod
    def _year_note() -> str:
        return (
            f"_Current as of FY {current_financial_year()} (AY "
            f"{current_assessment_year()}). Indian tax rules change with each "
            "Budget — check the current position before acting on this._"
        )
