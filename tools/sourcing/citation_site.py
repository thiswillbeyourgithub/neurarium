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
    drug:quetiapine/formulations[xr]/brands[Seroquel XR]
    metabolite:desmethyldiazepam/half_life
    drug:diazepam/metabolites[desmethyldiazepam]
    drug:clozapine/bindings[5ht2a:antagonist]
    drug:fluoxetine/enzymes[cyp2d6:inhibitor]
    receptor:5ht1a/classification[family]
    receptor:5ht1a/locations[amygdala]
    receptor:h1/effects[antagonism:sedation]
    receptor:5ht1e/effects
    projection:raphe_R->hippocampus_R

A site with no ``[key]`` names a whole facet of its owner: ``receptor:5ht1e/effects`` is
the address of an owner-level UNKNOWN search (``data_generators/unknown.py``: no searched
source states any effect of acting on it), the facet whose members would otherwise be
``effects[<mode>:<effect>]``.

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


def binding_key(row: dict) -> str:
    """A binding row's key: the target AND the action.

    Seven drugs state two actions on one target (amisulpride antagonises D2 and partially
    agonises it, amphetamine both blocks and reverses DAT), and those are two nodes with
    two sources, so the target alone would address both at once. A binding with no known
    direction (`affinity_only`) has nothing to add and keys on the target alone.
    """
    action = row.get("action")
    return f"{row.get('target')}:{action}" if action else str(row.get("target"))


def enzyme_key(row: dict) -> str:
    """An enzyme row's key: the isoform AND the role.

    A drug can be both a substrate and an inhibitor of the same isoform (that is what
    the autoinhibition addon is about), and those are two nodes with two sources, so the
    isoform alone would address both at once.
    """
    return f"{row.get('enzyme')}:{row.get('role')}"


def withdrawal_key(row: dict) -> str:
    """A market withdrawal's key: where AND when (one drug can leave several markets)."""
    return f"{row.get('country')}:{row.get('year')}"


def workup_key(row: dict) -> str:
    """A workup row's key: the test AND the timing (an ECG before and during are two)."""
    return f"{row.get('test')}:{row.get('timing')}"


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
    # `formulations[RELEASE]/...` is the two-level owner here: everything else hangs
    # directly off the drug. A formulation holds the same brands / tmax / half_life
    # facets as the drug, plus its own `release` claim. A `metabolites[ID]` reference
    # carries only the per-parent identity claim (and, emitted, its `formed_by` rows);
    # the molecule's own facts are addressed `metabolite:<id>/...` (_metabolite_site).
    if rest[0] == "formulations" and len(rest) >= 3:
        inner = ("release" if rest[2] == "release_sources" else _drug_facet(rest[2:]))
        return (site("drug", drug, f"formulations[{rest[1]}]/{inner}")
                if inner else None)
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
    if head == "withdrawals" and len(rest) >= 2:
        return f"withdrawals[{rest[1]}]"
    if head == "holders" and len(rest) >= 2:
        return f"holders[{rest[1]}]"
    # The flat ones: `category_sources`, `nbn_sources`, `half_life_sources`,
    # `tmax_sources`. The site drops the `_sources` suffix, which says how the claim is
    # stored, not what it is.
    return {"category_sources": "categories", "nbn_sources": "nbn",
            "half_life_sources": "half_life", "tmax_sources": "tmax",
            "first_approval_sources": "first_approval",
            "originator_sources": "originator",
            "originator_now_sources": "originator/now",
            "originator_country_sources": "originator_country",
            "prodrug_sources": "prodrug",
            "constituents_sources": "constituents",
            "therapeutic_range_sources": "therapeutic_range",
            "alert_level_sources": "alert_level",
            "xlogp_sources": "xlogp", "tpsa_sources": "tpsa",
            "bbb_sources": "bbb"}.get(head)


def _metabolite_facet(tail: list) -> str | None:
    if not tail:
        return None
    head = tail[0]
    if head in ("bindings", "formed_by") and len(tail) >= 2:
        return f"{head}[{tail[1]}]"
    return {"half_life_sources": "half_life"}.get(head)


