"""Extract Zerodha Varsity PDF chapters into Markdown knowledge-base articles.

Usage:
    python scripts/extract_varsity.py <pdf_path> <category> [--module <name>]

Example:
    python scripts/extract_varsity.py downloads/module1_stock_markets.pdf stocks --module "Stock Markets"
    python scripts/extract_varsity.py downloads/module11_personal_finance.pdf retirement --module "Personal Finance"

Each chapter becomes one .md file in data/knowledge_base/<category>/.
Front matter is generated automatically; review and adjust tags manually.

Categories: basics stocks bonds etfs mutual-funds risk diversification retirement tax behavioural
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _slug(text: str) -> str:
    """Convert a heading to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text)[:60]


def _infer_tags(text: str, category: str) -> list[str]:
    """Return a rough tag list from keywords found in the text."""
    keyword_map = {
        "compound interest": ["compound-interest", "time-value"],
        "sip": ["sip", "systematic-investment"],
        "expense ratio": ["expense-ratio", "fees"],
        "diversif": ["diversification"],
        "risk": ["risk"],
        "nifty": ["nifty", "index"],
        "sensex": ["sensex", "index"],
        "mutual fund": ["mutual-funds"],
        "etf": ["etf"],
        "bond": ["bonds", "fixed-income"],
        "ppf": ["ppf", "retirement", "tax-saving"],
        "nps": ["nps", "retirement"],
        "epf": ["epf", "retirement"],
        "elss": ["elss", "tax-saving", "mutual-funds"],
        "ltcg": ["ltcg", "capital-gains", "tax"],
        "stcg": ["stcg", "capital-gains", "tax"],
        "volatility": ["volatility", "risk"],
        "portfolio": ["portfolio"],
        "stock": ["stocks", "equity"],
        "sebi": ["sebi", "regulation"],
    }
    tags = {category}
    lower = text.lower()
    for keyword, kw_tags in keyword_map.items():
        if keyword in lower:
            tags.update(kw_tags)
    return sorted(tags)[:8]


def _split_into_chapters(pages: list[str]) -> list[tuple[str, str]]:
    """Split raw page text into (chapter_title, body) pairs.

    Zerodha Varsity PDFs use 'Chapter N' headings or ALL-CAPS section titles.
    Returns list of (title, full_body_text).
    """
    full_text = "\n".join(pages)

    # Try splitting on "Chapter N" pattern first (most Varsity modules)
    chapter_pattern = re.compile(
        r"(?:^|\n)(Chapter\s+\d+[^\n]*|CHAPTER\s+\d+[^\n]*)", re.IGNORECASE
    )
    splits = chapter_pattern.split(full_text)

    if len(splits) > 2:
        chapters = []
        # splits = [pre_text, title1, body1, title2, body2, ...]
        for i in range(1, len(splits) - 1, 2):
            title = splits[i].strip()
            body = splits[i + 1].strip() if i + 1 < len(splits) else ""
            if len(body) > 200:  # skip tiny stubs
                chapters.append((title, body))
        if chapters:
            return chapters

    # Fallback: split on ALL CAPS lines (section headings in some modules)
    lines = full_text.split("\n")
    chapters = []
    current_title = "Introduction"
    current_body: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Detect heading: 4-80 chars, mostly uppercase, no sentence-ending punctuation
        if (
            4 <= len(stripped) <= 80
            and stripped == stripped.upper()
            and not stripped.endswith(".")
            and re.search(r"[A-Z]", stripped)
            and not re.match(r"^\d+$", stripped)
        ):
            if current_body and len("\n".join(current_body)) > 200:
                chapters.append((current_title, "\n".join(current_body)))
            current_title = stripped.title()
            current_body = []
        else:
            current_body.append(line)

    if current_body and len("\n".join(current_body)) > 200:
        chapters.append((current_title, "\n".join(current_body)))

    return chapters if chapters else [("Full Content", full_text)]


def _clean_body(raw: str) -> str:
    """Remove page numbers, headers, excessive whitespace from extracted text."""
    lines = raw.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip page number lines like "12", "Page 12", "12 |"
        if re.match(r"^(Page\s*)?\d+(\s*\|.*)?$", stripped):
            continue
        # Skip very short repeated header/footer lines
        if len(stripped) < 3:
            continue
        cleaned.append(line)
    # Collapse 3+ blank lines into 2
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _to_markdown(title: str, body: str, category: str, module: str, index: int) -> str:
    """Wrap cleaned body in a Markdown article with YAML front matter."""
    tags = _infer_tags(body, category)
    tags_yaml = "\n".join(f'  - "{t}"' for t in tags)

    # Convert obvious paragraph breaks to Markdown paragraphs
    # and add a ## heading for the first real section
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    md_body = "\n\n".join(paragraphs)

    return f"""---
title: "{title}"
category: "{category}"
source: "Zerodha Varsity"
module: "{module}"
tags:
{tags_yaml}
---

## {title}

{md_body}
"""


def extract(pdf_path: Path, category: str, module: str) -> None:
    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber not installed. Run: pip install pdfplumber")
        sys.exit(1)

    out_dir = PROJECT_ROOT / "data" / "knowledge_base" / category
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Opening {pdf_path.name} ...")
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            pages.append(text)
            if i % 20 == 0:
                print(f"  read {i}/{total} pages")

    print(f"Splitting into chapters ...")
    chapters = _split_into_chapters(pages)
    print(f"Found {len(chapters)} chapters")

    written = 0
    for idx, (title, body) in enumerate(chapters, 1):
        body = _clean_body(body)
        if len(body) < 150:
            print(f"  skip (too short): {title[:50]}")
            continue

        md = _to_markdown(title, body, category, module, idx)
        slug = _slug(title) or f"chapter-{idx:02d}"
        filename = f"{idx:02d}_{slug}.md"
        out_path = out_dir / filename
        out_path.write_text(md, encoding="utf-8")
        print(f"  wrote {filename}")
        written += 1

    print(f"\nDone — {written} articles saved to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Zerodha Varsity PDF to Markdown articles")
    parser.add_argument("pdf", help="Path to the Varsity PDF file")
    parser.add_argument("category", help="Knowledge base category (e.g. stocks, basics, retirement)")
    parser.add_argument("--module", default="Zerodha Varsity", help="Module name for front matter")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: file not found — {pdf_path}")
        sys.exit(1)

    extract(pdf_path, args.category, args.module)


if __name__ == "__main__":
    main()
