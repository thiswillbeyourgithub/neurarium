"""The rules the binding-gap pass shares between its fetcher and its applier.

The gap pass (``tools/fetch/fetch_binding_gaps.py`` -> one LLM pass ->
``tools/sourcing/apply_binding_gaps.py``) looks for a **missing** binding: a drug whose
stored English Wikipedia article (corpus #9) says it acts on a modeled target the drug
carries no binding for. The fetcher uses these predicates to decide what to offer, the
applier re-runs the very same ones to decide what to accept, so the gate can never let
through what the worklist would not have shown (and a test pins both halves at once).

Lives in ``tools/`` beside ``target_aliases.py`` / ``chirality.py`` because the applier
must stay stdlib-only while the fetcher is a ``uv run`` script pulling bs4 in through
``fetch_metabolite_bindings``.

Built with the help of Claude Code.
"""
from __future__ import annotations

import os
import re
import sys

# tools/fetch, for fetch_ki (a script still owning COARSE_MEMBERS); tools/ itself is
# already on the path of any caller that can import ``lib``.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fetch"))

from lib import chirality  # noqa: E402  (the optical-rotation tag grammar, read not re-invented)
from lib import target_aliases as ta  # noqa: E402
from lib.corpora import wikipedia as wikistore  # noqa: E402  (stored-page lookup, stdlib)
from lib.drugs_io import is_combination  # noqa: E402
from data_generators.drugs import DRUG_TARGETS  # noqa: E402  (the receptor groups)
from fetch_ki import COARSE_MEMBERS  # noqa: E402  (stdlib module)

# A cue that the clause holding the target mention denies the action rather than
# claims it: "has no affinity for H1", "does not bind D2", "unlike clozapine, it lacks
# 5-HT2A antagonism", "negligible activity at M1". Read per clause (see `negated`), so
# "a D2 antagonist; it has no affinity for H1" still offers its D2 half.
NEGATION_RE = re.compile(
    r"\b(no|not|nor|none|neither|lacks?|lacking|devoid|unlike|negligible|"
    r"insignificant|without|inactive|fails?\s+to|absence|absent|minimal|"
    r"does\s*n[o']t|doesn't|did\s*n[o']t|cannot|unclear|unknown|"
    r"may|might|could|possibly|hypothes\w*|speculat\w*|proposed|suggested)\b", re.I)

# Where one clause ends: a sentence can hold a claim and a denial joined this way
# ("a D2 antagonist; it has no affinity for H1"), and the denial says nothing about the
# target the other clause names. Commas and brackets are deliberately NOT breaks: a
# list "negligible affinity (>10,000 nM) for the D1, D5 and H1 receptors" denies every
# target it enumerates, so cutting it at a comma would offer D5 and H1 as claims.
# One exception: a ")" followed by a capitalised word is where a stored list item runs on
# into the next paragraph with no full stop between them ("Nonselective mACh receptor
# antagonist ( anticholinergic , 58% as potent as atropine) Various monographs ... have
# proposed ..."), so the next paragraph's hedge does not reach back into the item.
CLAUSE_SPLIT_RE = re.compile(
    r";|\b(?:but|whereas|while|although|though|however)\b|(?<=\))\s+(?=(?-i:[A-Z][a-z]))", re.I)

# An explicit stereo descriptor in prose, "(S)-ketamine", "(+)-nicotine", "(R,S)-",
# reusing the PDSP / GtoPdb tag grammar `chirality` reads (rotation signs), plus the
# CIP letters prose uses where a database writes a sign. Case-sensitive: CIP letters
# are capitals, and a lower-case "(s)" is a plural ("the receptor(s) involved").
STEREO_TAG_RE = re.compile(
    r"(?:" + chirality.TAG + r"|\(\s*(?:[RS]|R\s*,\s*S|S\s*,\s*R)\s*\))\s*-?\s*[A-Za-z]")


# The French RCP section 5.1 input (corpus #24 ``bdpm_rcp``): the same two cues, read
# on ``target_aliases.fold``-ed text (accents gone, so "négligeable" is "negligeable").
# "faible" (weak) is deliberately not a cue: a weak activity is still a stated one. A bare
# "non" is no cue either ("agoniste non sélectif des récepteurs µ, δ et κ" is a claim),
# only "non anti..." ("neuroleptique non anticholinergique").
FR_NEGATION_RE = re.compile(
    r"(?<![a-z])(?:n['\u2019]|ne|pas|aucune?|sans|absence|nulle?|negligeables?|non[ -]anti\w*|"
    r"pourrai\w*|semble\w*|probablement|hypothes\w*|contrairement)(?![a-z])")
