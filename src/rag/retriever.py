"""Retrieve relevant chunks from ChromaDB for a user query.

The retriever is the bridge between the vector store and the agent:
  1. Embed the user's question
  2. Run similarity search (optionally filtered by category)
  3. Drop results below the relevance threshold
  4. Return LangChain Document objects so the agent can use them directly

Returns LangChain Documents (not raw dicts) because LangGraph agents expect
the standard Document interface: doc.page_content and doc.metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from langchain_core.documents import Document

from core.config import load_config
from rag.embedder import embed_single, get_client as get_openai_client
from rag.vector_store import get_client, get_or_create_collection, mmr_search, similarity_search


def build_retriever(persist_dir: str | Path | None = None) -> "FinnieRetriever":
    """Construct a FinnieRetriever from config.

    Args:
        persist_dir: Override for the Chroma persist path.
                     Defaults to config.yaml → rag.index_dir.
    """
    cfg = load_config()
    resolved_dir = persist_dir or cfg.rag.index_dir

    chroma_client = get_client(resolved_dir)
    collection = get_or_create_collection(chroma_client)
    openai_client = get_openai_client()

    return FinnieRetriever(
        collection=collection,
        openai_client=openai_client,
        top_k=cfg.rag.top_k,
        relevance_threshold=cfg.rag.relevance_threshold,
        use_mmr=cfg.rag.use_mmr,
        mmr_lambda=cfg.rag.mmr_lambda,
    )


class FinnieRetriever:
    """Retrieve knowledge-base chunks relevant to a user query.

    Usage:
        retriever = build_retriever()
        docs = retriever.get_relevant_documents("what is LTCG")
        docs = retriever.get_relevant_documents("what is LTCG", category="tax")
    """

    def __init__(
        self,
        collection: chromadb.Collection,
        openai_client: Any,
        top_k: int = 4,
        relevance_threshold: float = 0.35,
        use_mmr: bool = True,
        mmr_lambda: float = 0.5,
    ) -> None:
        self.collection = collection
        self.openai_client = openai_client
        self.top_k = top_k
        self.relevance_threshold = relevance_threshold
        self.use_mmr = use_mmr
        self.mmr_lambda = mmr_lambda

    def get_relevant_documents(
        self,
        query: str,
        category: str | None = None,
        top_k: int | None = None,
    ) -> list[Document]:
        """Return the most relevant chunks for query as LangChain Documents.

        Args:
            query:    The user's question in plain text.
            category: Optional category filter (e.g. "tax", "stocks").
                      Pass None to search the full knowledge base.
            top_k:    Override the default number of results.

        Returns:
            List of Document objects, filtered by relevance_threshold,
            sorted best-first (lowest cosine distance first).
            Returns empty list if nothing passes the threshold — the agent
            should respond "I don't have information on that" rather than
            guessing from irrelevant context.
        """
        k = top_k or self.top_k

        # Step 1 — embed the query using the same model as the index
        query_vector = embed_single(query, client=self.openai_client)

        # Step 2 — build optional metadata filter
        where: dict[str, Any] | None = None
        if category:
            where = {"category": category}

        # Step 3 — run similarity search (or MMR for diverse results)
        if self.use_mmr:
            raw_results = mmr_search(
                collection=self.collection,
                query_embedding=query_vector,
                top_k=k,
                lambda_mult=self.mmr_lambda,
                where=where,
            )
        else:
            raw_results = similarity_search(
                collection=self.collection,
                query_embedding=query_vector,
                top_k=k,
                where=where,
            )

        # Step 4 — filter by relevance threshold, de-duplicate by text, convert to Documents
        docs: list[Document] = []
        seen: set[int] = set()  # hash of chunk text to catch cross-category duplicates
        for result in raw_results:
            if result["distance"] > self.relevance_threshold:
                continue
            text_hash = hash(result["text"])
            if text_hash in seen:
                continue
            seen.add(text_hash)
            docs.append(
                Document(
                    page_content=result["text"],
                    metadata={
                        **result["metadata"],
                        "distance": round(result["distance"], 4),
                    },
                )
            )

        return docs

    def get_relevant_documents_with_scores(
        self,
        query: str,
        category: str | None = None,
    ) -> list[tuple[Document, float]]:
        """Same as get_relevant_documents but also returns the distance score.

        Useful for debugging retrieval quality and building the MRR evaluator.
        """
        query_vector = embed_single(query, client=self.openai_client)
        where = {"category": category} if category else None

        raw_results = similarity_search(
            collection=self.collection,
            query_embedding=query_vector,
            top_k=self.top_k,
            where=where,
        )

        return [
            (
                Document(page_content=r["text"], metadata=r["metadata"]),
                round(r["distance"], 4),
            )
            for r in raw_results
        ]