def _metabolite_site(path: list) -> str | None:
    """A row of ``tools/data/metabolites_data.jsonl`` (one per molecule), first element
    the metabolite id: ``metabolite:<id>/half_life``, ``metabolite:<id>/bindings[...]``."""
    if len(path) < 2:
        return None
    facet = _metabolite_facet(path[1:])
    return site("metabolite", path[0], facet) if facet else None


def _workup_site(path: list) -> str | None:
    """``workup.json``: ``drugs/<drug>/<test:timing>/sources``."""
    if len(path) < 3 or path[0] != "drugs":
        return None
    return site("drug", path[1], f"workup[{path[2]}]")


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


def _owner_keyed(facet: str):
    """A resolver for a ``<owner>/<node key>`` cache holding receptors and non-receptor
    targets alike (``receptor_effects.json``, ``receptor_demographics.json``): the owner
    kind is read off the receptor roster (lazily: this module otherwise imports nothing)."""
    def resolve(path: list) -> str | None:
        if len(path) < 2:
            return None
        from data_generators.receptors import RECEPTORS
        kind = "receptor" if any(r["id"] == path[0] for r in RECEPTORS) else "target"
        return site(kind, path[0], facet, path[1])
    return resolve


RESOLVERS = {
    "drugs_data.jsonl": _drug_site,
    "metabolites_data.jsonl": _metabolite_site,
    "location_sources.json": _location_site,
    "classification_sources.json": _classification_site,
    "expression_density.json": _density_site,
    "drug_enzymes.json": _drug_enzymes_site,
    "drug_enzymes_wikipedia.json": _drug_enzymes_site,
    "workup.json": _workup_site,
    "receptor_effects.json": _owner_keyed("effects"),
    "receptor_demographics.json": _owner_keyed("demographics"),
    # ``release_modulation.json``: ``<receptor>/<node key>`` (one node per key).
    "release_modulation.json": lambda path: (
        site("receptor", path[0], "release_modulation", path[1]) if len(path) >= 2 else None),
    "enzyme_variability.json": lambda path: (
        site("enzyme", path[1], "variability") if len(path) >= 2 else None),
}


def resolve(root: str, path: list) -> str | None:
    """The site of a source at ``path`` inside the file named ``root``, or ``None``."""
    fn = RESOLVERS.get(root)
    return fn(path) if fn else None


# ---------------------------------------------------------------------------
# The emitted side: site -> the node dict a claim lives on.
#
# The third reader of the grammar: a curated table keyed by site (the ``contradicted``
# entries, ``data_generators/quotes/contradictions.py``) needs the very dict a bullet
# can be attached to, in the generator's in-memory records or in the emitted data
# (the shapes are the same, only the sources differ). Only node-shaped sites are
# listed: a flat ``*_sources`` facet (``half_life``, ``tmax``, ``nbn`` ...) has no dict
# of its own to carry an ``uncertainty`` list, so it is absent here and a table entry
# naming one fails as unresolved rather than landing on the wrong owner.
# ---------------------------------------------------------------------------

