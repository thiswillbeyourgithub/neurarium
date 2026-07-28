"""Why a `verified` binding claim still deserves doubt (the ``uncertainty`` bullets).

A `verified` grade only ever meant "this sentence really is on that page". It never meant
"this sentence is *about this drug*", nor "this sentence is about *this* receptor". The shape
where the difference matters, **derived** here rather than hand-listed:

**The subject-less side-effect rule.** Stahl's **How Drug Causes Side Effects** block
prints mechanism-to-side-effect rules whose grammatical subject is the *mechanism*, not
the drug, so nothing in the sentence says this drug has the action::

    "Blockade of alpha adrenergic 1 receptors may explain dizziness, sedation, and
     hypotension"

The block is identified by the quote's own **heading trail** (see
``tools/fetch/fetch_quote_headers.py``), which is exactly what headings were resolved for;
the subject test is :func:`_attributes_to_drug`.

Those claims are kept, on evidence rather than convenience (the side-effect lines are
printed selectively, only on monographs that genuinely carry the property, and half the
bindings carry an independent measured Ki). But a flat green check overstates them, so
they carry an **uncertain** badge instead: same source, same quote, plus the reasons to
doubt it, each reason itself a badged, quote-gated claim.

**Nothing here is authored per site.** The flags and every bullet are derived from the
emitted data (the heading trail, the quote text, the drug's other sources, the Ki), so a
data edit cannot leave a stale flag behind and a new drug is covered the day it lands. The
derivation reproduces, binding for binding, the 89 that the hand audit in
``docs/SOURCING_GAPS.md`` had flagged.

**No prose is stored.** A bullet is a ``kind`` from :data:`UNCERTAINTY_REASONS` plus
optional slot ``args``; the viewer builds the sentence from an i18n key, so both languages
live in ``public/js/i18n.js`` with every other display string and the flagged bindings do
not carry a copy of the same sentences each.

**Every bullet is itself sourced, or says so.** A bullet either resolves a real
quote-gated source (``source: "own_quote"`` reuses the quote the flag was read off,
``source: "ki"`` its measured affinity) or declares ``absence: True``, which renders the
red NOSOURCE pill and reads as "the corpus does not say this". Forgetting a source is an
error, not a silent blank (:func:`_uncertainty_bullet` raises, and ``check_data.py``
family 5 re-checks it on the emitted data).
"""
from __future__ import annotations

import collections
import re
from typing import Any

from .. import quote_table

# The Stahl subsections the derivation reads. The book's subsection vocabulary is closed
# and stable across all 158 monographs (which is what makes the heading trail derivable
# at all), so matching them by name is safe rather than brittle.
SIDE_EFFECT_SUBSECTION = "How Drug Causes Side Effects"
MECHANISM_SUBSECTION = "How the Drug Works"

# Stahl's telegraphic style elides the subject of a predicate about the drug ("Prevents
# the action of acetylcholine on muscarinic receptors"), so a verb-initial sentence IS
# attributed: its subject is the drug, just unwritten. Only openers that actually occur
# in the corpus are listed; an opener missing here can only ADD doubt to a claim, never
# remove it, which is the safe direction for this list to be wrong in.
_ELIDED_SUBJECT = re.compile(
    r"^(blocks|prevents|inhibits|binds|increases|decreases|boosts|enhances|reduces|"
    r"stimulates|activates|antagonizes|modulates|potentiates|releases|occupies|"
    r"desensitizes|converts|acts|has|does|is)\b", re.I)

# "By blocking histamine 1 receptors in the brain, IT can cause sedation": a pronoun
# subject attributes the action as squarely as the drug's own name does.
_ATTRIBUTING_PRONOUN = re.compile(r"\bits?\b", re.I)


