"""Read the full-text paper corpus (#25 ``papers``) as whole sentences.

A paper page (``tools/fetch/fetch_papers.py``) is PDF-to-Markdown text: hard-wrapped
lines, words hyphenated across a break, ``**bold**`` / ``_italic_`` markup, two-column
layouts. :func:`sentences` rebuilds whole sentences from it so a picker sees "5-HT2A
antagonists ... consistently increase SWS in subjects with normal sleep." rather than
the fragment after a line break, and every sentence stays a verbatim quote: the quote
gate compares through ``lib.quote_match.normalize_for_match``, which folds exactly the
artifacts cleaned here (hyphen breaks, markup, whitespace).

A library, not a script. Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from pathlib import Path

from lib.page_file import read_page
from lib.quote_match import normalize_for_match

ROOT = Path(__file__).resolve().parents[3]
PAGES_DIR = ROOT / "data_sources" / "papers" / "pages"

_PAGE_HEAD = re.compile(r"^## PDF page (\d+)\s*$")
_BREAK = re.compile(r"^\s*(?:#{1,6}\s|\|)|^\s*$")  # heading, table row, blank: ends a paragraph
_MARKUP = re.compile(r"\*\*|__|(?<!\w)_(?=\w)|(?<=\w)_(?!\w)|</?(?:u|b|i|em|strong|sup|sub)>")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
MIN_CHARS, MAX_CHARS = 30, 600


def _clean(paragraph: str) -> str:
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", paragraph)   # sero-\ntonin -> serotonin
    text = _MARKUP.sub("", text)
    return " ".join(text.split())


def sentences(key: str, pages: Path = PAGES_DIR) -> list[tuple[int, str]]:
    """``[(pdf page, sentence)]`` for paper ``key``, in reading order; ``[]`` when the
    page is absent. Header lines (before the first ``## PDF page``) are skipped."""
    text = read_page(pages, key)
    if text is None:
        return []
    out: list[tuple[int, str]] = []
    page, para = 0, []

    def flush():
        if para and page:
            for s in _SPLIT.split(_clean("\n".join(para))):
                s = s.strip()
                if MIN_CHARS <= len(s) <= MAX_CHARS:
                    out.append((page, s))
        para.clear()

    for line in text.splitlines():
        m = _PAGE_HEAD.match(line)
        if m:
            flush()
            page = int(m.group(1))
            continue
        if _BREAK.match(line):
            flush()
            continue
        para.append(line.lstrip("-•* ").rstrip())
    flush()
    # A sentence rebuilt across an OCR break the gate folds differently is dropped, so
    # only quotes the gate accepts are ever offered.
    whole = normalize_for_match(text)
    return [(p, s) for p, s in out if normalize_for_match(s) in whole]
