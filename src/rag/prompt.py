"""RAG prompt templates for Finnie.

Two templates:
  RAG_SYSTEM_PROMPT  — injected as the system message; contains the retrieved
                       context and strict instructions to stay grounded.
  RAG_USER_TEMPLATE  — wraps the user's question (simple pass-through for now,
                       but having a template lets us add chain-of-thought or
                       formatting instructions later without touching chain.py).

Design rule: the LLM must only use the supplied context. If the context does
not contain the answer, Finnie says so explicitly rather than hallucinating.
This matters for a finance assistant — a confident wrong answer about tax or
returns could mislead the user.
"""

from __future__ import annotations

from langchain_core.documents import Document

# ── Templates ─────────────────────────────────────────────────────────────────

# {context} is replaced at runtime with the formatted retrieved chunks.
RAG_SYSTEM_PROMPT = """\
You are Finnie, an AI financial literacy assistant. Your job is to educate \
users about personal finance using plain, accurate language.

RULES:
1. Answer using ONLY the context provided below. Do not use outside knowledge.
2. If the context does not contain enough information, say:
   "I don't have enough information in my knowledge base to answer that."
3. Never recommend a specific trade, stock, or fund.
4. If multiple context chunks contradict each other on tax rates or regulations,
   prefer the chunk that explicitly mentions a later budget (e.g. "Budget 2024"
   beats "Budget 2018"), or the one marked as an amendment/update. Do NOT
   average contradictory rates — state the most recent figure and note that an
   earlier source said otherwise.
5. Always end your response with this disclaimer:
   "⚠️ This is educational information, not financial advice. \
Consult a licensed financial adviser before making any investment decision."

CONTEXT:
{context}
"""

# {question} is replaced with the user's raw query.
RAG_USER_TEMPLATE = "{question}"

# ── Context formatter ──────────────────────────────────────────────────────────

def format_context(docs: list[Document]) -> str:
    """Convert a list of retrieved Documents into a single context string.

    Each chunk is numbered and labelled with its source so the LLM can cite it.

    Example output:
        [1] Source: Zerodha Varsity | Category: mutual-funds | Section: CHAPTER 8
        SIP stands for Systematic Investment Plan...

        [2] Source: Zerodha Varsity | Category: tax | Section: CHAPTER 4
        Long-term capital gains on equity...
    """
    if not docs:
        return "No relevant context found."

    parts: list[str] = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata
        label = (
            f"[{i}] Source: {meta.get('source', 'unknown')}"
            f" | Category: {meta.get('category', 'unknown')}"
            f" | Section: {meta.get('section', 'unknown')}"
        )
        parts.append(f"{label}\n{doc.page_content}")

    return "\n\n".join(parts)
