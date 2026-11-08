"""Finance Q&A Agent — grounded answers from the knowledge base (PRD FR-010).

What it adds over calling `RAGChain.ask()` directly
---------------------------------------------------
1. **Adaptation.** The graph speaks `AgentState`; the chain speaks strings. The
   translation lives here instead of being inlined at every call site.
2. **State contribution.** It writes `retrieved_docs`, so the compliance node, the
   UI citation panel and any later agent can see what this turn was grounded in.
3. **Economics.** With no retrieved context it refuses *without* calling the LLM.
   `RAGChain.ask()` would still send a completion over an empty context block and
   bill for the privilege.

Why it does not reuse `RAGChain`
--------------------------------
The chain retrieves and generates in one call, returning a string. This agent needs
the documents *and* the answer, needs to branch before generating when retrieval is
empty, and needs to record distances in its trace. Composing those out of
`ask_with_sources()` would mean retrieving twice or re-deriving what the chain
already discarded, so it uses the retriever and prompt directly — the same two
pieces the chain is built from.
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.base import BaseAgent
from core.logging_setup import get_logger
from rag.prompt import RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE, format_context
from rag.retriever import build_retriever
from workflow.state import AgentState

logger = get_logger(__name__)

# Matches the refusal wording the system prompt instructs the model to use, so a
# refusal reads identically whether it came from the model or from this short
# circuit. The user should not be able to tell which path produced it.
NO_CONTEXT_REPLY = "I don't have enough information in my knowledge base to answer that."


class FinanceQAAgent(BaseAgent):
    """Answers general financial-education questions from the knowledge base."""

    name = "finance_qa"
    description = (
        "Answers general questions about personal finance concepts, instruments and "
        "Indian tax rules using the curated knowledge base — what a SIP is, how PPF "
        "works, capital gains treatment, insurance basics, budgeting. Use this for "
        "anything conceptual or definitional. Do NOT use it for live prices, a user's "
        "own portfolio, or goal projections."
    )

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        retriever: Any | None = None,
        category: str | None = None,
    ) -> None:
        """
        Args:
            llm: injected for tests; built lazily from config otherwise.
            retriever: injected for tests; built lazily from config otherwise.
            category: optional hard filter. Left None in production — the retriever
                should find the right category unaided, and supplying one as both
                input and scoring criterion is the tautology the eval avoids.
        """
        super().__init__(llm=llm)
        self._retriever = retriever
        self.category = category

    @property
    def retriever(self) -> Any:
        """Built on first use, so constructing the agent needs no index or API key."""
        if self._retriever is None:
            self._retriever = build_retriever()
        return self._retriever

    # ── the work ──────────────────────────────────────────────────────────────

    def handle(self, state: AgentState) -> dict[str, Any]:
        question = self._latest_question(state)
        docs = self.retriever.get_relevant_documents(question, category=self.category)
        sources = [self._as_source(d) for d in docs]

        if not docs:
            # Refuse before generating. Nothing in an empty context block can ground
            # an answer, so a completion here would be an invitation to hallucinate
            # and a charge for the privilege.
            logger.info("No context retrieved for %r; refusing without an LLM call", question[:60])
            return {
                "messages": [AIMessage(content=NO_CONTEXT_REPLY)],
                "retrieved_docs": [],
            }

        messages = [
            SystemMessage(content=RAG_SYSTEM_PROMPT.format(context=format_context(docs))),
            HumanMessage(content=RAG_USER_TEMPLATE.format(question=question)),
        ]
        response = self.llm.invoke(messages)

        return {
            "messages": [AIMessage(content=response.content)],
            "retrieved_docs": sources,
        }

    def trace_detail(self, update: dict[str, Any]) -> str:
        sources = update.get("retrieved_docs") or []
        if not sources:
            return "no context retrieved; refused without calling the LLM"
        best = min(s["distance"] for s in sources if s["distance"] is not None)
        return f"{len(sources)} docs retrieved, best distance {best:.2f}"

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _as_source(d: Document) -> dict[str, Any]:
        """Flatten a Document into the citation shape the UI and trace consume."""
        meta = d.metadata
        return {
            "title": meta.get("title", "untitled"),
            "section": meta.get("section", ""),
            "category": meta.get("category", "unknown"),
            "source": meta.get("source", "unknown"),
            "url": meta.get("url", ""),
            "distance": meta.get("distance"),
        }