# No ";" here, unlike `CLAUSE_SPLIT_RE`: a label runs one denial over a ";" list ("peu ou
# pas d'effet sur les récepteurs 5-HT2 ; sur les récepteurs alpha1, alpha2 ...").
# A sentence end is a break: an RCP unit is a whole paragraph, so without it the "Il
# n'altère donc pas la motilité" after a glycine-receptor claim would deny that claim.
FR_CLAUSE_SPLIT_RE = re.compile(
    r"(?<![a-z])(?:mais|alors que|tandis que|cependant|toutefois|en revanche)(?![a-z])"
    r"|(?<=[a-z0-9)])\.\s+")

# The class words a French label names a receptor family by. Most name no subtype
# ("antidopaminergique", "anticholinergique (atropinique)"), hence the receptor-group
# targets (`GROUP_MEMBERS`); the English aliases still apply on top ("D2", "5-HT2A").
# Kept explicit like ``target_aliases.EXTRA_ALIASES``: a missing word costs a candidate,
# an invented one lets a sentence about something else through.
FR_ALIASES: dict[str, list[str]] = {
    "dopamine": ["antidopaminergique", "antidopaminergiques", "récepteurs dopaminergiques",
                 "récepteurs de la dopamine"],
    "muscarinic": ["anticholinergique", "anticholinergiques", "atropinique", "atropiniques",
                   "antimuscarinique", "antimuscariniques", "récepteurs muscariniques",
                   "parasympatholytique", "parasympatholytiques"],
    "alpha1": ["alpha-1 adrénergique", "alpha-1 anti-adrénergique", "adrénolytique",
               "adrénolytiques"],
    "h1": ["antihistaminique", "antihistaminiques", "anti-histaminergique",
           "récepteurs histaminiques H1"],
    "sert": ["recapture de la sérotonine"],
    "net": ["recapture de la noradrénaline"],
    "dat": ["recapture de la dopamine"],
    "glycine": ["récepteurs glycinergiques", "récepteur glycinergique"],
    "nav": ["canal sodique", "canaux sodiques"],
    "cav": ["canal calcique", "canaux calciques"],
}
# "adrénolytique" names the adrenoceptors at large; a label means α1 by it only when it
# says so, or names the orthostatic hypotension α1 blockade causes.
_ALPHA1_CUE = re.compile(r"alpha|orthostati")
_ADRENOLYTIC = ["adrénolytique", "adrénolytiques"]


WIKI_CORPUS = "wikipedia_pharm"  # the English input (corpus #9)
RCP_CORPUS = "bdpm_rcp"         # the French input (corpus #24, RCP section 5.1)


def line_aliases(target: str, english: list[str], line: str, corpus: str) -> list[str]:
    """The aliases ``target`` goes by in ``line``: the English ones, plus on the French
    input its class words (`FR_ALIASES`; a subtype is written the same in both languages),
    "adrénolytique" counting for α1 only beside an `_ALPHA1_CUE`."""
    if corpus != RCP_CORPUS:
        return english
    aliases = FR_ALIASES.get(target, []) + english
    if target == "alpha1" and not _ALPHA1_CUE.search(ta.fold(line)):
        aliases = [a for a in aliases if a not in _ADRENOLYTIC]
    return aliases


def claims_target(line: str, target: str, english: list[str], corpus: str) -> bool:
    """Whether ``line`` names ``target`` in a clause neither negated nor hedged: the one
    test the fetcher offers with and the applier gates with, per input language."""
    aliases = line_aliases(target, english, line, corpus)
    return ta.mentions(line, aliases) and not negated(line, aliases, corpus == RCP_CORPUS)


def covered(drug: dict, corpus: str) -> set[str]:
    """`bound_targets` for one input. On the RCP a class word may add its receptor group
    over subtypes that only rest on a Ki-less (vague) source, so there a group counts as
    covered only by a measured subtype."""
    return bound_targets(drug, group_needs_ki=corpus == RCP_CORPUS)


def clauses(line: str, french: bool = False) -> list[str]:
    """The clauses of one sentence, in order (empty pieces dropped)."""
    if french:
        line = ta.fold(line)
    return [c for c in (FR_CLAUSE_SPLIT_RE if french else CLAUSE_SPLIT_RE).split(line)
            if c and c.strip()]


def negated(line: str, aliases: list[str], french: bool = False) -> bool:
    """Whether every clause naming the target carries a negation / hedge cue.

    True also when no clause names it (the alias straddled a clause break): then no
    clause can be read as a positive claim about the target, so it is not offered.
    ``french`` reads the cues of the RCP input (`FR_NEGATION_RE`).
    """
    naming = [c for c in clauses(line, french) if ta.mentions(c, aliases)]
    cue = FR_NEGATION_RE if french else NEGATION_RE
    return not naming or all(cue.search(c) for c in naming)


