"""Embed text chunks using OpenAI text-embedding-3-small.

Chosen over all-MiniLM-L6-v2 because:
- text-embedding-3-small supports 8,191 tokens (vs 256 for MiniLM — silent truncation)
- Higher quality vectors → better retrieval precision
- Same OpenAI key already used by the LLM layer
- 1,536-dim vectors (or 512 with matryoshka reduction)

Embedding cost estimate for this project:
  253 articles × ~8 chunks × ~400 tokens = ~810,000 tokens
  At $0.02/1M tokens → < $0.02 total. Negligible.
"""

from __future__ import annotations

import os
import time
from typing import Sequence

import openai

# Model dimensions: 1536 by default; can reduce to 512 with `dimensions` param
# for smaller index size with minimal quality loss (matryoshka embeddings).
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512   # reduced from 1536 — saves ~67% storage, <5% quality loss
BATCH_SIZE = 100             # OpenAI allows up to 2048 inputs per call; 100 is safe
RETRY_WAIT = 2               # seconds to wait on rate-limit before retrying


def get_client() -> openai.OpenAI:
    """Return an OpenAI client, failing fast if the key is missing."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Add it to your .env file."
        )
    return openai.OpenAI(api_key=api_key)


def embed_texts(texts: Sequence[str], client: openai.OpenAI | None = None) -> list[list[float]]:
    """Embed a list of strings and return their vectors.

    Batches requests to stay within API limits.
    Retries once on rate-limit errors.

    Args:
        texts: The strings to embed. Each should be under 8,191 tokens.
        client: Optional pre-built OpenAI client (useful for testing with mocks).

    Returns:
        List of float vectors, one per input string, in the same order.
    """
    if not texts:
        return []

    if client is None:
        client = get_client()

    all_vectors: list[list[float]] = []

    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[batch_start: batch_start + BATCH_SIZE])

        for attempt in range(2):  # try twice — once normal, once after rate-limit wait
            try:
                response = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=batch,
                    dimensions=EMBEDDING_DIMENSIONS,
                )
                # Response items are sorted by index, matching our input order
                vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
                all_vectors.extend(vectors)
                break

            except openai.RateLimitError:
                if attempt == 0:
                    print(f"  Rate limit hit — waiting {RETRY_WAIT}s before retry …")
                    time.sleep(RETRY_WAIT)
                else:
                    raise  # second attempt failed, propagate up

    return all_vectors


def embed_single(text: str, client: openai.OpenAI | None = None) -> list[float]:
    """Convenience wrapper for embedding one string."""
    return embed_texts([text], client=client)[0]
