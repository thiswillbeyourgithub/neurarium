"""The one reader of Stahl's generated ``INDEX.md`` (drug -> monograph page span).

Stahl's Prescriber's Guide has one monograph per drug over a contiguous page span, and
``tools/fetch/build_index.py`` writes those spans as a Markdown table under the
author-side ``data_sources/books/stahl/``::

    | 5 | Amitriptyline | [39-46](pages/39.md) |
    | 6 | Some drug     | [47](pages/47.md) |      <- a one-page monograph has no dash

Every Stahl pass (the check's monograph-range gate, the CYP / pharmacokinetics / Tmax
fetchers, the source-quote / brand / category / NbN appliers) needs "which pages are this
drug's monograph", and each used to parse that table itself. They differed only in how a
drug name is folded into a lookup key, so :func:`ranges` takes the fold as a parameter and
the row grammar lives here once.

:func:`find_page` is the other repeated piece: "the first page of a span whose text holds
this quote", under the quote gate's own ``lib.quote_match.normalize_for_match``, so a page found
here is a page ``check_data.py`` accepts by construction.

Stdlib only; author-side (the book tree is gitignored, so on a clone :data:`INDEX` is
absent and callers decide whether that is an error or a skip).

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib.text_fold import alnum_key

STAHL_DIR = Path(__file__).resolve().parents[2] / "data_sources" / "books" / "stahl"
INDEX = STAHL_DIR / "INDEX.md"
PAGES = STAHL_DIR / "pages"

# One table row: "| <n> | <drug name> | [<start>-<end>](...)" or "[<start>](...)" for a
# one-page monograph (build_index.py writes that form when start == end). The name is
# lazy up to the cell separator, so its surrounding spaces stay out of it.
_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)(?:-(\d+))?\]")


def rows(path: Path = INDEX, missing_ok: bool = False) -> list[tuple[str, int, int]]:
    """Every monograph row of the index, in book order.

    Parameters
    ----------
    path
        The ``INDEX.md`` to read (default: Stahl's).
    missing_ok
        When true an absent file yields ``[]`` (the check's "skip on a clone" rule);
        otherwise it raises ``FileNotFoundError`` like a plain read would.

    Returns
    -------
    list of (str, int, int)
        ``(display drug name, first page, last page)``, pages inclusive. A one-page
        monograph has ``first == last``.
    """
    if missing_ok and not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            start = int(m.group(2))
            out.append((m.group(1), start, int(m.group(3) or start)))
    return out


def ranges(key: Callable[[str], str] = alnum_key, path: Path = INDEX,
           missing_ok: bool = False) -> dict[str, tuple[int, int]]:
    """``key(drug name) -> (first page, last page)`` over :func:`rows`.

    The fold is the only thing the callers disagree on (``alnum_key`` keeps accented
    letters, ``drugs_io.ascii_key`` drops them, the CYP pass only lowercases), so each
    passes the one its lookups are keyed with. Two rows folding to one key: the later
    row wins, as a plain dict build does.
    """
    return {key(name): (lo, hi) for name, lo, hi in rows(path, missing_ok)}


def find_page(start: int, end: int, quote: str, min_chars: int = 1,
              pages: Path = PAGES) -> int | None:
    """The first page in ``start..end`` (inclusive) whose text holds ``quote``.

    The match is the quote gate's own: an exact substring test on
    ``lib.quote_match.normalize_for_match`` of both sides, so the page returned is one
    ``check_data.py`` will accept. The whole span is searched, so the page is the one
    the text really sits on, never the one an LLM remembered.

    Parameters
    ----------
    start, end
        Inclusive page-file numbers (``pages/<n>.md``); a missing file is skipped.
    quote
        The raw quote.
    min_chars
        Refuse (return ``None``) a quote whose normalized form has fewer than this many
        non-space characters: a short needle matches by accident (the source-quote pass
        uses 12, the check's ``_MIN_QUOTE_CHARS`` floor; the default 1 only refuses an
        empty one).
    pages
        The page tree (default: Stahl's).

    Returns
    -------
    int or None
        The page number, or ``None`` when no page in the span holds it.
    """
    from lib.quote_match import normalize_for_match

    needle = normalize_for_match(quote)
    if len(needle.replace(" ", "")) < min_chars:
        return None
    for p in range(start, end + 1):
        f = page_path(pages, p)
        if f.exists() and needle in normalize_for_match(f.read_text(encoding="utf-8")):
            return p
    return None
