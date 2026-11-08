"""RAG chain — the complete Retrieve → Prompt → Generate pipeline.

This is the public interface the LangGraph agents will call.
They don't need to know about ChromaDB, embeddings, or prompt templates —
they just call ask() with a question and get a string answer back.

Flow:
    ask(question, category)
        │
        ├─ retriever.get_relevant_documents(question, category)
        │       returns list[Document]
        │
        ├─ format_context(docs)
        │       returns context string
        │
        ├─ build RAG prompt  [system: rules + context]  [user: question]
        │
        └─ llm.invoke(messages)
                returns answer string
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import build_llm
from rag.prompt import RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE, format_context
from rag.retriever import FinnieRetriever, build_retriever


def build_rag_chain(retriever: FinnieRetriever | None = None) -> "RAGChain":
    """Construct a RAGChain from config.

    Args:
        retriever: Pass an existing retriever to reuse its Chroma client.
                   Defaults to building a fresh one from config.
    """
    resolved_retriever = retriever or build_retriever()
    llm = build_llm()
    return RAGChain(retriever=resolved_retriever, llm=llm)


class RAGChain:
    """Retrieve-then-generate pipeline.

    Usage:
        chain = build_rag_chain()
        answer = chain.ask("what is LTCG tax on equity?", category="tax")
        answer = chain.ask("how does SIP work?")   # searches full KB
    """

    def __init__(self, retriever: FinnieRetriever, llm: object) -> None:
        self.retriever = retriever
        self.llm = llm

    def ask(
        self,
        question: str,
        category: str | None = None,
    ) -> str:
        """Answer a question using retrieved context.

        Args:
            question: The user's question in plain text.
            category: Optional category filter passed to the retriever
                      (e.g. "tax", "stocks"). None searches the full KB.

        Returns:
            Answer string from the LLM, grounded in retrieved context.
            Includes the educational disclaimer at the end.
        """
        # Step 1 — retrieve relevant chunks
        docs = self.retriever.get_relevant_documents(question, category=category)

        # Step 2 — format chunks into a context string
        context = format_context(docs)

        # Step 3 — build the prompt
        system_text = RAG_SYSTEM_PROMPT.format(context=context)
        user_text = RAG_USER_TEMPLATE.format(question=question)

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content=user_text),
        ]

        # Step 4 — call the LLM
        response = self.llm.invoke(messages)

        # LangChain LLMs return an AIMessage; .content is the string
        return response.content

    def ask_with_sources(
        self,
        question: str,
        category: str | None = None,
    ) -> dict:
        """Same as ask() but also returns the retrieved source chunks.

        Useful for the UI to show "Sources used" alongside the answer.

        Returns:
            {
                "answer": str,
                "sources": list[dict]  # {title, section, category, distance}
            }
        """
        docs = self.retriever.get_relevant_documents(question, category=category)
        context = format_context(docs)

        system_text = RAG_SYSTEM_PROMPT.format(context=context)
        user_text = RAG_USER_TEMPLATE.format(question=question)

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content=user_text),
        ]

        response = self.llm.invoke(messages)

        sources = [
            {
                "title": d.metadata.get("title", "unknown"),
                "section": d.metadata.get("section", "unknown"),
                "category": d.metadata.get("category", "unknown"),
                "distance": d.metadata.get("distance", None),
            }
            for d in docs
        ]

        return {"answer": response.content, "sources": sources}
