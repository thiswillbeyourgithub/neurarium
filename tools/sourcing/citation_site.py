#!/usr/bin/env python
"""The address of one *citation*, so a verdict can name a claim instead of a quote.

A quote id is a content hash, so one sentence reaching two claims is one id. That is
deliberate (the excerpt table stays deduplicated, and `provenance` / `pipeline` already
ride the citation rather than the quote for exactly this reason), but it leaves the
judging pass with no way to say the useful thing: *this sentence backs the binding and
not the class*. Judged by quote, such a sentence is either kept on a claim it does not
support or stripped off one it does.

A **site** is that missing address: a short, stable, human-readable string naming one
place a quote is cited from.

    drug:brexpiprazole/half_life
    drug:brexpiprazole/metabolites[DM-3411]/half_life
    drug:clozapine/bindings[5ht2a]
    drug:fluoxetine/enzymes[cyp2d6:inhibitor]
    receptor:5ht1a/classification[family]
    receptor:5ht1a/locations[amygdala]
    projection:raphe_R->hippocampus_R

It is written for a reader, not for a parser: a judge is shown one per claim and answers
with the ones that fail, so a site that cannot be read back by a person is useless even
if a program can resolve it.

**Two callers, one grammar, and that is the whole point of this module.**
`recheck_quotes.py` labels each claim it reconstructs out of the *emitted* data, and
`demote_quotes.py` recognizes the same site while walking the *authoring* files, whose
shapes differ (a receptor's regions are nested under the receptor in `receptors.jsonl`
and under a corpus-keyed cache in `location_sources.json`). Writing the grammar once and
resolving it twice is what keeps the two ends from drifting apart into a silent no-op.
Divergence stays loud rather than silent: an applier that is handed a site it never
visited says so instead of skipping it (see ``demote_quotes.py``).

Stdlib only; authoring helper, not served. Built with the help of Claude Code.
"""
from __future__ import annotations


def site(kind: str, owner: str, facet: str | None = None,
         key: str | None = None) -> str:
    """Assemble a site string. The one place its punctuation is decided."""
    out = f"{kind}:{owner}"
    if facet:
        out += f"/{facet}"
        if key:
            out += f"[{key}]"
    return out


def enzyme_key(row: dict) -> str:
    """An enzyme row's key: the isoform AND the role.

    A drug can be both a substrate and an inhibitor of the same isoform (that is what
    the autoinhibition addon is about), and those are two nodes with two sources, so the
    isoform alone would address both at once.
    """
    return f"{row.get('enzyme')}:{row.get('role')}"


# ---------------------------------------------------------------------------
# The authoring side: (file root, path) -> site.
#
# `path` is the sequence of dict keys and list-member labels the walker descended
# through, ending at the key holding the source list. Each resolver below reads only
# what its own file's shape guarantees, and returns None for a path it does not
# recognize, which the caller treats as "not addressable", never as a match.
# ---------------------------------------------------------------------------

def _drug_site(path: list) -> str | None:
    """A row of ``tools/data/drugs_data.jsonl``, whose first element is the drug id."""
    if not path:
        return None
    drug, rest = path[0], path[1:]
    if not rest:
        return None
    # `metabolites[NAME]/...` is the only two-level owner here: everything else hangs
    # directly off the drug.
    if rest[0] == "metabolites" and len(rest) >= 2:
        metab = rest[1]
        tail = rest[2:]
        inner = _metabolite_facet(tail)
        return (site("drug", drug, f"metabolites[{metab}]/{inner}")
                if inner else site("drug", drug, f"metabolites[{metab}]"))
    facet = _drug_facet(rest)
    return site("drug", drug, facet) if facet else None


def _drug_facet(rest: list) -> str | None:
    head = rest[0]
    if head == "bindings" and len(rest) >= 2:
        return f"bindings[{rest[1]}]"
    if head == "enzymes" and len(rest) >= 2:
        return f"enzymes[{rest[1]}]"
    if head == "brands" and len(rest) >= 2:
        return f"brands[{rest[1]}]"
    # The flat ones: `category_sources`, `nbn_sources`, `half_life_sources`. The site
    # drops the `_sources` suffix, which says how the claim is stored, not what it is.
    return {"category_sources": "categories", "nbn_sources": "nbn",
            "half_life_sources": "half_life"}.get(head)


def _metabolite_facet(tail: list) -> str | None:
    if not tail:
        return None
    head = tail[0]
    if head in ("bindings", "formed_by") and len(tail) >= 2:
        return f"{head}[{tail[1]}]"
    return {"half_life_sources": "half_life"}.get(head)


def _owner_kind(bucket: str) -> str:
    """``receptors``/``targets``, the two keys the owner-keyed caches split on."""
    return {"receptors": "receptor", "targets": "target"}.get(bucket, bucket)


def _location_site(path: list) -> str | None:
    """``location_sources.json``: ``<bucket>/<owner>/<region>``."""
    if len(path) < 3:
        return None
    return site(_owner_kind(path[0]), path[1], "locations", path[2])


def _classification_site(path: list) -> str | None:
    """``classification_sources.json``: ``<bucket>/<owner>[/<attribute>]``.

    A receptor splits into four independently graded attributes, so its sources hang off
    one of them; a non-receptor target states a single `type`, so its sources hang off
    the target itself. Both are one claim, so both get a site.
    """
    if len(path) < 2:
        return None
    attr = path[2] if len(path) >= 3 else None
    return site(_owner_kind(path[0]), path[1], "classification", attr)


def _density_site(path: list) -> str | None:
    """``expression_density.json``: ``<bucket>/<owner>/...``, one node per profile."""
    if len(path) < 2:
        return None
    return site(_owner_kind(path[0]), path[1], "density")


def _drug_enzymes_site(path: list) -> str | None:
    """``drug_enzymes*.json``: ``<drug>/<enzyme:role>``."""
    if len(path) < 2:
        return None
    return site("drug", path[0], f"enzymes[{path[1]}]")


RESOLVERS = {
    "drugs_data.jsonl": _drug_site,
    "location_sources.json": _location_site,
    "classification_sources.json": _classification_site,
    "expression_density.json": _density_site,
    "drug_enzymes.json": _drug_enzymes_site,
    "drug_enzymes_wikipedia.json": _drug_enzymes_site,
    "enzyme_variability.json": lambda path: (
        site("enzyme", path[1], "variability") if len(path) >= 2 else None),
}


def resolve(root: str, path: list) -> str | None:
    """The site of a source at ``path`` inside the file named ``root``, or ``None``."""
    fn = RESOLVERS.get(root)
    return fn(path) if fn else None


def member_label(obj, index: int) -> str:
    """How a list member is named in a path: by what it *is*, not where it sits.

    An index would address a different claim the moment an applier reorders a list, and
    these lists are rewritten by appliers on every refresh, so a site keyed by position
    would rot silently. Every list a source hangs off has a natural key.
    """
    if isinstance(obj, dict):
        if "enzyme" in obj and "role" in obj:
            return enzyme_key(obj)
        for k in ("target", "name", "id", "enzyme", "region", "brand"):
            if isinstance(obj.get(k), str):
                return obj[k]
    return str(index)
