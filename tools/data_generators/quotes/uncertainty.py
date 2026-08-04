"""Why a `verified` claim still deserves doubt (the ``uncertainty`` bullets).

A `verified` grade only ever meant "this sentence really is on that page". It never meant
"this sentence is *about this drug*", nor "this sentence is about *this* receptor", nor
"this sentence is about *this* region". Three shapes where the difference matters, all
**derived** here rather than hand-listed:

1. **The subject-less side-effect rule.** Stahl's **How Drug Causes Side Effects** block
   prints mechanism-to-side-effect rules whose grammatical subject is the *mechanism*, not
   the drug, so nothing in the sentence says this drug has the action::

       "Blockade of alpha adrenergic 1 receptors may explain dizziness, sedation, and
        hypotension"

   The block is identified by the quote's own **heading trail** (see
   ``tools/fetch/fetch_quote_headers.py``), which is exactly what headings were resolved
   for; the subject test is :func:`_attributes_to_drug`.

2. **The family-level claim.** The source names a receptor *family* ("alpha 1 adrenergic
   receptors", "muscarinic receptors") and we publish its **subtypes** (alpha1A/B/D,
   M1-M5): one sentence covering several of a drug's bindings without naming any of them
   is a family claim by construction, and the split into subtypes is our reading, not the
   book's. On its own that is bearable when a measured Ki pins the subtype down; it is a
   real reason to doubt when it does not (nortriptyline has an alpha1A assay, nothing for
   alpha1B or alpha1D, and Stahl only ever wrote "alpha 1").

3. **The blanket pathway claim.** The projection twin of shape 2. The anatomy books
   describe the diffuse ascending systems by their *sweep*, not target by target::

       "These neurons project to virtually every part of the neuraxis"
       "the sole source of histaminergic actions in the entire brain, from the cerebral
        cortex to the spinal cord"

   One such sentence is the source for many arrows out of one nucleus, and it names none
   of their targets: which regions the sweep is drawn to is our reading of it, exactly as
   the subtype split is in shape 2. Same ``>= 2 siblings, none named`` construction as
   :func:`_family_groups`, over the regions instead (:func:`_blanket_groups`).

Those claims are kept, on evidence rather than convenience (the side-effect lines are
printed selectively, only on monographs that genuinely carry the property, half the
bindings carry an independent measured Ki, and a sweep sentence is a real anatomical
statement about a real system). But a flat green check overstates them, so they carry an
**uncertain** badge instead: same source, same quote, plus the reasons to doubt it, each
reason itself a badged, quote-gated claim.

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

# A modeled receptor subtype ends in the letter or digit that distinguishes it from its
# siblings (alpha1**a**, m**3**, 5ht2**c**); dropping it gives the family stem the source
# would have named.
_SUBTYPE_SUFFIX = re.compile(r"[a-e]$|[0-9]$")

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
    # "One sentence covers n receptor subtypes at once, so it names the family and the
    # split is ours." Cited on that sentence, which is its own evidence.
    "family_claim": {"source": "own_quote", "absence": False, "args": ("n",)},
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
    # "One sentence covers n pathways out of this structure at once and names none of
    # their targets." The projection twin of family_claim (see shape 3 in the module
    # docstring).
    "blanket_claim": {"source": "own_quote", "absence": False, "args": ("n",)},
}


def _english(value: Any) -> str:
    """A display string that may still be an authored ``{en, fr}`` pair."""
    if isinstance(value, dict):
        return str(value.get("en") or "")
    return str(value or "")


def _tokens(text: str) -> str:
    """``text`` reduced to space-separated alphanumeric tokens, space-padded.

    Matching happens on tokens rather than raw substrings because "alpha 1 adrenergic"
    contains the letters of "alpha1a" once punctuation is stripped, and that false
    positive is exactly the family claim this module exists to catch."""
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


def _designations(target: str) -> set[str]:
    """The tokens by which a source would be naming **this** subtype.

    Its own id (``mt1``, ``5ht2a``, ``gaba_a`` -> "gaba a") and its family-relative
    designation: the bare digit for a numbered subtype (``m3`` -> ``3``, as in
    "muscarinic 3"), the family's number plus the letter for a lettered one (``alpha1a``
    -> ``1a``, as in "alpha 1A"). Tokenized like the quote it will be searched in, so an
    id carrying punctuation still matches the prose spelling.
    """
    out = {target}
    m = _SUBTYPE_SUFFIX.search(target)
    if m:
        suffix, stem = m.group(0), target[:m.start()]
        if suffix.isdigit():
            out.add(suffix)
        else:
            number = re.search(r"(\d+)$", stem)
            out.add(number.group(1) + suffix if number else suffix)
    # Both spellings: spaced ("gaba a") and glued ("gabaa"), because prose writes an id's
    # separator either way and a missed spelling would publish a false family claim.
    return ({_tokens(d).strip() for d in out}
            | {re.sub(r"[^a-z0-9]", "", d.lower()) for d in out})


def _family_groups(drug: dict[str, Any]) -> dict[int, tuple[int, dict[str, Any]]]:
    """``binding index -> (family size, the shared source)`` for this drug's family claims.

    A family claim is a group of the drug's bindings that (a) share **one** source quote,
    (b) are subtypes of one family (same stem once the distinguishing suffix is dropped),
    and (c) are **not** named individually in that quote. (c) is what separates "Blocks
    serotonin 2A, 2C, and 3 receptors" (three claims, each stated) from "Blockade of alpha
    adrenergic 1 receptors" (one claim, three subtypes of our own making).
    """
    bindings = drug.get("bindings", [])
    by_quote: dict[str, list[int]] = collections.defaultdict(list)
    source_of: dict[tuple[int, str], dict[str, Any]] = {}
    for i, b in enumerate(bindings):
        for src in b.get("sources", []):
            if not src.get("quote"):
                continue
            qid = quote_table.quote_id(src)
            by_quote[qid].append(i)
            source_of[(i, qid)] = src

    out: dict[int, tuple[int, dict[str, Any]]] = {}
    for qid, idx in by_quote.items():
        if len(idx) < 2:
            continue
        targets = [bindings[i]["target"] for i in idx]
        stems = {_SUBTYPE_SUFFIX.sub("", t) for t in targets}
        if len(stems) != 1 or not stems.pop():
            continue                       # not one family (or no stem left at all)
        quote = _tokens(source_of[(idx[0], qid)]["quote"])
        if any(f" {d} " in quote for t in targets for d in _designations(t)):
            continue                       # the sentence names them one by one
        for i in idx:
            out[i] = (len(set(targets)), source_of[(i, qid)])
    return out


def _uncertainty_bullet(kind: str, *, what: str, node: dict[str, Any] | None = None,
                        source: dict[str, Any] | None = None,
                        args: dict[str, Any] | None = None) -> dict[str, Any]:
    """One ``uncertainty`` bullet: a reason kind, its slot args, and its own source.

    ``node`` is the doubted node (a drug binding, a projection): only the ``ki`` kinds
    read anything off it, so a node kind that has no Ki simply never uses them.

    Where the source comes from is declared by the kind, not by the caller (see
    :data:`UNCERTAINTY_REASONS`), so a bullet cannot cite the wrong thing:

    * ``own_quote`` cites the passed ``source`` (the very sentence the bullet is a
      reading of), so the bullet inherits its grade and its quote gate;
    * ``ki`` reuses the node's measured-affinity source;
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
        src = ((node or {}).get("ki") or {}).get("source")
    else:
        src = None
    if not src:
        raise ValueError(
            f"{what} uncertainty bullet {kind!r} resolves to no source "
            f"(it cites {spec['source']!r}, which this node does not carry). "
            f"Every bullet must be sourced or declare absence=True.")
    out["sources"] = [dict(src)]
    return out


