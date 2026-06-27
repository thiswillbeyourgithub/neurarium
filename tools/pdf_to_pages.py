#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf4llm>=0.0.17",
# ]
# ///
"""Split a PDF into one Markdown file per page.

Each output file is named <pagenumber>.md (1-based, matching the PDF page) and
holds that page's text extracted as Markdown by pymupdf4llm. This is the first
half of the source-verification pipeline: regenerate a corpus's per-page text from
a PDF you hold, then `tools/check_data.py` confirms every `verified` quote really
appears on its cited page. The defaults target the Stahl corpus so anyone with
that book can reproduce it in one command; pass --pdf/--out for another book.

Usage (from the repo root):
    uv run tools/pdf_to_pages.py                 # regenerate the Stahl pages (defaults)
    uv run tools/pdf_to_pages.py --pdf foo.pdf --out sources/books/foo/pages
    uv run tools/pdf_to_pages.py --zero-pad      # 0001.md, 0002.md, ... (sortable)

Built with the help of Claude Code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf4llm

# Defaults target the Stahl corpus from the repo root, so a bare
# `uv run tools/pdf_to_pages.py` regenerates the pages the quote-verification gate
# (tools/check_data.py) checks against. Point --pdf/--out elsewhere for another book.
DEFAULT_PDF = "sources/books/stahl/Prescriber's Guide_ Stahl's Essential Psychopharmacology.pdf"
DEFAULT_OUT = "sources/books/stahl/pages"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        default=DEFAULT_PDF,
        type=Path,
        help=f"source PDF (default: {DEFAULT_PDF!r})",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        type=Path,
        help=f"output directory for the per-page .md files (default: {DEFAULT_OUT!r})",
    )
    parser.add_argument(
        "--zero-pad",
        action="store_true",
        help="zero-pad the file names so they sort naturally (e.g. 0007.md)",
    )
    parser.add_argument(
        "--layout",
        action="store_true",
        help="use pymupdf's layout/OCR engine (slower; better column/table reading "
        "order but per-page OCR may alter characters). Default off: classic "
        "text-layer extraction (faithful + fast), which exact-substring quote "
        "checking relies on.",
    )
    args = parser.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")

    args.out.mkdir(parents=True, exist_ok=True)

    # Newer pymupdf4llm ships a layout/OCR engine that is ON by default; turn it
    # off unless asked, so extraction stays fast and faithful to the PDF's text
    # layer (the original Stahl split predates this engine). Older versions lack
    # the toggle, so guard on it.
    if hasattr(pymupdf4llm, "use_layout"):
        pymupdf4llm.use_layout(args.layout)

    # page_chunks=True returns one dict per page, in order; the markdown text
    # of each page is under the "text" key.
    pages = pymupdf4llm.to_markdown(str(args.pdf), page_chunks=True)
    width = len(str(len(pages))) if args.zero_pad else 0

    for index, page in enumerate(pages, start=1):
        name = f"{index:0{width}d}.md" if width else f"{index}.md"
        text = page["text"] if isinstance(page, dict) else str(page)
        (args.out / name).write_text(text, encoding="utf-8")

    print(f"Wrote {len(pages)} pages to {args.out}/")


if __name__ == "__main__":
    main()