# The closed vocabulary of reason kinds. Each entry declares where its source comes from:
#
# - ``own_quote``: the quote the flag was read off (the sentence being doubted). The
#   bullet is a reading OF that quote, so it cites it and inherits its grade.
# - ``ki``:        the binding's measured-affinity source (PDSP / GtoPdb / Wikipedia).
# - ``None``:      an absence-of-evidence bullet; it MUST set ``absence`` so the viewer
#   renders NOSOURCE and the gate knows the blank is deliberate.
#
# ``args`` lists the slots the i18n sentence takes, so a typo in a derived arg is caught
# here rather than surfacing as a literal "{ki}" in the panel. Adding a kind means adding
# its ``uncertain.<kind>`` string to BOTH i18n catalogues.
UNCERTAINTY_REASONS: dict[str, dict[str, Any]] = {
    # "The source sentence explains a side effect; its subject is the mechanism, not
    # the drug." The finding itself, cited on the very sentence it is about.
    "side_effect_rule": {"source": "own_quote", "absence": False, "args": ()},
    # "The same sentence is printed on N other monographs." Not damning on its own
    # (Stahl writes true class-wide lines constantly), but it is what the reader needs
    # in order to weigh the one above.
    "class_wide": {"source": "own_quote", "absence": False, "args": ("n",)},
    # "A measured binding affinity backs it independently of the sentence."
    "measured_ki": {"source": "ki", "absence": False, "args": ("ki", "n")},
    # ... and its absence twin.
    "no_measured_ki": {"source": None, "absence": True, "args": ()},
    # "The corpus never lists this action among the drug's mechanisms of action."
    "not_a_mechanism": {"source": None, "absence": True, "args": ()},
}


def _english(value: Any) -> str:
    """A display string that may still be an authored ``{en, fr}`` pair."""
    if isinstance(value, dict):
        return str(value.get("en") or "")
    return str(value or "")


def _tokens(text: str) -> str:
    """``text`` reduced to space-separated alphanumeric tokens, space-padded.

    Matching happens on whole tokens rather than raw substrings, so a drug name cannot be
    "found" inside a longer word."""
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def _attributes_to_drug(quote: str, drug: dict[str, Any]) -> bool:
    """Does ``quote`` say that **this drug** has the action, rather than stating a rule?

    Three ways a Stahl sentence attributes: it names the drug ("Paroxetine's weak
    antimuscarinic properties..."), it uses a pronoun subject ("...IT can cause
    sedation"), or it elides the subject in the book's telegraphic style ("Prevents the
    action of acetylcholine..."). Anything else has a *mechanism* for a subject and never
    states that this drug has it.
    """
    text = quote.strip()
    if _ELIDED_SUBJECT.match(text) or _ATTRIBUTING_PRONOUN.search(text):
        return True
    tokens = _tokens(text)
    names = {drug["id"]}
    names.update(re.findall(r"[a-z]{4,}", _english(drug.get("name")).lower()))
    return any(f" {name} " in tokens for name in names)


def _uncertainty_bullet(kind: str, *, what: str, binding: dict[str, Any],
                        source: dict[str, Any] | None = None,
                        args: dict[str, Any] | None = None) -> dict[str, Any]:
    """One ``uncertainty`` bullet: a reason kind, its slot args, and its own source.

    Where the source comes from is declared by the kind, not by the caller (see
    :data:`UNCERTAINTY_REASONS`), so a bullet cannot cite the wrong thing:

    * ``own_quote`` cites the passed ``source`` (the very sentence the bullet is a
      reading of), so the bullet inherits its grade and its quote gate;
    * ``ki`` reuses the binding's measured-affinity source;
    * an ``absence`` kind carries no source on purpose and renders NOSOURCE.

    Raises when a non-absence kind resolves to nothing: a bullet with a silent blank
    would read exactly like an absence bullet while meaning "we forgot".
    """
    spec = UNCERTAINTY_REASONS.get(kind)
    if spec is None:
        raise KeyError(f"{what} uncertainty bullet {kind!r} is not an "
                       f"UNCERTAINTY_REASONS kind (one of "
                       f"{sorted(UNCERTAINTY_REASONS)})")
    args = args or {}
    missing = [a for a in spec["args"] if a not in args]
    if missing:
        raise ValueError(f"{what} uncertainty bullet {kind!r} is missing "
                         f"arg(s) {missing} (the i18n sentence has those slots)")
    out: dict[str, Any] = {"kind": kind}
    if args:
        out["args"] = args
    if spec["absence"]:
        out["absence"] = True
        return out
    if spec["source"] == "own_quote":
        src = source
    elif spec["source"] == "ki":
        src = (binding.get("ki") or {}).get("source")
    else:
        src = None
    if not src:
        raise ValueError(
            f"{what} uncertainty bullet {kind!r} resolves to no source "
            f"(it cites {spec['source']!r}, which this binding does not carry). "
            f"Every bullet must be sourced or declare absence=True.")
    out["sources"] = [dict(src)]
    return out


