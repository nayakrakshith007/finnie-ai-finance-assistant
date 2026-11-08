"""Split knowledge-base Markdown articles into retrieval-ready chunks.

Each article has YAML front matter + sections separated by ## headings.
Strategy: heading-based split first, then cap any oversized section at
MAX_TOKENS with a sliding window so context is never lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.logging_setup import get_logger

logger = get_logger(__name__)

# Defaults — overridden at runtime by values from config.yaml via chunk_directory()
MAX_TOKENS = 500
OVERLAP_TOKENS = 50


@dataclass
class Chunk:
    text: str                    # the actual text to embed
    metadata: dict[str, Any]     # title, category, source, module, tags, chunk_index
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


def _rough_tokens(text: str) -> int:
    """Estimate token count — 1 token ≈ 4 characters (good enough for sizing)."""
    return len(text) // 4


def _parse_front_matter(content: str) -> tuple[dict[str, Any], str]:
    """Split YAML front matter from Markdown body.

    Returns (metadata_dict, body_text).
    Raises ValueError if front matter is missing or malformed.
    """
    if not content.startswith("---"):
        raise ValueError("Missing YAML front matter (file must start with ---)")

    # Find the closing ---
    end = content.find("\n---", 3)
    if end == -1:
        raise ValueError("YAML front matter not closed with ---")

    raw_yaml = content[3:end].strip()
    body = content[end + 4:].strip()  # skip the closing ---\n

    meta = yaml.safe_load(raw_yaml) or {}
    return meta, body


def _split_by_headings(body: str) -> list[tuple[str, str]]:
    """Split Markdown body on ## headings.

    Returns list of (heading_text, section_body) pairs.
    Text before the first heading becomes an 'Overview' section.
    """
    # Match lines starting with ## (but not ###)
    pattern = re.compile(r"^(## .+)$", re.MULTILINE)
    parts = pattern.split(body)

    sections: list[tuple[str, str]] = []

    # parts alternates: [pre_text, heading1, body1, heading2, body2, ...]
    if parts[0].strip():
        sections.append(("Overview", parts[0].strip()))

    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].lstrip("# ").strip()
        section_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if section_body:
            sections.append((heading, section_body))

    return sections if sections else [("Full Content", body)]


def _sub_split(heading: str, text: str, overlap: int) -> list[str]:
    """Split a large section into overlapping windows of MAX_TOKENS.

    Each sub-chunk starts with the heading so it stays self-contained.
    """
    words = text.split()
    words_per_chunk = MAX_TOKENS * 4 // 5  # convert tokens → approx word count
    step = words_per_chunk - overlap

    chunks: list[str] = []
    start = 0
    while start < len(words):
        window = words[start: start + words_per_chunk]
        chunk_text = f"{heading}\n\n" + " ".join(window)
        chunks.append(chunk_text)
        start += step

    return chunks


def chunk_file(path: Path, category_map: dict[str, str] | None = None) -> list[Chunk]:
    """Parse one Markdown article and return its chunks.

    Each chunk carries the article's full metadata so the retriever
    can cite source, category, and module without a separate lookup.
    """
    content = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(content)

    raw_category = meta.get("category", "unknown")
    mapped_category = (category_map or {}).get(raw_category, raw_category)

    base_meta = {
        "title": meta.get("title", path.stem),
        "category": mapped_category,
        "source": meta.get("source", "unknown"),
        "module": meta.get("module", ""),
        "tags": ", ".join(meta.get("tags", [])),  # Chroma needs strings, not lists
        # url lets a citation link out to the authority it came from; date_retrieved
        # matters because tax rules change with every Finance Act. Both default to ""
        # so older articles without them still index cleanly.
        "url": meta.get("url", ""),
        "date_retrieved": str(meta.get("date_retrieved", "")),
        "file": str(path),
    }

    sections = _split_by_headings(body)
    chunks: list[Chunk] = []

    for section_heading, section_body in sections:
        # Prepend heading so each chunk is self-contained when retrieved
        full_text = f"{section_heading}\n\n{section_body}"

        if _rough_tokens(full_text) <= MAX_TOKENS:
            # Small enough — emit as one chunk
            chunk_meta = {**base_meta, "section": section_heading, "chunk_index": len(chunks)}
            chunks.append(Chunk(text=full_text, metadata=chunk_meta))
        else:
            # Too large — sub-split with overlap
            sub_chunks = _sub_split(section_heading, section_body, OVERLAP_TOKENS)
            for sub in sub_chunks:
                chunk_meta = {**base_meta, "section": section_heading, "chunk_index": len(chunks)}
                chunks.append(Chunk(text=sub, metadata=chunk_meta))

    return chunks


def chunk_directory(kb_dir: Path, category_map: dict[str, str] | None = None) -> list[Chunk]:
    """Chunk every .md file under kb_dir (recurses into category subdirs)."""
    all_chunks: list[Chunk] = []
    files = sorted(kb_dir.rglob("*.md"))
    for path in files:
        try:
            all_chunks.extend(chunk_file(path, category_map=category_map))
        except (ValueError, yaml.YAMLError) as exc:
            logger.warning("Skipped %s during chunking: %s", path.name, exc)
    return all_chunks
