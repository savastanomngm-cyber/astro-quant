#!/usr/bin/env python3
"""
PDF PAGE-BY-PAGE READER — AI Knowledge Extraction
====================================================
Reads PDFs page by page, extracts knowledge points, generates summaries.
Inspired by echohive42/AI-reads-books-page-by-page but self-contained.

Usage:
    python3 pdf_reader.py /path/to/book.pdf

Requires:  pip install pymupdf

No OpenAI needed — uses local extraction via PyMuPDF.
For AI summarization, provides the extracted text ready for LLM prompting.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ====================================================================
# PDF EXTRACTION (PyMuPDF — no API keys needed)
# ====================================================================

def extract_pages(pdf_path: str, start: int = 0, end: Optional[int] = None) -> list[dict]:
    """
    Extract text page by page from a PDF.

    Returns list of dicts: {page_num, text, char_count, has_content}
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("Install PyMuPDF: pip install pymupdf")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    pages = []

    if end is None:
        end = len(doc)

    for i in range(start, min(end, len(doc))):
        page = doc[i]
        text = page.get_text().strip()

        # Skip clearly empty/near-empty pages
        has_content = len(text) > 100 and not _is_skip_page(text)

        pages.append({
            "page_num": i + 1,
            "text": text,
            "char_count": len(text),
            "has_content": has_content,
        })

    doc.close()
    return pages


def _is_skip_page(text: str) -> bool:
    """Heuristic to detect TOC, index, blank pages."""
    lower = text.lower()[:200]
    skip_markers = [
        "table of contents", "contents", "index", "bibliography",
        "acknowledgments", "acknowledgements", "references",
    ]
    return any(m in lower for m in skip_markers)


# ====================================================================
# KNOWLEDGE EXTRACTION (rule-based, no LLM)
# ====================================================================

def extract_knowledge_points(pages: list[dict]) -> dict:
    """
    Extract structured knowledge from pages.

    Returns:
        {
            "metadata": {title, author, pages, date},
            "chapters": [{title, pages, key_points: str}],
            "key_terms": [{term, pages, context}],
            "tables": [{description, page, data}],
        }
    """
    result = {
        "metadata": {"title": "", "author": "", "total_pages": len(pages), "date": datetime.now().isoformat()},
        "chapters": [],
        "key_terms": [],
        "tables": [],
    }

    current_chapter = None
    chapter_texts = defaultdict(list)

    for p in pages:
        text = p["text"]
        pn = p["page_num"]

        # Detect chapter/section headers (all caps or numbered sections)
        lines = text.split("\n")
        for line in lines[:5]:
            line = line.strip()
            # Chapter patterns: "CHAPTER X", "Chapter X", numbered sections, all-caps headers
            if (line.isupper() and len(line) > 5 and len(line) < 80) or \
               line.lower().startswith("chapter") or \
               (line and line[0].isdigit() and "." in line[:4] and len(line) < 80):
                if current_chapter:
                    result["chapters"].append({
                        "title": current_chapter,
                        "start_page": chapter_texts[current_chapter][0] if chapter_texts[current_chapter] else pn,
                        "end_page": pn - 1,
                        "text": "\n".join(chapter_texts[current_chapter]),
                    })
                current_chapter = line
                chapter_texts[current_chapter] = []
                break

        if current_chapter:
            chapter_texts[current_chapter].append(text)
        elif chapter_texts:
            # Continue last chapter
            last = list(chapter_texts.keys())[-1]
            chapter_texts[last].append(text)
        else:
            chapter_texts["Preamble"].append(text)

    # Save last chapter
    if current_chapter:
        for title, texts in chapter_texts.items():
            if texts:
                result["chapters"].append({
                    "title": title,
                    "start_page": pages[0]["page_num"],
                    "end_page": pages[-1]["page_num"],
                    "text": "\n".join(texts),
                })

    return result


# ====================================================================
# SUMMARIZATION (local extraction, LLM-ready)
# ====================================================================

def generate_summary(knowledge: dict, max_sections: int = 20) -> str:
    """
    Generate a structured markdown summary from extracted knowledge.

    If you want AI-powered summarization, pass the `text` field of each
    chapter to an LLM for deeper analysis.
    """
    lines = [
        f"# Book Analysis Summary",
        f"",
        f"**Total pages**: {knowledge['metadata']['total_pages']}",
        f"**Chapters detected**: {len(knowledge['chapters'])}",
        f"**Extracted**: {knowledge['metadata']['date']}",
        f"",
        "---",
        "",
    ]

    for i, ch in enumerate(knowledge["chapters"][:max_sections]):
        text = ch["text"]
        n_chars = len(text)
        n_words = len(text.split())

        # Extract first meaningful paragraph as summary
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
        excerpt = paragraphs[0][:300] if paragraphs else text[:300]

        lines.append(f"## {i+1}. {ch['title']}")
        lines.append(f"")
        lines.append(f"*Pages {ch['start_page']}–{ch['end_page']} | {n_words:,} words | {n_chars:,} chars*")
        lines.append(f"")
        lines.append(f"> {excerpt}")
        lines.append(f"")
        lines.append(f"```")
        lines.append(f"# TO ANALYZE WITH AI:")
        lines.append(f"# Pass the full text below to an LLM with a prompt like:")
        lines.append(f"# 'Extract the key astrological concepts, techniques, and rules from this chapter.'")
        lines.append(f"```")
        lines.append("")

    return "\n".join(lines)


# ====================================================================
# MAIN
# ====================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 pdf_reader.py <pdf_file> [start_page] [end_page]")
        print("  Example: python3 pdf_reader.py rectification_manual.pdf 0 100")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    end = int(sys.argv[3]) if len(sys.argv) > 3 else None

    print(f"Reading: {pdf_path}")
    print(f"Pages: {start} → {end or 'end'}")

    # Extract
    pages = extract_pages(pdf_path, start=start, end=end)
    n_content = sum(1 for p in pages if p["has_content"])
    print(f"Extracted {len(pages)} pages ({n_content} with content)")

    # Knowledge extraction
    knowledge = extract_knowledge_points(pages)
    print(f"Found {len(knowledge['chapters'])} chapters/sections")

    # Save knowledge base
    out_dir = Path(pdf_path).stem + "_analysis"
    os.makedirs(out_dir, exist_ok=True)
    kb_path = os.path.join(out_dir, "knowledge_base.json")
    with open(kb_path, "w") as f:
        json.dump(knowledge, f, indent=2, default=str)
    print(f"Knowledge base saved to {kb_path}")

    # Generate summary
    summary = generate_summary(knowledge)
    summary_path = os.path.join(out_dir, "summary.md")
    with open(summary_path, "w") as f:
        f.write(summary)
    print(f"Summary saved to {summary_path}")

    # Print first chapter excerpt
    if knowledge["chapters"]:
        print("\n" + "=" * 60)
        print(" FIRST CHAPTER PREVIEW")
        print("=" * 60)
        ch = knowledge["chapters"][0]
        print(f"\n  {ch['title']} (pages {ch['start_page']}–{ch['end_page']})")
        preview = ch["text"][:500].replace("\n", "\n  ")
        print(f"  {preview}...")
        print(f"\n  Full text available in {kb_path}")
        print(f"  To AI-analyze: load the JSON, iterate chapters, pass text to LLM.")


if __name__ == "__main__":
    main()