def apply_binding_uncertainty(drugs: list[dict[str, Any]]) -> None:
    """Derive and attach the ``uncertainty`` bullets to every doubtful binding, in place.

    Run as a post-pass over the assembled drugs rather than inside ``_binding_record``,
    because the ``class_wide`` bullet counts the drugs the same sentence is printed on,
    which no single binding can see.

    Must run **before** serialization, while the sources are still inline: the heading
    trail is looked up through :func:`quote_table.heading_of`, which keys on the quote's
    content hash.
    """
    # How many drugs each Stahl sentence is printed on. Keyed by the quote TEXT, since
    # that is what "the same sentence" means to a reader (the same line on two pages is
    # two quote nodes but one printed rule).
    spread: dict[str, set[str]] = collections.defaultdict(set)
    for drug in drugs:
        for b in drug.get("bindings", []):
            for src in b.get("sources", []):
                if src.get("corpus") == "stahl" and src.get("quote"):
                    spread[src["quote"]].add(drug["id"])

    for drug in drugs:
        for b in drug.get("bindings", []):
            what = f"Drug {drug['id']!r} binding {b['target']!r}"
            rule_source = None          # the subject-less side-effect sentence, if any
            in_stahl = False            # is this binding read off a Stahl monograph ...
            has_mechanism = False       # ... and does the book state it as a mechanism?
            for src in b.get("sources", []):
                if src.get("corpus") != "stahl" or not src.get("quote"):
                    continue
                in_stahl = True
                trail = quote_table.heading_of(src)
                where = trail[-1] if trail else None
                if where == MECHANISM_SUBSECTION:
                    has_mechanism = True
                elif (where == SIDE_EFFECT_SUBSECTION
                        and not _attributes_to_drug(src["quote"], drug)):
                    rule_source = src
            if not rule_source:
                continue

            bullets = [_uncertainty_bullet(
                "side_effect_rule", what=what, binding=b, source=rule_source)]
            others = len(spread.get(rule_source.get("quote", ""), ())) - 1
            if others > 0:
                bullets.append(_uncertainty_bullet(
                    "class_wide", what=what, binding=b, source=rule_source,
                    args={"n": others}))
            # The affinity bullet is derived, never authored, so it cannot drift from
            # the Ki actually shipped: it says what the measurement is, or that there
            # is none (which is itself a reason to doubt).
            ki = b.get("ki")
            if ki:
                bullets.append(_uncertainty_bullet(
                    "measured_ki", what=what, binding=b,
                    args={"ki": ki["median"],
                          "n": int(ki.get("n_human", 0)) + int(ki.get("n_nonhuman", 0))}))
            else:
                bullets.append(_uncertainty_bullet(
                    "no_measured_ki", what=what, binding=b))
            # Only sayable about a drug the book actually covers: "the corpus never lists
            # this among its mechanisms" is a statement about a monograph that exists.
            if in_stahl and not has_mechanism:
                bullets.append(_uncertainty_bullet(
                    "not_a_mechanism", what=what, binding=b))
            # Evidence first, absences last: the list reads as "here is what the source
            # does say ... but here is what it never says", which is the shape of the
            # doubt. Stable within each half (the order they were built in).
            bullets.sort(key=lambda bl: bool(bl.get("absence")))
            b["uncertainty"] = bullets
