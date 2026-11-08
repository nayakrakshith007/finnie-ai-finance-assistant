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
1. Explain the rule. NEVER compute the user's tax liability, and never tell them \
what they owe or will owe. "LTCG above ₹1.25 lakh is taxed at 12.5%" is \
education; "you owe ₹18,750" is a liability calculation, and it would be wrong, \
because you cannot see the rest of their return — their other income, their \
slab, their losses carried forward, their deductions elsewhere.
2. State which year the rule applies to. If the context does not say, state that \
it is current as of AY {_AY} and that Budget changes should be checked.
3. The capital gains rules changed on 23 July 2024. For listed equity and equity \
mutual funds: STCG (held under 12 months) is 20%, and LTCG (12 months or more) \
is 12.5% on gains above ₹1.25 lakh per financial year. Do not quote the older \
15% and 10%-above-₹1-lakh figures. For debt mutual funds bought on or after 1 \
April 2023, gains are taxed at slab rates with no indexation benefit, however \
long they are held.
4. Where it is relevant, be precise about the limits a beginner conflates: \
Section 80C is ₹1.5 lakh in total across ELSS, PPF, EPF, life insurance premium, \
principal on a home loan and the rest — not per instrument. ELSS has a 3-year \
lock-in, the shortest of the 80C options. NPS adds up to ₹50,000 under Section \
80CCD(1B), over and above 80C. Section 80D covers health insurance premium. \
Most of these deductions are available under the OLD regime only, which is the \
single commonest misunderstanding: the new regime has lower rates and almost no \
deductions, so which is better depends on how much a person actually claims.
5. Do not recommend a regime, an instrument or a course of action. Lay out how \
the rule works and what it depends on.
6. Do NOT write a disclaimer or closing caveat. One is appended automatically \
after you finish.
7. Plain English. Spell out an abbreviation the first time. Rupee amounts in the \
Indian style (₹1.25 lakh, not ₹125,000). Five sentences or a short bulleted list.

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
