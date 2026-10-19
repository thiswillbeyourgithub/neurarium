"""The one rule turning a citation's ``page`` into a quote-gate page file name.

A citation's ``page`` reaches the tools from untrusted places: an LLM's judged
answer, an API response (a DailyMed setid), a hand edit. Every page file is
``<pages_dir>/<page>.md``, so an unchecked value like ``../../README`` would make a
quote "pass" against a file outside the corpus. Every page value the dataset emits
today is a bare token (a book page ``982``, a slug ``lithium_medication``, a CIS
``69071035``, an EMA ``EMEA-H-C-123``), so anything else is refused here, once,
instead of at each of the call sites that build the path.

Stdlib only, so ``generate_data.py`` and ``check_data.py`` stay runnable offline.

Built with the help of Claude Code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Letters, digits, `_`, `.`, `-`, not starting with a dot (so `.` / `..` and hidden
# names are out). No separator can appear, so the file always sits in pages_dir.
_PAGE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")


def page_name(page: Any) -> str | None:
    """``page`` as a safe file stem, or None when it is empty or path-like.

    >>> page_name(982), page_name(" lithium_medication "), page_name("../x")
    ('982', 'lithium_medication', None)
    """
    text = str(page if page is not None else "").strip()
    return text if _PAGE.fullmatch(text) else None


def page_file(pages_dir: str | Path | None, page: Any, suffix: str = ".md") -> Path | None:
    """``<pages_dir>/<page><suffix>``, or None when there is no directory or the page
    fails :func:`page_name`. Whether the file exists is the caller's question (the
    page trees are author-side, absent on a clone). ``suffix`` names a sibling store
    keyed by the same id (a fetcher's ``raw/<id>.json`` / ``.html`` / ``.xml``).

    >>> page_file("data_sources/bdpm/pages", "69071035").as_posix()
    'data_sources/bdpm/pages/69071035.md'
    >>> page_file("pages", "../../etc/passwd") is None
    True
    """
    name = page_name(page)
    if not pages_dir or name is None:
        return None
    return Path(pages_dir) / f"{name}{suffix}"


def page_path(pages_dir: str | Path, page: Any, suffix: str = ".md") -> Path:
    """``<pages_dir>/<page><suffix>`` for a caller that writes or must read the file: a
    page id failing :func:`page_name` raises instead of returning None, so a path-like
    id can never name a file outside ``pages_dir``.

    >>> page_path("data_sources/gtopdb/pages", 61).as_posix()
    'data_sources/gtopdb/pages/61.md'
    """
    path = page_file(pages_dir, page, suffix)
    if path is None:
        raise ValueError(f"refusing page id {page!r} under {pages_dir}: not a bare token")
    return path


def read_page(pages_dir: str | Path | None, page: Any) -> str | None:
    """The raw (unnormalized) text of ``<pages_dir>/<page>.md``, or None when there is
    no directory, the page fails :func:`page_name`, or the file is absent. Undecodable
    bytes are replaced, as every quote gate reads them. The one raw page reader: a gate
    normalizes it (``pipeline.gate.PageGate``), a judge's excerpt keeps it raw.
    """
    return read_page_file(page_file(pages_dir, page))


def read_page_file(path: str | Path | None) -> str | None:
    """The raw text of a page file a caller already holds the path of (a stored article
    ``lib.corpora.wikipedia.page_for`` resolved, one entry of a page-tree glob), or None
    when ``path`` is empty or absent. Undecodable bytes are replaced, as in
    :func:`read_page`, which is this plus the page-id join.
    """
    if not path or not Path(path).exists():
        return None
    return Path(path).read_text("utf-8", errors="replace")
