"""Node walks shared by the grade family (4) and the quote family (5), and by
freshness (13).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

# The drug + its formulations, the holders of brands / Tmax / T½ (one walker, so the
# grade and quote walks cannot skip a formulation's claims).
from data_generators.provenance import product_holders
from data_generators.provenance_stats import own_targets


# The per-drug physicochemistry citations (kinds drug_lipophilicity / drug_polar_surface /
# drug_bbb, data_generators/physchem.py).
PHYSCHEM_SOURCES = ("xlogp_sources", "tpsa_sources", "bbb_sources")


def holder_ctxs(ctx, drug):
    """``(context label, holder)`` for the drug and each of its formulations."""
    return [(ctx if h is drug else f"{ctx} formulation {h.get('release')}", h)
            for h in product_holders(drug)]


def _listed(ctx, sources, short_ok, facet, owner):
    for i, src in enumerate(sources or []):
        yield f"{ctx}[{i}]", src, short_ok, facet, owner


def iter_drug_sources(drug):
    """THE walk over every quote-level citation a drug record carries, shared by the
    grade family (4) and the quote family (5) so a facet added here is both graded and
    quote-gated. Yields ``(ctx, source, short_ok, facet, owner)``: ``short_ok`` when the
    quote is short by design (a class label, one table cell, a brand name, a
    ``Label: value`` line), ``facet`` names the collection and ``owner`` is the record
    holding the list (a binding, an enzyme row, a withdrawal, ...)."""
    did = f"drug {drug.get('id')}"
    for b in drug.get("bindings", []) or []:
        yield from _listed(f"{did} binding {b.get('target')} sources", b.get("sources"),
                           False, "binding", b)
    yield from _listed(f"{did} nbn_sources", drug.get("nbn_sources"), False, "nbn", drug)
    # A class quote is the class label itself ("Stimulant"): short by design.
    yield from _listed(f"{did} category_sources", drug.get("category_sources"), True,
                       "category", drug)
    # The molecule and each formulation: a release read off a brand's own suffix cites
    # that brand ("Seroquel XR"), a duration is one labelled cell ("Half-life 10 hours").
    for hctx, h in holder_ctxs(did, drug):
        for f in ("half_life_sources", "tmax_sources", "release_sources"):
            yield from _listed(f"{hctx} {f}", h.get(f), True, f, h)
        for br in h.get("brands", []) or []:
            yield from _listed(f"{hctx} brand {br.get('name')} sources", br.get("sources"),
                               True, "brand", br)
    for f in ("first_approval_sources", "prodrug_sources", "constituents_sources",
              "therapeutic_range_sources", "alert_level_sources"):
        yield from _listed(f"{did} {f}", drug.get(f), False, f, drug)
    # A PubChem quote is one short `Label: value` line by design ("XLogP3: 3.2").
    for f in PHYSCHEM_SOURCES:
        yield from _listed(f"{did} {f}", drug.get(f), True, f, drug)
    for wi, w in enumerate(drug.get("withdrawals", []) or []):
        yield from _listed(f"{did} withdrawals[{wi}] sources", w.get("sources"), False,
                           "withdrawal", w)
    # A workup quote can be one RCP bullet under its heading ("Ionogramme sanguin,
    # numeration et formule sanguine."), so it may be short by design.
    for wi, w in enumerate(drug.get("workup", []) or []):
        yield from _listed(f"{did} workup[{wi}] sources", w.get("sources"), True,
                           "workup", w)
    # Holder names are short register strings ("holder: UCB PHARMA"), by design.
    for h in drug.get("holders", []) or []:
        yield from _listed(f"{did} holders[{h.get('market')}] sources", h.get("sources"),
                           True, "holder", h)
    for f in ("originator_sources", "originator_now_sources", "originator_country_sources"):
        yield from _listed(f"{did} {f}", drug.get(f), False, f, drug)
    # One cell of the drug's own metabolism table ("Inhibits CYP2D6").
    for e in drug.get("enzymes", []) or []:
        yield from _listed(f"{did} enzyme {e.get('enzyme')} sources", e.get("sources"),
                           True, "enzyme", e)
    # The per-parent half of a metabolite: "X is a metabolite of <did>" + the enzymes
    # making it from <did>. Its molecule facts are walked once, off metabolites.jsonl.
    for m in drug.get("metabolites", []) or []:
        mid = f"{did} metabolite {m.get('id')}"
        yield from _listed(f"{mid} sources", m.get("sources"), False, "metabolite", m)
        for fb in m.get("formed_by", []) or []:
            yield from _listed(f"{mid} formed_by {fb.get('enzyme')} sources",
                               fb.get("sources"), False, "formed_by", fb)


def unknown_stamps(drugs, metabolites=(), receptors=(), meta=None):
    """Every emitted UNKNOWN stamp, as ``(where, kind, claim, stamp)``: a drug or
    metabolite binding direction (kind ``drug_binding_action``, claim = the binding),
    or a receptor's / non-receptor target's effects (kind ``receptor_effect``, claim =
    the owner record). See data_generators/unknown.py."""
    owners = [(f"drug {d.get('id')}", d) for d in drugs] + [
        (f"metabolite {m.get('id')}", m) for m in metabolites]
    for label, owner in owners:
        for b in owner.get("bindings", []) or []:
            if b.get("unknown"):
                yield (f"{label} binding {b.get('target')}", "drug_binding_action", b,
                       b["unknown"])
    effect_owners = [(f"receptor {r.get('id')}", r) for r in receptors] + [
        (f"target {tid}", t)
        for tid, t in own_targets((meta or {}).get("drug_targets") or {}).items()]
    for label, owner in effect_owners:
        if owner.get("effects_unknown"):
            yield f"{label} effects", "receptor_effect", owner, owner["effects_unknown"]
