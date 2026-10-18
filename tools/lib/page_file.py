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


def page_file(pages_dir: str | Path | None, page: Any) -> Path | None:
    """``<pages_dir>/<page>.md``, or None when there is no directory or the page
    fails :func:`page_name`. Whether the file exists is the caller's question (the
    page trees are author-side, absent on a clone).

    >>> page_file("data_sources/bdpm/pages", "69071035").as_posix()
    'data_sources/bdpm/pages/69071035.md'
    >>> page_file("pages", "../../etc/passwd") is None
    True
    """
    name = page_name(page)
    if not pages_dir or name is None:
        return None
    return Path(pages_dir) / f"{name}.md"
