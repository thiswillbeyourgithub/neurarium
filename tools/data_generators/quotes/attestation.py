"""Which *part* of a pathway claim its quote actually attests (the per-claim split).

A projection record states three things at once, and one quote almost never carries all
three: that the pathway **exists** (region A projects to region B), what **transmitter**
it carries, and, for the glutamate/GABA arrows, its **sign** (excitatory / inhibitory).
Before this pass all three rode the pathway's single grade, so a Kandel sentence that
only ever said *the subthalamic nucleus projects to the globus pallidus* also published a
green check on "Glutamate", and the sign it implies colours every arrow in the viewer's
Potential mode. That is the same overstatement the receptor classification was split for
(``RECEPTOR_CLASSIFICATION_COVERAGE``: a quote grades only the attributes it
substantiates) and the same one the binding-direction split fixed, so it is fixed the
same way: each part becomes its own graded node.

Two node kinds come out of it, on the projection's ``claims`` dict:

* ``transmitter`` (kind ``projection_transmitter``), on **every** pathway: the record
  always names one (``neurotransmitter``), and naming it is a separate assertion from
  drawing the arrow.
* ``sign`` (kind ``projection_sign``), on the pathways whose ``kind`` maps to a real sign
  only. A modulatory system's arrow makes **no** sign claim at all (``KIND_TO_SIGN``
  folds it to the neutral grey "modulatory"), so inventing a node for it would count a
  claim nobody made.

**Derived, never authored per pathway**, like the uncertainty flags next door: a
sub-claim earns its quote's grade when a quote the pathway already cites *names* the
claimed transmitter or the claimed sign, else it stays :data:`BASE_GRADE` with no source.
So a data edit cannot leave a stale attestation behind, and a new arrow is covered the
day it lands. The vocabulary is closed (:data:`TRANSMITTER_WORDS`, :data:`SIGN_WORDS`)
and deliberately narrow: it matches the transmitter's own name and its ``-ergic``
adjective, never the anatomy that implies it. "Raphe nuclei" is not a word for serotonin
here, because a sentence naming the nucleus has not stated what it releases.

**What the word test can and cannot see.** It is a presence test on the cited sentence,
not a parse of it, so it inherits one known over-reach: a sentence about an *inhibitory*
pathway and a sentence that merely uses the verb "inhibits" both contain ``inhibit``. It
is kept because the alternative is worse in both directions (a hand-assigned list goes
stale silently, and no split at all leaves every sign green), and because the failure is
bounded: a false attestation can only ever hand the sub-claim the grade the pathway
already had, never invent a source. The honest half is the large one: most pathway quotes
name neither, and those now read ``llm`` instead of borrowing the arrow's check.

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from typing import Any

from ..presentation import KIND_TO_SIGN

# The grade a sub-claim keeps when no cited quote names it: the value is still an
# LLM-authored classification, exactly like an unattested receptor attribute.
BASE_GRADE = "llm"

# Strongest-first, so a claim attested by several quotes takes the best of them. Mirrors
# ``_GRADE_RANK`` in generate_data.py; kept local so this module stays importable on its
# own (it is a two-entry ordering, not a duplicated table).
_GRADE_RANK = {"llm": 0, "sourced": 1, "verified": 2}

# A transmitter is attested when the sentence names the substance or its "-ergic"
# adjective. Keyed by the emitted ``neurotransmitter`` display string (English), which
# ``_projection_records`` writes from a closed authored vocabulary, so a new transmitter
# with no entry here raises rather than silently never attesting.
TRANSMITTER_WORDS: dict[str, str] = {
    "Glutamate": r"glutamat",                        # glutamate, glutamatergic
    "GABA": r"\bgaba",                               # GABA, GABAergic, GABA-ergic
    "Dopamine": r"dopamin",
    "Serotonin": r"seroton|5-?ht\b",                 # serotonin, serotonergic, 5-HT
    "Noradrenaline": r"noradren|norepinephrin|adrenergic",
    "Acetylcholine": r"cholin",                      # acetylcholine, cholinergic
    "Histamine": r"histamin",
    "Melatonin": r"melatonin",
    "Releasing hormones": r"hormon|releasing factor|neuroendocrin",
}

# A sign is attested when the sentence uses the word itself. Only the two signed kinds
# appear: "modulatory" is the ABSENCE of a sign claim, not a third value.
SIGN_WORDS: dict[str, str] = {
    "excitatory": r"excitat",                        # excitatory, excitation, excites
    "inhibitory": r"inhibit",                        # inhibitory, inhibition, inhibits
}

# The metabolism twin of the two tables above. A drug's enzyme row states two things at
# once as well: WHICH isoform clears the drug (or is modulated by it) and HOW MUCH of the
# job it does, and the CYP applier's quote gate only ever checked the first ("the quote
# names the isoform the row claims"). So "major substrate of CYP3A4" and "metabolized by
# CYP3A4" both shipped a green check on the tier, though only one of them states it, and
# the tier is what the interaction rows are read through (a major substrate meeting a
# strong inhibitor is the pair that matters). Keyed by the ``ENZYME_STRENGTHS`` value.
ENZYME_STRENGTH_WORDS: dict[str, str] = {
    "major": r"\bmajor|\bprimar(?:y|ily)|\bprincipal",
    "minor": r"\bminor",
    # "potent" is the word the prose overwhelmingly uses where the regulatory tables say
    # "strong"; the other two tiers have no such synonym in the corpora.
    "strong": r"\bstrong|\bpotent",
    "moderate": r"\bmoderate",
    "weak": r"\bweak",
}

_TRANSMITTER_RE = {k: re.compile(v, re.IGNORECASE) for k, v in TRANSMITTER_WORDS.items()}
_SIGN_RE = {k: re.compile(v, re.IGNORECASE) for k, v in SIGN_WORDS.items()}
_STRENGTH_RE = {k: re.compile(v, re.IGNORECASE)
                for k, v in ENZYME_STRENGTH_WORDS.items()}


def _claim(sources: list[dict[str, Any]], pattern: re.Pattern) -> dict[str, Any]:
    """Grade one sub-claim against the pathway's own sources.

    Parameters
    ----------
    sources
        The pathway's ``sources`` list, still inline ``{corpus, page, quote,
        provenance}`` dicts at post-pass time (the quote table externalizes them later).
    pattern
        The closed-vocabulary word test for the claimed value.

    Returns
    -------
    dict
        ``{"grade": ...}`` plus a ``sources`` list of **only** the quotes that name the
        claim, so the pill shows the sentence that backs this part and not a neighbour's.
    """
    hits = [s for s in sources or [] if pattern.search(s.get("quote") or "")]
    entry: dict[str, Any] = {"grade": BASE_GRADE}
    if hits:
        entry["sources"] = [dict(s) for s in hits]
        entry["grade"] = max((s.get("provenance", BASE_GRADE) for s in hits),
                             key=lambda g: _GRADE_RANK.get(g, 0))
    return entry


def apply_projection_claims(projections: list[dict[str, Any]]) -> None:
    """Attach each pathway's per-claim grades, in place.

    Raises
    ------
    KeyError
        When a pathway names a transmitter this module has no word test for: a new
        system must declare how a sentence would attest it, or every one of its arrows
        would silently publish an unattestable claim.
    """
    for p in projections:
        nt = p.get("neurotransmitter")
        # ``neurotransmitter`` is bilingual by now (``_t`` wraps it before this pass);
        # the word test keys on the English side, the only one the corpora are written in.
        name = nt.get("en") if isinstance(nt, dict) else nt
        sources = p.get("sources") or []
        claims: dict[str, Any] = {}
        if name:
            if name not in _TRANSMITTER_RE:
                raise KeyError(
                    f"projection {p.get('from')!r} -> {p.get('to')!r} carries "
                    f"neurotransmitter {name!r}, which has no TRANSMITTER_WORDS entry. "
                    f"Add the word(s) a source sentence would name it by, or its "
                    f"transmitter claim can never be attested.")
            claims["transmitter"] = _claim(sources, _TRANSMITTER_RE[name])
        sign = KIND_TO_SIGN.get(p.get("kind"))
        if sign in _SIGN_RE:
            claims["sign"] = _claim(sources, _SIGN_RE[sign])
        if claims:
            p["claims"] = claims


def pattern_for(claim: str, value: str) -> re.Pattern | None:
    """The word test one sub-claim's value is attested by, or None when it has none.

    The public read of the two tables above, so ``check_data.py`` family 5 can re-run the
    very test that graded an emitted claim (the gate against a hand-edited or stale
    ``claims`` block) without restating the vocabulary and letting the two drift.

    Parameters
    ----------
    claim
        The key under a node's ``claims``: ``"transmitter"`` / ``"sign"`` on a
        projection, ``"strength"`` on a drug's enzyme row.
    value
        The claimed value: the English transmitter name, the sign, or the tier.

    Returns
    -------
    re.Pattern or None
        None for an unknown claim name or a value outside the closed vocabulary (a
        modulatory "sign", say), which is the caller's cue that there is nothing to
        attest rather than something that failed to attest.
    """
    table = {"transmitter": _TRANSMITTER_RE, "sign": _SIGN_RE,
             "strength": _STRENGTH_RE}.get(claim)
    return table.get(value) if table else None


def apply_enzyme_strength_claims(drugs: list[dict[str, Any]]) -> None:
    """Attach each metabolism row's strength claim, in place.

    The metabolism twin of :func:`apply_projection_claims`, and the same shape of fix: a
    row with no tier makes no claim and gets no node (like a modulatory pathway's absent
    sign), while a row that states one is graded by whether a quote it already cites uses
    that tier's word.

    Its known over-reach is the mirror-image of the projection one and worth naming: a
    single sentence often lists several isoforms at different tiers ("CYP1A2, CYP2D6;
    minor: CYP2C19, CYP3A4"), and the word test cannot tell which isoform a tier word is
    attached to, so a row cited on such a sentence can attest off its neighbour's word.
    The bound is the same, too: it can only ever hand the sub-claim the grade the enzyme
    row already carried.
    """
    for drug in drugs:
        for row in drug.get("enzymes") or []:
            strength = row.get("strength")
            if not strength:
                continue
            pattern = _STRENGTH_RE.get(strength)
            if pattern is None:
                raise KeyError(
                    f"drug {drug.get('id')!r} enzyme row {row.get('enzyme')!r} claims "
                    f"strength {strength!r}, which has no ENZYME_STRENGTH_WORDS entry. "
                    f"Add the word(s) a source sentence would state that tier by, or it "
                    f"can never be attested.")
            row["claims"] = {"strength": _claim(row.get("sources") or [], pattern)}