def _names(drug: dict) -> tuple[set[str], set[str]]:
    """``(own, other)`` prose names of one drug: what its own article calls it, and what
    a stereo relative's article would call it.

    The article title is always the drug's own name ("dexmethylphenidate"). The display
    name counts as its own only when unqualified: "Methylphenidate (D)" is the
    d-enantiomer, so on another article its stem "Methylphenidate" names the racemate.
    """
    path = wikistore.page_for(drug)
    title = os.path.splitext(os.path.basename(path))[0].replace("_", " ") if path else ""
    name = drug.get("name") or drug["id"]
    stem = name.split("(")[0].strip()
    own = {n.lower() for n in (title, name if stem == name else "") if n}
    return own, own | {stem.lower()}


def stereo_siblings(drug: dict, roster: list[dict]) -> list[str]:
    """The names a stereo relative of this drug goes by in prose, never its own.

    One name holding the other ("ketamine" in "esketamine", "Methylphenidate (D)" in
    "Methylphenidate (D,L)", "modafinil" in "armodafinil") is how an enantiomer and its
    racemate are named, so a sentence on one's article naming the other is about a
    different molecule (the false ``verified`` ``CLAUDE.local.md`` forbids for
    PDSP/GtoPdb joins). Combos and the drug itself are skipped. On the
    dexmethylphenidate article this yields ``["methylphenidate"]``; on the
    methylphenidate one ``["dexmethylphenidate"]``.
    """
    fold = lambda d: re.sub(r"[^a-z]", "", (d.get("name") or d["id"]).lower())  # noqa: E731
    me = fold(drug)
    own, _ = _names(drug)
    out: set[str] = set()
    for other in roster:
        it = fold(other)
        if other["id"] == drug["id"] or is_combination(other):
            continue
        if min(len(it), len(me)) >= 6 and it != me and (me in it or it in me):
            out |= _names(other)[1] - own
    return sorted(out)


def stereo_mixed(line: str, siblings: list[str]) -> bool:
    """Whether a sentence names a stereo sibling or carries an explicit stereo tag."""
    if STEREO_TAG_RE.search(line):
        return True
    folded = ta.fold(line)
    return any(re.search(rf"(?<![a-z]){re.escape(ta.fold(s))}(?![a-z])", folded)
               for s in siblings)


def _group_members() -> dict[str, set[str]]:
    """``{group target: its subtypes}``: `fetch_ki.COARSE_MEMBERS` plus every authored
    ``receptor_group`` (muscarinic, alpha1, dopamine, ...)."""
    out = {k: set(v) for k, v in COARSE_MEMBERS.items()}
    for tid, rec in DRUG_TARGETS.items():
        if rec.get("type") == "receptor_group" and rec.get("subtypes"):
            out.setdefault(tid, set()).update(rec["subtypes"])
    return out


GROUP_MEMBERS = _group_members()


def bound_targets(drug: dict, group_needs_ki: bool = False) -> set[str]:
    """Every target the drug already covers: its bindings plus their group relatives.

    A drug binding the coarse ``alpha2`` already says what an ``alpha2a`` sentence would
    add, and one binding ``alpha2a`` makes a coarse ``alpha2`` row redundant, so both
    directions of :data:`GROUP_MEMBERS` count as covered.

    ``group_needs_ki`` (the French RCP input, whose class words name a group, never a
    subtype): a group counts as covered by its subtypes only when one of them carries a
    measured Ki. Tropatepine's m1-m5 rest on one vague "anticholinergic" sentence, so
    the RCP's "anticholinergique" is still a claim worth adding as ``muscarinic``, while
    a drug with an M1 Ki already says it.
    """
    rows = [b for b in drug.get("bindings", []) if b.get("target")]
    bound = {b["target"] for b in rows}
    measured = {b["target"] for b in rows if b.get("ki")}
    out = set(bound)
    for group, members in GROUP_MEMBERS.items():
        if group in bound:
            out |= members
        if (measured if group_needs_ki else bound) & members:
            out.add(group)
    return out


def is_stahl(drug: dict) -> bool:
    """Whether the drug has a Stahl monograph (any field cites corpus #1).

    CLAUDE.md: a Stahl drug's own bindings are strictly dump-sourced, so the applier
    tallies a gap it adds there apart (it can only add a target Stahl does not list).
    """
    def cites(o) -> bool:
        if isinstance(o, dict):
            return o.get("corpus") == "stahl" or any(cites(v) for v in o.values())
        if isinstance(o, list):
            return any(cites(v) for v in o)
        return False
    return cites(drug)


def offerable(drug: dict) -> bool:
    """A combo's pharmacology is its constituents' (named "A + B", or a salt declaring
    ``constituents``), a prodrug's its metabolite's: neither carries own bindings, so
    neither can have a gap of its own."""
    return not (is_combination(drug) or drug.get("constituents")
                or drug.get("prodrug"))
