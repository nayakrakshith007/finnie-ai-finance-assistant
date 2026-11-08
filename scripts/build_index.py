"""Build the ChromaDB vector index from the knowledge base.

Reads all Markdown articles → chunks → embeds → upserts into Chroma.

Usage:
    python scripts/build_index.py              # skip if index exists
    python scripts/build_index.py --rebuild    # drop and rebuild from scratch

Cost estimate: ~1,841 chunks × 500 tokens × $0.02/1M ≈ $0.02 total.
Run with --rebuild only when articles have changed or chunk size was modified.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.config import load_config  # noqa: E402
from rag.chunker import chunk_directory  # noqa: E402
from rag.embedder import embed_texts, get_client  # noqa: E402
from rag.vector_store import (  # noqa: E402
    add_chunks,
    collection_count,
    delete_collection,
    get_or_create_collection,
)
from rag.vector_store import (  # noqa: E402
    get_client as get_chroma_client,
)
from utils.console import ensure_utf8_stdout  # noqa: E402


def _make_chunk_id(chunk_meta: dict) -> str:
    """Generate a stable, unique ID for each chunk.

    Format: <original_folder>__<file_stem>__<chunk_index>
    Example: stocks__01_chapter-1__3

    Uses the original folder name (not the mapped category) so IDs stay
    unique even when multiple folders remap to the same logical category.
    Stable means the same chunk always gets the same ID across runs,
    so upsert overwrites correctly instead of creating duplicates.
    """
    file_path = Path(chunk_meta["file"])
    folder = file_path.parent.name   # original KB subfolder, not mapped category
    idx = chunk_meta["chunk_index"]
    return f"{folder}__{file_path.stem}__{idx}"


def build(rebuild: bool = False) -> None:
    cfg = load_config()

    chroma_client = get_chroma_client(cfg.resolve(cfg.rag.index_dir))
    collection = get_or_create_collection(chroma_client)

    # ── Guard: skip if already indexed ───────────────────────────────────────
    existing = collection_count(collection)
    if existing > 0 and not rebuild:
        print(f"Index already has {existing} chunks. Use --rebuild to re-index.")
        return

    if rebuild and existing > 0:
        print(f"Dropping existing index ({existing} chunks) …")
        delete_collection(chroma_client)
        collection = get_or_create_collection(chroma_client)

    # ── Step 1: Chunk all articles ────────────────────────────────────────────
    kb_dir = cfg.resolve(cfg.rag.knowledge_base_dir)
    print(f"\nChunking articles from {kb_dir} …")
    if cfg.rag.category_map:
        print(f"  Applying category_map: {dict(cfg.rag.category_map)}")
    t0 = time.perf_counter()
    chunks = chunk_directory(kb_dir, category_map=dict(cfg.rag.category_map))
    print(f"  {len(chunks)} chunks from {kb_dir} in {time.perf_counter() - t0:.1f}s")

    # ── Step 2: Prepare lists for Chroma ─────────────────────────────────────
    ids = [_make_chunk_id(c.metadata) for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [c.metadata for c in chunks]

    # ── Step 3: Embed in batches ──────────────────────────────────────────────
    print(f"\nEmbedding {len(chunks)} chunks with text-embedding-3-small …")
    print("  (this costs ~$0.02 and takes ~30–60s depending on rate limits)")
    t0 = time.perf_counter()
    openai_client = get_client()
    embeddings = embed_texts(documents, client=openai_client)
    elapsed = time.perf_counter() - t0
    print(f"  Done in {elapsed:.1f}s")

    # ── Step 4: Upsert into Chroma ────────────────────────────────────────────
    print(f"\nUpserting {len(chunks)} chunks into ChromaDB …")
    t0 = time.perf_counter()
    add_chunks(
        collection=collection,
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    print(f"  Done in {time.perf_counter() - t0:.1f}s")

    # ── Summary ───────────────────────────────────────────────────────────────
    final_count = collection_count(collection)
    print(f"\nIndex built. Collection '{collection.name}' now has {final_count} chunks.")
    print(f"Persisted to: {cfg.resolve(cfg.rag.index_dir)}")


def main() -> None:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Build the Finnie ChromaDB index")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop existing index and rebuild from scratch",
    )
    args = parser.parse_args()
    build(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
