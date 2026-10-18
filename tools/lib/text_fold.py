"""Shared name/text folding for the author-side tools (stdlib only).

Two primitives every matcher here was re-implementing:

- :func:`strip_accents`: NFKD-decompose and drop the combining marks, so
  ``"Théralène"`` -> ``"Theralene"``. Case and punctuation are left to the caller,
  since each matcher keeps different separators (``target_aliases.fold`` needs word
  boundaries, ``apply_brand_names.brand_key`` drops them all).
- :func:`alnum_key`: lowercase alphanumerics only, the key a drug name is reconciled
  against a book ``INDEX.md`` with, so ``"Amphetamine (D)"`` and ``"Amphetamine D"``
  meet as ``"amphetamined"``.
- :func:`ascii_key`: the same but ASCII ``[a-z0-9]`` only (an accented letter is
  dropped, not kept), the key drug and metabolite names are joined on across the
  fetchers, appliers and generator (``"Carbamazepine-10,11-epoxide"`` ->
  ``"carbamazepine1011epoxide"``).
"""
from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    """``text`` with every combining mark removed after NFKD decomposition."""
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def alnum_key(name: str) -> str:
    """Lowercase alphanumerics only (``str.isalnum``, so accented letters survive)."""
    return "".join(c for c in name.lower() if c.isalnum())


def ascii_key(name: str | None) -> str:
    """Lowercase ASCII letters and digits only (``None`` -> ``""``)."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())
