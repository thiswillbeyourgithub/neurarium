"""Placeholder words that must never ship as a name (a brand, a holder, an originator).

Stahl's Prescriber's Guide closes some "Brands" lists with a literal "Other" bullet
(diazepam: "Valium / Diastat / Other"), meaning "and other brands", not a trade name.
The word is on the page, so a verbatim-quote gate happily confirms it; only a vocabulary
check can refuse it. Defined once and shared by the Stahl brand parser (which drops
them) and the generator (which raises on them, whatever corpus wrote the name).

Stdlib only. Built with the help of Claude Code.
"""
from __future__ import annotations

# Compared case-folded, punctuation and whitespace stripped at both ends.
PLACEHOLDER_NAMES = frozenset({
    "other", "others", "generic", "generics", "todo", "tbd", "n/a", "na", "none",
    "unknown", "various", "misc", "-", "?",
})


def is_placeholder(name: object) -> bool:
    """True when ``name`` is not a usable name: not a string, empty, whitespace-only, or a
    placeholder word (``"Other"``, ``" n/a "``, ``"TODO"``)."""
    if not isinstance(name, str):
        return True
    folded = name.strip().strip(".:;,").strip().casefold()
    return not folded or folded in PLACEHOLDER_NAMES
