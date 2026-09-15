#!/usr/bin/env python
"""Name a modeled drug target the way prose does, so "the quote names the target" is testable.

The dataset calls a target by an id (``5ht2c``, ``alpha2a``, ``sert``) and a display
name (``5-HT2C``, ``α2A``, ``Serotonin transporter (SERT)``); an article calls it
whatever its author typed (``5-HT 2C``, ``serotonin 2C``, ``alpha-2A adrenergic``,
``5-HTT``). Both halves of the binding-direction pass need the same answer to "does
this sentence name this target": the fetcher to offer a candidate line at all, the
applier to gate the judge's pick. One definition here, imported by both, because two
copies of a matching rule drift and the gate would then accept what the worklist never
offered.

Lives in ``tools/`` next to ``drugs_io.py`` / ``chirality.py`` (the shared,
stdlib-only libraries) rather than inside either script: the fetcher is a ``uv run``
module with a BeautifulSoup dependency, and the applier must stay importable with the
stdlib alone.

Matching is deliberately **shape-tolerant, boundary-strict**:

* Greek letters fold to their Latin names (``α2A`` and ``alpha-2A`` are one target),
  and accents decompose away, so the fold is stable across an article's typography.
* An alias matches across a short run of separators (``5-HT2C`` also finds ``5-HT 2C``
  and ``5HT2C``), because a spelling difference is not a different claim.
* It never matches inside a longer alphanumeric token: ``d2`` does not fire on
  ``CYP2D6`` or on "and 2", and ``alpha2`` does not fire on ``alpha2A``, so the coarse
  receptor-group target cannot silently absorb one of its subtypes.

A broad alias is a false positive at worst, never a false claim: this test says only
that a sentence *mentions* the target, and a model plus the verbatim quote gate decide
whether it states a direction for it.

Built with the help of Claude Code.
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:                  # so `data_generators` resolves when a caller
    sys.path.insert(0, HERE)              # imported this module by path, not by package

from data_generators.drugs import DRUG_TARGETS  # noqa: E402  (authoring side, not meta.json)
from data_generators.receptors import RECEPTORS  # noqa: E402

# Greek is spelled out rather than stripped, because an article writes the same
# receptor both ways ("α2A" / "alpha-2A") and stripping would leave "2a", which no
# longer names an adrenoceptor at all. Only the letters the target names actually use.
GREEK_TO_LATIN = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "κ": "kappa", "μ": "mu", "σ": "sigma", "ω": "omega",
    "Α": "alpha", "Β": "beta", "Γ": "gamma", "Δ": "delta", "Κ": "kappa",
    "Μ": "mu", "Σ": "sigma", "Ω": "omega",
}

# How much punctuation/whitespace an alias may skip between two of its tokens. Bounded
# (not ``*``) on purpose: an unbounded run would let "M." ... ", 1" satisfy the alias
# "M1" across a sentence boundary, which is a mention of nothing.
SEP = r"[^a-z0-9]{0,2}"


def fold(text: str) -> str:
    """Canonicalize text for alias matching: Greek spelled out, accents dropped, lowercased.

    Separators are **kept** (unlike ``check_data.normalize_for_match``, which collapses
    them): the boundary assertions in :func:`alias_pattern` need to see where a token
    starts and ends.

    Parameters
    ----------
    text : str
        Raw prose or an alias.

    Returns
    -------
    str
        The folded form, safe to run an alias pattern against.
    """
    for greek, latin in GREEK_TO_LATIN.items():
        text = text.replace(greek, latin)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def alias_pattern(alias: str) -> str | None:
    """The regex source matching one alias in folded text, or None when it has no tokens.

    The alias is cut into runs of letters and runs of digits, which are then rejoined
    with an optional short separator. That is what makes one alias cover a family of
    spellings ("5-HT2C" -> ``5-HT2C``, ``5-HT 2C``, ``5HT2C``, ``5 ht(2c)``) without
    listing each. Lookarounds on both ends keep the match on token boundaries.

    Parameters
    ----------
    alias : str
        A name the target may go by, in any typography.

    Returns
    -------
    str or None
        A regex source string, or None when the alias holds no alphanumerics.
    """
    tokens = re.findall(r"[a-z]+|[0-9]+", fold(alias))
    if not tokens:
        return None
    body = SEP.join(re.escape(t) for t in tokens)
    return rf"(?<![a-z0-9]){body}(?![a-z0-9])"


def alias_regex(aliases: list[str]) -> re.Pattern[str] | None:
    """One compiled alternation over every alias of a target (None when there are none)."""
    parts = [p for p in (alias_pattern(a) for a in aliases) if p]
    return re.compile("|".join(parts)) if parts else None


def mentions(text: str, aliases: list[str]) -> bool:
    """Whether folded ``text`` names the target any of ``aliases`` stands for."""
    rx = alias_regex(aliases)
    return bool(rx and rx.search(fold(text)))


# Names no rule can derive from an id + display name, because they are what an article
# happens to call the thing. Kept small and explicit: a missing alias costs a candidate
# sentence, an invented one would let a sentence about something else through the gate.
EXTRA_ALIASES: dict[str, list[str]] = {
    # The transporters go by gene symbol, by the reuptake process, and (SERT) by an
    # older abbreviation that is still the common one in pharmacology prose.
    "sert": ["5-HTT", "SLC6A4", "serotonin reuptake"],
    "net": ["noradrenaline transporter", "norepinephrine reuptake",
            "noradrenaline reuptake", "SLC6A2"],
    "dat": ["dopamine reuptake", "SLC6A3"],
    # Opioid receptors: the display name carries the Greek letter and the three-letter
    # abbreviation, so only the spelled-out compounds are added here. A bare "delta"
    # can in principle fire on "delta-9-THC"; harmless, because no drug in the roster
    # carries both a delta-opioid binding and a cannabinoid article.
    "mu": ["mu opioid", "mu receptor"],
    "kappa": ["kappa opioid", "kappa receptor"],
    "delta": ["delta opioid", "delta receptor"],
    # The subtype is what identifies this one; "nAChR" alone names every other subtype too.
    "nachr_a7": ["alpha7", "alpha7 nicotinic", "alpha7 nAChR"],
    # The coarse group target. The boundary rule already keeps "alpha2" off "alpha2A".
    "alpha2": ["alpha2 adrenergic", "alpha2 autoreceptor", "alpha2 adrenoceptor"],
}


def target_names() -> dict[str, str]:
    """Every modeled drug target id -> its English display name.

    Read from the **authoring** side (``data_generators``), not from
    ``public/data/meta.json``, so the pass runs on a checkout whose site has not been
    regenerated. Mirrors ``_build_drug_targets``: the non-receptor targets plus every
    receptor id (the two id spaces do not overlap).
    """
    names = {tid: rec["name"]["en"] for tid, rec in DRUG_TARGETS.items()}
    for receptor in RECEPTORS:
        names.setdefault(receptor["id"], receptor["name"])
    return names


def target_aliases(target_id: str, display_name: str) -> list[str]:
    """Every name one target may appear under in prose, deduplicated, in stable order.

    Parameters
    ----------
    target_id : str
        The dataset id (``5ht2c``, ``alpha2a``, ``sert``).
    display_name : str
        Its English display name (``5-HT2C``, ``α2A``, ``Serotonin transporter (SERT)``).

    Returns
    -------
    list of str
        Aliases to hand :func:`alias_regex`. Shape variants (hyphen/space/Greek) are
        NOT listed: :func:`alias_pattern` already covers those.
    """
    out: list[str] = [display_name]
    # "Serotonin transporter (SERT)" states two names: the phrase and the abbreviation.
    # Both are used in prose, and the abbreviation is usually the one a binding sentence
    # reaches for.
    for inner in re.findall(r"\(([^)]+)\)", display_name):
        out.append(inner)
    head = display_name.split("(")[0].strip()
    if head:
        out.append(head)
    # The id doubles as the flat spelling a table or a terse sentence uses ("5ht2c",
    # "alpha2a", "d4"). Skipped when it carries an underscore, which is our own
    # punctuation and names nothing on a page.
    if "_" not in target_id:
        out.append(target_id)
    # A serotonin receptor is routinely named by transmitter + subtype rather than by
    # the 5-HT shorthand ("serotonin 2C receptor"), which no other family does.
    sub = re.fullmatch(r"5ht(.+)", target_id)
    if sub:
        out.append(f"serotonin {sub.group(1).upper()}")
    out.extend(EXTRA_ALIASES.get(target_id, []))
    seen: set[str] = set()
    return [a for a in out if a and not (a.lower() in seen or seen.add(a.lower()))]


def aliases_by_target() -> dict[str, list[str]]:
    """``{target id: aliases}`` for every modeled drug target."""
    return {tid: target_aliases(tid, name) for tid, name in target_names().items()}
