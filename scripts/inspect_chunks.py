"""Preview chunks produced by the chunker for one article.

Usage:
    python scripts/inspect_chunks.py <markdown_file>

Example:
    python scripts/inspect_chunks.py data/knowledge_base/tax/01_chapter-1.md

Writes a human-readable report to data/chunk_preview.txt so you can open it
in VS Code and see exactly what the retriever will receive.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rag.chunker import chunk_file  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_chunks.py <markdown_file>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    chunks = chunk_file(path)

    out_path = PROJECT_ROOT / "data" / "chunk_preview.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"SOURCE FILE: {path}")
    lines.append(f"TOTAL CHUNKS: {len(chunks)}")
    lines.append("=" * 70)

    for i, chunk in enumerate(chunks, 1):
        lines.append(f"\n{'─' * 70}")
        lines.append(f"CHUNK {i} of {len(chunks)}")
        lines.append(f"Section  : {chunk.metadata['section']}")
        lines.append(f"Category : {chunk.metadata['category']}")
        lines.append(f"Source   : {chunk.metadata['source']}")
        lines.append(f"Tags     : {chunk.metadata['tags']}")
        lines.append(f"Chars    : {chunk.char_count}")
        lines.append(f"~Tokens  : {chunk.char_count // 4}")
        lines.append("")
        lines.append("TEXT:")
        lines.append(chunk.text[:600] + ("..." if len(chunk.text) > 600 else ""))

    output = "\n".join(lines)
    out_path.write_text(output, encoding="utf-8")

    print(f"Wrote {len(chunks)} chunks → {out_path}")
    print("\nQuick summary:")
    for i, c in enumerate(chunks, 1):
        print(f"  Chunk {i:02d} | ~{c.char_count // 4:4d} tokens | {c.metadata['section'][:50]}")


if __name__ == "__main__":
    main()
