"""ChromaDB vector store — persist, load, and query embedded chunks.

Responsibilities:
  - Create or load a persistent Chroma collection
  - Add chunks (text + metadata + pre-computed vectors)
  - Run similarity search with optional metadata filter
  - Delete and rebuild the collection cleanly

Collection name: "finnie_kb"
Persist directory: read from config.yaml → rag.index_dir
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb import Collection

from core.logging_setup import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "finnie_kb"


# ── Client / collection helpers ───────────────────────────────────────────────

def get_client(persist_dir: str | Path) -> chromadb.PersistentClient:
    """Return a Chroma client backed by a local directory.

    PersistentClient writes to disk so the index survives restarts.
    Call this once and reuse the client — opening many clients on the
    same directory causes file-lock conflicts.
    """
    return chromadb.PersistentClient(path=str(persist_dir))


def get_or_create_collection(client: chromadb.PersistentClient) -> Collection:
    """Return the collection, creating it if it does not exist yet.

    We pass embedding_function=None because we supply our own vectors
    (from embedder.py). Chroma's default is to embed text itself, which
    we don't want — we control the model.
    """
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  # cosine similarity, not L2
    )


# ── Write ─────────────────────────────────────────────────────────────────────

def add_chunks(
    collection: Collection,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
    batch_size: int = 500,
) -> None:
    """Upsert chunks into the collection in batches.

    Uses upsert (not add) so re-indexing is idempotent — running
    build_index.py twice won't create duplicates.

    Args:
        ids:        Unique string ID per chunk (e.g. "stocks_01_chapter-1_0")
        embeddings: Pre-computed vectors from embedder.py
        documents:  Raw chunk text (stored for retrieval + display)
        metadatas:  Dict per chunk with category, source, tags, etc.
        batch_size: Chroma recommends ≤ 5,000 per call; 500 is safe.
    """
    total = len(ids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        logger.debug("Upserted %d/%d chunks", end, total)


# ── Read ──────────────────────────────────────────────────────────────────────

def similarity_search(
    collection: Collection,
    query_embedding: list[float],
    top_k: int = 4,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return the top_k most similar chunks to query_embedding.

    Args:
        query_embedding: Vector for the user's question (from embedder.py)
        top_k:           Number of results to return
        where:           Optional Chroma metadata filter, e.g.
                         {"category": "tax"} or
                         {"category": {"$in": ["tax", "stocks"]}}

    Returns:
        List of dicts, each with keys: id, text, metadata, distance
        Sorted by distance ascending (0 = identical, 2 = opposite).
    """
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    # Chroma returns lists-of-lists (one inner list per query embedding).
    # We always send one query at a time, so we unpack index 0.
    output = []
    for i, doc_id in enumerate(results["ids"][0]):
        output.append({
            "id": doc_id,
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return output


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity between two vectors (range –1 to 1)."""
    # strict=True: mismatched vector lengths mean an index built with a different
    # embedding model or dimension. Fail loudly rather than silently truncating to
    # the shorter vector and returning a plausible-looking wrong similarity.
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def mmr_search(
    collection: Collection,
    query_embedding: list[float],
    top_k: int = 4,
    fetch_k: int | None = None,
    lambda_mult: float = 0.5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """MMR (Maximal Marginal Relevance) search for diverse results.

    Plain similarity_search can return several chunks from the same section.
    MMR fixes this by greedily selecting results that are relevant to the query
    but dissimilar to what has already been selected.

    Score formula (per candidate at each step):
        score = λ * relevance(candidate, query)
                - (1-λ) * max_similarity(candidate, already_selected)

    Args:
        query_embedding: Vector for the user's question (from embedder.py)
        top_k:           Number of diverse results to return
        fetch_k:         Candidate pool size before MMR re-ranking.
                         Default: top_k * 3 (more candidates → better diversity)
        lambda_mult:     Balance knob. 1.0 = pure relevance (= similarity_search).
                         0.0 = pure diversity. 0.5 = balanced (default).
        where:           Optional Chroma metadata filter

    Returns:
        Same format as similarity_search — list of {id, text, metadata, distance}.
        Ordered by MMR selection (best first).
    """
    _fetch_k = fetch_k if fetch_k is not None else top_k * 3

    # Step 1 — fetch a larger candidate pool with embeddings so we can compute
    # inter-candidate similarity ourselves
    kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": _fetch_k,
        "include": ["documents", "metadatas", "distances", "embeddings"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    ids = results["ids"][0]
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]
    embeddings = results["embeddings"][0]

    if not ids:
        return []

    # Chroma uses cosine distance (0 = identical, 2 = opposite).
    # Convert to relevance score (1 = identical, –1 = opposite).
    relevance = [1.0 - d for d in distances]

    # Step 2 — greedy MMR selection
    selected: list[int] = []
    remaining = list(range(len(ids)))

    while len(selected) < top_k and remaining:
        if not selected:
            # First pick is always the highest-relevance candidate
            best = max(remaining, key=lambda i: relevance[i])
        else:
            best = None
            best_score = float("-inf")
            for i in remaining:
                max_sim = max(
                    _cosine_similarity(embeddings[i], embeddings[j])
                    for j in selected
                )
                score = lambda_mult * relevance[i] - (1 - lambda_mult) * max_sim
                if score > best_score:
                    best_score = score
                    best = i

        selected.append(best)
        remaining.remove(best)

    # Step 3 — build output in MMR selection order
    return [
        {
            "id": ids[i],
            "text": docs[i],
            "metadata": metas[i],
            "distance": distances[i],
        }
        for i in selected
    ]


# ── Maintenance ───────────────────────────────────────────────────────────────

def delete_collection(client: chromadb.PersistentClient) -> None:
    """Drop the collection so build_index.py can start fresh.

    Safe to call even if the collection does not exist.
    """
    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info("Deleted collection '%s'", COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - Chroma raises bare exceptions for "not found"
        logger.debug("Collection '%s' did not exist; nothing to delete", COLLECTION_NAME)


def collection_count(collection: Collection) -> int:
    """Return number of chunks currently in the collection."""
    return collection.count()
