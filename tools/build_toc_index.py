#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.24",
# ]
# ///
"""Build INDEX.md from a PDF's embedded table of contents (bookmarks).

The Stahl-Prescriber's-Guide `build_index.py` detects drug monographs by their
"THERAPEUTICS" section heading; that heuristic does not fit a textbook (Kandel,
Stahl's Neuroscientific Basis) or a differently-formatted drug reference (Carlat).
This sibling instead reads the PDF outline directly, so it works for any book that
ships bookmarks: it emits the outline as an indented, page-linked Markdown list
(a Part -> Chapter -> Section tree for a textbook, a per-drug list for a drug
reference). The page links point at the per-page Markdown files written by
`pdf_to_pages.py`, whose `<pagenumber>.md` names match the PDF's 1-based pages,
so the two scripts compose: split with `pdf_to_pages.py`, index with this.

Usage (from the repo root):
    uv run tools/build_toc_index.py --pdf book.pdf                 # -> INDEX.md
    uv run tools/build_toc_index.py --pdf book.pdf --pages DIR --out INDEX.md
    uv run tools/build_toc_index.py --pdf book.pdf --max-level 3   # cap outline depth
    uv run tools/build_toc_index.py --pdf book.pdf --title "Kandel 6e"  # override heading

Built with the help of Claude Code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz  # PyMuPDF


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path, help="source PDF")
    parser.add_argument("--pages", default="pages", type=Path,
                        help="directory of per-page .md files (default: pages)")
    parser.add_argument("--out", default="INDEX.md", type=Path,
                        help="output index file (default: INDEX.md)")
    parser.add_argument("--max-level", type=int, default=0,
                        help="cap outline depth (1=top only, 0=no cap; default 0)")
    parser.add_argument("--title", default=None,
                        help="index heading (default: the PDF file stem)")
    args = parser.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")

    doc = fitz.open(str(args.pdf))
    toc = doc.get_toc(simple=True)  # [[level, title, page_1based], ...]
    if not toc:
        raise SystemExit(
            f"{args.pdf.name}: no embedded table of contents (bookmarks); "
            "this index builder needs an outline (use a per-book heuristic instead)."
        )

    rel = args.pages.name  # link target dir as seen from INDEX.md
    rows = [
        (level, title.strip(), page)
        for (level, title, page) in toc
        if page >= 1 and (args.max_level == 0 or level <= args.max_level)
    ]
    if not rows:
        raise SystemExit("outline had no entries at or above the requested level.")

    # Warn (in the file) if the split page count does not match the PDF's, since
    # the page links assume file N == PDF page N.
    n_files = len(list(args.pages.glob("*.md"))) if args.pages.is_dir() else 0

    title = args.title or args.pdf.stem
    depth_note = f" (depth capped at level {args.max_level})" if args.max_level else ""
    lines = [
        f"# {title}: page index",
        "",
        f"Generated from the PDF's embedded table of contents. Page numbers are "
        f"the per-page Markdown files in `{rel}/` (one file per PDF page, e.g. "
        f"`15.md`), written by `pdf_to_pages.py`. Generated with the help of "
        f"Claude Code.",
        "",
        f"{doc.page_count} PDF pages, {len(rows)} outline entries{depth_note}.",
        "",
    ]
    if n_files and n_files != doc.page_count:
        lines += [
            f"> NOTE: `{rel}/` holds {n_files} files but the PDF has "
            f"{doc.page_count} pages; the page links may be off by the difference.",
            "",
        ]

    base_level = min(level for level, _, _ in rows)
    for level, heading, page in rows:
        indent = "  " * (level - base_level)
        lines.append(f"{indent}- [{heading}]({rel}/{page}.md) (p{page})")
    lines.append("")

    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out} ({len(rows)} entries from {doc.page_count} pages).")


if __name__ == "__main__":
    main()
