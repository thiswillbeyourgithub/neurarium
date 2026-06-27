#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Build INDEX.md: the page range of each drug monograph in the split pages/.

Self-contained (stdlib only). It detects each monograph by its "THERAPEUTICS"
section heading (every Stahl monograph opens with one) and reads the drug name
from the bold heading just above it. A drug spans from its start page up to the
page before the next monograph; the last drug stops at the back-matter
("Index by Drug Name").

Usage (from the repo root):
    uv run tools/build_index.py           # reads sources/books/stahl/pages -> its INDEX.md
    uv run tools/build_index.py --pages PAGES_DIR --out INDEX.md

Built with the help of Claude Code.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

NAME_HEADING = re.compile(r"##\s*\*\*([^*]+?)\*\*")
BACKMATTER = re.compile(r"Index.{0,15}(Drug|Name)", re.IGNORECASE)


def page_number(path: Path) -> int:
    return int(path.stem)


def find_monographs(pages_dir: Path):
    """Return [(start_page, drug_name), ...] in page order."""
    starts = []
    for path in sorted(pages_dir.glob("*.md"), key=page_number):
        text = path.read_text(encoding="utf-8")
        if "THERAPEUTICS" not in text:
            continue
        m = NAME_HEADING.search(text)
        name = m.group(1).strip().title() if m else path.stem
        starts.append((page_number(path), name))
    return starts


def backmatter_page(pages_dir: Path, after: int) -> int:
    """First page after `after` that is back matter (the drug-name index)."""
    for path in sorted(pages_dir.glob("*.md"), key=page_number):
        n = page_number(path)
        if n <= after:
            continue
        if BACKMATTER.search(path.read_text(encoding="utf-8")):
            return n
    return after + 1  # fall back: last drug is a single page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", default="sources/books/stahl/pages", type=Path,
                        help="directory of per-page .md files "
                             "(default: sources/books/stahl/pages)")
    parser.add_argument("--out", default="sources/books/stahl/INDEX.md", type=Path,
                        help="output index file (default: sources/books/stahl/INDEX.md)")
    args = parser.parse_args()

    starts = find_monographs(args.pages)
    if not starts:
        raise SystemExit(f"no monographs found under {args.pages}/")

    # end of each drug = page before the next monograph; last drug = up to
    # the page before the back matter.
    rows = []
    for i, (start, name) in enumerate(starts):
        if i + 1 < len(starts):
            end = starts[i + 1][0] - 1
        else:
            end = backmatter_page(args.pages, start) - 1
        rows.append((name, start, end))

    rel = args.pages.name  # link target dir as seen from INDEX.md
    lines = [
        "# Stahl Prescriber's Guide: drug page index",
        "",
        f"Page numbers below are the per-page Markdown files in `{rel}/` "
        "(one file per PDF page, e.g. `15.md`).",
        "Generated with the help of Claude Code.",
        "",
        f"{len(rows)} drugs.",
        "",
        "| # | Drug | Pages |",
        "|---|------|-------|",
    ]
    for i, (name, start, end) in enumerate(rows, start=1):
        span = f"{start}" if start == end else f"{start}-{end}"
        lines.append(f"| {i} | {name} | [{span}]({rel}/{start}.md) |")
    lines.append("")

    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out} ({len(rows)} drugs).")


if __name__ == "__main__":
    main()