def apply_binding_uncertainty(drugs: list[dict[str, Any]]) -> None:
    """Derive and attach the ``uncertainty`` bullets to every doubtful binding, in place.

    Run as a post-pass over the assembled drugs rather than inside ``_binding_record``,
    because two of the bullets look *across* bindings: ``class_wide`` counts the drugs the
    same sentence is printed on, and ``family_claim`` needs the sibling bindings the same
    sentence covers. No single binding can see either.

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
        families = _family_groups(drug)
        for i, b in enumerate(drug.get("bindings", [])):
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
            family = families.get(i)
            # A family claim on its own is bearable when a measured affinity pins the
            # subtype down (prazosin's alpha1A/B/D are each assayed); it is a reason to
            # doubt when nothing outside that one family-level sentence reaches this
            # subtype. That conjunction is the whole point of the flag.
            family_doubt = bool(family) and not b.get("ki")
            if not rule_source and not family_doubt:
                continue

            bullets = []
            if rule_source:
                bullets.append(_uncertainty_bullet(
                    "side_effect_rule", what=what, node=b, source=rule_source))
            if family:
                bullets.append(_uncertainty_bullet(
                    "family_claim", what=what, node=b, source=family[1],
                    args={"n": family[0]}))
            quoted = rule_source or family[1]
            others = len(spread.get(quoted.get("quote", ""), ())) - 1
            if others > 0:
                bullets.append(_uncertainty_bullet(
                    "class_wide", what=what, node=b, source=quoted,
                    args={"n": others}))
            # The affinity bullet is derived, never authored, so it cannot drift from
            # the Ki actually shipped: it says what the measurement is, or that there
            # is none (which is itself a reason to doubt).
            ki = b.get("ki")
            if ki:
                bullets.append(_uncertainty_bullet(
                    "measured_ki", what=what, node=b,
                    args={"ki": ki["median"],
                          "n": int(ki.get("n_human", 0)) + int(ki.get("n_nonhuman", 0))}))
            else:
                bullets.append(_uncertainty_bullet(
                    "no_measured_ki", what=what, node=b))
            # Only sayable about a drug the book actually covers: "the corpus never lists
            # this among its mechanisms" is a statement about a monograph that exists.
            if in_stahl and not has_mechanism:
                bullets.append(_uncertainty_bullet(
                    "not_a_mechanism", what=what, node=b))
            # Evidence first, absences last: the list reads as "here is what the source
            # does say ... but here is what it never says", which is the shape of the
            # doubt. Stable within each half (the order they were built in).
            bullets.sort(key=lambda bl: bool(bl.get("absence")))
            b["uncertainty"] = bullets


# The words a region's name shares with every other region ("nucleus", "lobe"), which
# therefore designate none of them: a quote saying "nucleus" has not named the nucleus
# basalis. Dropping them leaves the distinguishing word the source would have used.
_REGION_GENERIC = {"nucleus", "nuclei", "lobe", "gland", "cortex", "body", "area",
                   "gyrus", "complex", "formation", "system", "matter"}

# A source writes a region's name in whatever form its sentence needs ("the subthalamus"
# for our subthalamic nucleus, "thalamic" for the thalamus), so designations are matched
# on a shared stem rather than exactly. Six characters is long enough that the pairs the
# atlas actually contains stay apart (caudate / caudal share only four).
_REGION_STEM = 6


def _region_designations(base: str, name: str) -> set[str]:
    """The words a source would use to name the region ``base`` (id + display name).

    Generic anatomical nouns are dropped (see :data:`_REGION_GENERIC`), as are words too
    short to stem-match safely, so what is left is the region's own word: "accumbens",
    "hippocampus", "tuberomammillary".
    """
    words = set(re.split(r"[^a-z0-9]+", base.lower()))
    words |= set(re.split(r"[^a-z0-9]+", _english(name).lower()))
    return {w for w in words if len(w) >= 4 and w not in _REGION_GENERIC}


def _names_region(quote: str, designations: set[str]) -> bool:
    """Does ``quote`` name the region, in any of the forms a book would write it in?"""
    words = [w for w in re.split(r"[^a-z0-9]+", quote.lower()) if len(w) >= 4]
    for d in designations:
        for w in words:
            if w == d:
                return True
            # Same stem = same region ("subthalamus" / "subthalamic"). Only for words
            # long enough that the stem is the region and not a shared prefix.
            common = 0
            for a, b in zip(d, w):
                if a != b:
                    break
                common += 1
            if common >= _REGION_STEM:
                return True
    return False


def _blanket_groups(projections: list[dict[str, Any]],
                    designations: dict[str, set[str]],
                    ) -> dict[int, tuple[int, dict[str, Any]]]:
    """``projection index -> (group size, the shared source)`` for the blanket claims.

    A blanket group is a set of pathways that (a) leave the **same** structure, (b) share
    **one** source sentence, and (c) are each unnamed by it. (c) is what separates "The
    B5-B7 neurons ... provide serotonergic innervation of the thalamus, hypothalamus, and
    cerebral cortex" (the thalamus arrow is stated; the four cortical-lobe arrows are our
    split of "cerebral cortex") from a sentence that lists its targets one by one.

    The group must hold **two** unnamed pathways, mirroring :func:`_family_groups`: one
    sentence covering several targets while naming none of them is a sweep by
    construction, which a single arrow cannot establish.
    """
    named: list[bool] = []
    by_quote: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    source_of: dict[tuple[str, str], dict[str, Any]] = {}
    for i, p in enumerate(projections):
        des = designations.get(_base_id(p["to"]), set())
        hit = False
        for src in p.get("sources") or []:
            quote = src.get("quote")
            if not quote:
                continue
            if _names_region(quote, des):
                hit = True
            key = (p["from"], quote)
            by_quote[key].append(i)
            source_of.setdefault(key, src)
        named.append(hit)

    out: dict[int, tuple[int, dict[str, Any]]] = {}
    for key, idx in by_quote.items():
        unnamed = [i for i in idx if not named[i]]
        if len(unnamed) < 2:
            continue
        for i in unnamed:
            # A pathway cited by two sweep sentences takes the wider one: that is the
            # count a reader should weigh the claim against.
            if i not in out or out[i][0] < len(unnamed):
                out[i] = (len(unnamed), source_of[key])
    return out


def _base_id(structure_id: str) -> str:
    """``accumbens_R`` -> ``accumbens`` (a midline structure has no side suffix)."""
    return re.sub(r"_[RL]$", "", structure_id)


def apply_projection_uncertainty(projections: list[dict[str, Any]],
                                 structures: list[dict[str, Any]]) -> None:
    """Derive and attach the ``uncertainty`` bullets to every blanket pathway, in place.

    A post-pass for the same reason the binding one is: the flag is a statement about the
    *sibling* pathways one sentence covers, which no single projection can see.
    """
    # Keyed by base, so the two members of an L/R pair share one entry (the side is
    # never what a source names). ``base_name`` is the hemisphere-stripped display name;
    # a midline structure carries only ``name``.
    designations = {
        _base_id(s["id"]): _region_designations(
            _base_id(s["id"]), s.get("base_name") or s.get("name"))
        for s in structures}
    groups = _blanket_groups(projections, designations)
    for i, p in enumerate(projections):
        group = groups.get(i)
        if not group:
            continue
        what = f"Projection {p['from']!r} -> {p['to']!r}"
        p["uncertainty"] = [_uncertainty_bullet(
            "blanket_claim", what=what, node=p, source=group[1],
            args={"n": group[0]})]
