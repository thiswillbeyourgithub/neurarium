"""The viewer's UI message catalogue (``public/js/i18n/<lang>.js``) read from Python.

One reader for every tool that must show a reader the same words the viewer does: the
/api Markdown headings (``tools/api_sections.py``), the quote judge's uncertainty
sentences (``sourcing/claim_walk.py``) and the EN/FR parity test (``tests/test_i18n.py``).

The scan is a regex over one-line ``"key": "value"`` entries rather than a JS parse: every
UI string the panels look up is written that way, and an entry it cannot see is invisible
the same way in both languages. Stdlib only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parent.parent.parent / "public" / "js" / "i18n"
ENTRY = re.compile(r'^\s*"([A-Za-z0-9_.]+)":\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)


def unescape(raw: str) -> str:
    """A JS double-quoted string body as its value (``\\"``, ``\\'``, ``\\n``, ``\\uXXXX``)."""
    return json.loads('"' + raw.replace("\\'", "'") + '"')


def entries(lang: str = "en", i18n_dir: Path = I18N_DIR) -> list[tuple[str, str]]:
    """Every ``(key, raw string body)`` in file order, duplicates kept (for the guard
    that a JS object literal never silently shadows one)."""
    return ENTRY.findall((i18n_dir / f"{lang}.js").read_text(encoding="utf-8"))


def catalogue(lang: str = "en", i18n_dir: Path = I18N_DIR) -> dict[str, str]:
    """``key -> string`` (unescaped) for one language; a duplicate key keeps its last
    value, as the JS object literal does."""
    return {k: unescape(v) for k, v in entries(lang, i18n_dir)}


def fill(text: str, **values: object) -> str:
    """Fill ``{name}`` placeholders the way ``js/i18n.js`` ``t()`` does."""
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text