def node_index(*, drugs=(), metabolites=(), receptors=(), targets=None,
               projections=(), circuits=(), groups=(), structures=()):
    """``(nodes, ambiguous)``: every node-shaped site -> its dict, plus the sites two
    nodes share (a duplicated binding row), which no entry may name.

    ``targets`` is the ``drug_targets`` map (id -> record). Keys mirror the claim walk
    (``claim_walk.reconstruct_claims``) exactly; ``test_citation_site`` holds them to it.
    """
    # Lazily, like _owner_keyed: the authoring resolvers above need none of it.
    from data_generators import demographics as DEMOG
    from data_generators import release_modulation as RELMOD
    nodes: dict[str, dict] = {}
    ambiguous: set[str] = set()

    def put(s: str, node) -> None:
        if not isinstance(node, dict):
            return
        if s in nodes and nodes[s] is not node:
            ambiguous.add(s)
        nodes[s] = node

    def owner_nodes(kind: str, oid: str, rec: dict) -> None:
        # The facets receptors and non-receptor targets share.
        for e in rec.get("effects") or []:
            put(site(kind, oid, "effects", f"{e['mode']}:{e['effect']}"), e)
        for n in rec.get("demographics") or []:
            put(site(kind, oid, "demographics",
                     DEMOG.node_key(n["factor"], n["direction"], n.get("structure"))), n)

    for d in drugs:
        did = d["id"]
        for b in d.get("bindings") or []:
            put(site("drug", did, f"bindings[{binding_key(b)}]"), b)
        for e in d.get("enzymes") or []:
            key = f"enzymes[{enzyme_key(e)}]"
            put(site("drug", did, key), e)
            put(site("drug", did, f"{key}/strength"), (e.get("claims") or {}).get("strength"))
        for m in d.get("metabolites") or []:
            put(site("drug", did, f"metabolites[{m['id']}]"), m)
            for fb in m.get("formed_by") or []:
                put(site("drug", did, f"metabolites[{m['id']}]/formed_by[{fb['enzyme']}]"), fb)
        for holder in [d, *(d.get("formulations") or [])]:
            fac = f"formulations[{holder['release']}]/" if holder.get("release") else ""
            for br in holder.get("brands") or []:
                put(site("drug", did, f"{fac}brands[{br['name']}]"), br)
            # The duration value dict ({hours, hours_max?}) stands for its node, so a
            # curated contradiction can doubt one T½ / Tmax like any other claim.
            for field in ("half_life", "tmax"):
                put(site("drug", did, f"{fac}{field}"), holder.get(field))
        for w in d.get("withdrawals") or []:
            put(site("drug", did, f"withdrawals[{withdrawal_key(w)}]"), w)
        for w in d.get("workup") or []:
            put(site("drug", did, f"workup[{workup_key(w)}]"), w)
        for h in d.get("holders") or []:
            put(site("drug", did, f"holders[{h['market']}]"), h)
    for m in metabolites:
        for b in m.get("bindings") or []:
            put(site("metabolite", m["id"], f"bindings[{binding_key(b)}]"), b)
    for r in receptors:
        for attr, entry in (r.get("classification") or {}).items():
            put(site("receptor", r["id"], "classification", attr), entry)
        owner_nodes("receptor", r["id"], r)
        for n in r.get("release_modulation") or []:
            where = n.get("site") or {}
            put(site("receptor", r["id"], "release_modulation", RELMOD.node_key(
                kind=n["kind"], structure=where.get("structure"), cell=where.get("cell"),
                modulates=n["modulates"], effect=n["effect_of_activation"])), n)
    for tid, t in (targets or {}).items():
        owner_nodes("target", tid, t)
    for p in projections:
        pid = f"{p['from']}->{p['to']}"
        put(site("projection", pid), p)
        for facet, claim in (p.get("claims") or {}).items():
            put(site("projection", pid, facet), claim)
    for c in circuits:
        put(site("circuit", c["id"]), c)
    for g in groups:
        put(site("group", f"{g['mode']}:{g['key']}"), g)
    for s in structures:
        put(site("structure", s["id"]), s)
    return nodes, ambiguous


def member_label(obj, index: int) -> str:
    """How a list member is named in a path: by what it *is*, not where it sits.

    An index would address a different claim the moment an applier reorders a list, and
    these lists are rewritten by appliers on every refresh, so a site keyed by position
    would rot silently. Every list a source hangs off has a natural key.
    """
    if isinstance(obj, dict):
        if "enzyme" in obj and "role" in obj:
            return enzyme_key(obj)
        if "target" in obj:
            return binding_key(obj)
        if "country" in obj and "year" in obj:
            return withdrawal_key(obj)
        if "test" in obj and "timing" in obj:
            return workup_key(obj)
        for k in ("target", "name", "id", "enzyme", "region", "brand", "release", "market"):
            if isinstance(obj.get(k), str):
                return obj[k]
    return str(index)
