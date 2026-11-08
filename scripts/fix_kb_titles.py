"""Replace placeholder "Chapter N" titles in the knowledge base with real ones.

Why this exists
---------------
`extract_varsity.py` wrote `title: "Chapter 1"` into every article's front matter,
because that is what the PDF heading said. Retrieval then cites sources as
"Chapter 1", which tells a reader nothing and makes a correct, grounded answer
*feel* untrustworthy. Trust is a product requirement (PRD 2.1), so this is a
defect, not cosmetics.

Where the real title comes from
-------------------------------
In the extracted Markdown the chapter's actual title is the first non-empty line
after the `## Chapter N` heading:

    ## Chapter 1

    Introduction to Fundamental Analysis     <-- the real title
    1.1 - Overview
    Fundamental Analysis (FA) is a holistic ...

So: skip the heading, take the next non-empty line, and accept it as a title only
if it looks like one (short, not a sentence). Otherwise fall back to
"<module> - Chapter N", which is still more informative than "Chapter 1".

Idempotent: only rewrites front matter whose title still matches "Chapter <N>".

Usage
-----
    python scripts/fix_kb_titles.py             # apply
    python scripts/fix_kb_titles.py --dry-run   # show what would change
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

KB_DIR = PROJECT_ROOT / "data" / "knowledge_base"

# PDF extraction leaves private-use-area glyphs (ligatures, bullets) in the text.
# They are invisible in most fonts, break Windows console output, and would end up
# inside citation titles, so strip them at the source.
PUA_CHARS = re.compile(r"[-�]")

PLACEHOLDER_TITLE = re.compile(r'^title:\s*"?Chapter\s+(\d+)"?\s*$', re.IGNORECASE)
MODULE_LINE = re.compile(r'^module:\s*"?(.+?)"?\s*$')
CHAPTER_HEADING = re.compile(r"^#{1,6}\s*Chapter\s+\d+\s*$", re.IGNORECASE)

# A line is a plausible title if it is short, has no terminal full stop, and is not
# a numbered section marker like "1.1 - Overview".
SECTION_MARKER = re.compile(r"^\d+\.\d+\s")
MAX_TITLE_LEN = 90


def _clean(text: str) -> str:
    """Strip extraction artefacts and normalise whitespace and dashes."""
    text = PUA_CHARS.sub("", text)
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    return " ".join(text.split()).strip(" -")


def _looks_like_title(line: str) -> bool:
    line = _clean(line)
    if not line or len(line) > MAX_TITLE_LEN:
        return False
    if line.startswith(("#", "-", "*", ">", "|", "!")):
        return False
    if SECTION_MARKER.match(line):
        return False
    if line.endswith((".", ":", ";", ",")):
        return False
    # Needs at least two words; a bare number or stray token is not a title.
    return len(line.split()) >= 2


def derive_title(lines: list[str], module: str, chapter_no: str) -> tuple[str, str]:
    """Return (title, how_it_was_found)."""
    # Find the chapter heading, then the first plausible title line after it.
    start = 0
    for i, line in enumerate(lines):
        if CHAPTER_HEADING.match(line.strip()):
            start = i + 1
            break

    for line in lines[start : start + 8]:
        if _looks_like_title(line):
            return _clean(line), "body"

    fallback = f"{module} - Chapter {chapter_no}" if module else f"Chapter {chapter_no}"
    return fallback, "fallback"


def process(path: Path, *, dry_run: bool) -> tuple[str, str] | None:
    """Rewrite one file's title. Returns (old, new) when changed, else None."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    title_idx = None
    chapter_no = ""
    module = ""
    for i, line in enumerate(lines[:12]):
        match = PLACEHOLDER_TITLE.match(line)
        if match:
            title_idx = i
            chapter_no = match.group(1)
        mod = MODULE_LINE.match(line)
        if mod:
            module = mod.group(1)

    if title_idx is None:
        return None  # already has a real title, or no front matter

    new_title, _source = derive_title(lines, module, chapter_no)
    old_title = f"Chapter {chapter_no}"

    # Escape embedded quotes so the YAML stays valid.
    safe = new_title.replace('"', "'")
    lines[title_idx] = f'title: "{safe}"'

    if not dry_run:
        path.write_text("\n".join(lines), encoding="utf-8")
    return old_title, new_title


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    args = parser.parse_args()

    # Windows consoles default to cp1252 and die on anything outside it.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    files = sorted(KB_DIR.rglob("*.md"))
    if not files:
        print(f"No .md files under {KB_DIR}")
        return 1

    changed = 0
    fallbacks = 0
    for path in files:
        result = process(path, dry_run=args.dry_run)
        if result is None:
            continue
        _old, new = result
        changed += 1
        if new.endswith(tuple(f"Chapter {n}" for n in range(1, 30))):
            fallbacks += 1
        print(f"  {path.parent.name}/{path.name}: {new}")

    verb = "would rename" if args.dry_run else "renamed"
    print(f"\n{verb} {changed} of {len(files)} files ({fallbacks} used the module fallback)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
