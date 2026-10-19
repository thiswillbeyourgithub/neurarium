"""data_generators.provenance_stats: the dataset-wide sourcing tally.

``_provenance_stats`` reduces every emitted node to its strongest grade and buckets
it (verified / uncertain / sourced / llm / nosource / unknown), emitted as
``meta.provenance_stats`` (per kind + the headline). Split out of
data_generators.provenance, which keeps the grade vocabulary and the validators.
"""

from __future__ import annotations

from typing import Any

from lib.drugs_io import is_combination

from . import node_kinds as node_kinds_mod
from .provenance import _GRADE_RANK, DEFAULT_PROVENANCE, product_holders


def own_targets(drug_targets: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The non-receptor drug targets, by id. A receptor-linked target (``type:
    "receptor"``) is already its receptor's node, so every target kind skips it, never
    counting it twice.

    >>> sorted(own_targets({"sert": {"type": "transporter"}, "d2": {"type": "receptor"}}))
    ['sert']
    """
    return {tid: t for tid, t in drug_targets.items()
            if isinstance(t, dict) and t.get("type") != "receptor"}


def _strongest_grade(sources: list[dict[str, Any]] | None) -> int:
    """The strongest provenance rank among a list of source objects (0 if none)."""
    best = 0
    for src in sources or []:
        best = max(best, _GRADE_RANK.get(src.get("provenance"), 0))
    return best


def _binding_grade(binding: dict[str, Any]) -> int:
    """A binding's grade = the strongest of its quote ``sources`` and its ``ki``
    source. A measured Ki (its own verified source) confirms the drug binds the
    target, so it backs the binding claim; an affinity_only binding is graded solely
    by its Ki."""
    best = _strongest_grade(binding.get("sources"))
    ki_src = (binding.get("ki") or {}).get("source")
    if ki_src:
        best = max(best, _GRADE_RANK.get(ki_src.get("provenance"), 0))
    return best


def _binding_action_grade(binding: dict[str, Any]) -> int | str:
    """A binding DIRECTION's grade = the strongest of its quote ``sources`` alone.

    A measured Ki attests that the ligand binds the target, never whether it
    activates or blocks it, so the Ki is deliberately excluded here: an
    ``affinity_only`` binding (a Ki with no known direction) scores 0 and reads as
    NOSOURCE, which is the whole point of splitting this claim out of
    ``_binding_grade``. A direction stated with no document behind it floors at
    ``llm`` (rank 1): it was authored from memory, which is weaker than a quote but
    stronger than nothing at all.
    """
    if not binding.get("action"):
        # Searched everywhere, nothing states it (data_generators/unknown.py): its own
        # bucket, outside the headline denominator.
        return "unknown" if binding.get("unknown") else 0
    return max(1, _strongest_grade(binding.get("sources")))


# The per-drug scalar node kinds: ONE node per drug carrying a truthy ``field``, graded
# by its ``<field>_sources`` (absent field = no claim, not an unsourced node).
# ``per_product`` walks each formulation as well as the molecule (product_holders).
# (kind, field, per_product), with what each node claims:
DRUG_SCALAR_KINDS: tuple[tuple[str, str, bool], ...] = (
    ("drug_nbn", "nbn", False),                    # Neuroscience-based Nomenclature label
    # Elimination T½ (Stahl verbatim; apply_pharmacokinetics.py).
    ("drug_half_life", "half_life", True),
    # Time to peak: its own kind, not a field of the T½ node, since the two are sourced
    # and missing separately and the simulation reads both ends of one curve (apply_tmax.py).
    ("drug_tmax", "tmax", True),
    ("drug_first_approval", "first_approval", False),  # apply_drug_history.py
    ("drug_originator", "originator", False),          # data_generators/origin.py
    ("drug_originator_country", "originator_country", False),
    # "Inactive until metabolised into X"; a drug active itself claims nothing (apply_prodrug.py).
    ("drug_prodrug", "prodrug", False),
    # A salt / combination lending its constituents' bindings; a combo named after its
    # parts carries no such claim.
    ("drug_constituents", "constituents", False),
    # AGNP TDM, corpus #19 (data_generators/tdm.py).
    ("drug_therapeutic_range", "therapeutic_range", False),
    ("drug_alert_level", "alert_level", False),
)


def _provenance_stats(structures: list[dict[str, Any]],
                      projections: list[dict[str, Any]],
                      circuits: list[dict[str, Any]],
                      projection_groups: list[dict[str, Any]],
                      receptors: list[dict[str, Any]],
                      drugs: list[dict[str, Any]],
                      metabolites: list[dict[str, Any]],
                      drug_targets: dict[str, dict[str, Any]],
                      addons: list[dict[str, Any]],
                      enzymes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Programmatic sourcing tally over the dataset's **nodes** (see the Nodes
    section of CLAUDE.md), emitted into ``meta.provenance_stats``.

    A *node* is any sourceable datum: a drug binding, a drug NbN label, a drug class
    classification, a neuron projection, a functional circuit, a projection group, a
    receptor classification, a receptor expression region, a non-receptor target
    classification, a target expression region, or a brain-region anatomy fact. Every
    node is bucketed by the strength of its source: ``verified`` (quote-checked),
    ``sourced`` (from a document, not quote-checked) or ``missing`` (no source
    document at all: an ``llm`` grade means "an LLM asserted this from memory", which
    is precisely *no document*, so it is missing, exactly like a node with no source
    object). The viewer's About panel and the README headline read these numbers, so
    the "% sourced" figure is always a real count of the shipped data, never
    hand-typed (the whole point: a programmatic count of source strength across every
    node).

    The knowledge nodes drive the headline ``pct_backed`` (emitted under the
    ``nodes`` key); Wikipedia ``references`` are tallied separately (read-more links,
    which point *at* a node but are not themselves a knowledge node).
    """
    def bucket(rank_or_grade: Any) -> str:
        # An "uncertain" node is a real quote-checked source that the audit flagged as
        # not attributing the claim (see quotes/uncertainty.py). It carries a document,
        # so it stays *backed* (the headline is unchanged), but it leaves the green
        # verified count: a flat check would overstate it.
        uncertain = False
        if isinstance(rank_or_grade, tuple):
            rank_or_grade, uncertain = rank_or_grade
        if rank_or_grade == "unknown":
            return "unknown"
        rank = (rank_or_grade if isinstance(rank_or_grade, int)
                else _GRADE_RANK.get(rank_or_grade, 0))
        # Only a node resting on a document can be "uncertain": a bare llm claim that
        # another corpus denies (quotes/contradictions.py) is still missing its own
        # source, and the denial must not lift it into the backed headline.
        if uncertain and rank >= _GRADE_RANK["sourced"]:
            return "uncertain"
        # rank 1 = a bare ``llm`` grade (asserted from memory), rank 0 = no source
        # object at all. Both are "missing" (no document), but the viewer renders them
        # differently (grey ``?`` vs orange NOSOURCE), so split them out here too.
        return ("verified" if rank == 3 else
                "sourced" if rank == 2 else
                "llm" if rank == 1 else "nosource")

    def _node_grade(node: dict[str, Any], grade: Any = None) -> tuple[Any, bool]:
        # A (grade, is_uncertain) pair for a node-shaped claim, so a bullet on it (a
        # ``contradicted`` entry can name any node site, quotes/contradictions.py)
        # buckets ``uncertain`` like a binding's. ``grade`` defaults to its sources'.
        return (_strongest_grade(node.get("sources")) if grade is None else grade,
                bool(node.get("uncertainty")))

    def tally(grades: list[Any]) -> dict[str, int]:
        # ``missing`` is kept as the llm+nosource sum (the headline / README / check_data
        # read it); ``llm`` and ``nosource`` are the finer split the sourcing bar renders
        # as distinct grey and red segments.
        # ``unknown`` (searched everywhere, nothing states it; data_generators/unknown.py)
        # is counted beside the total, never in it: it is neither backed nor missing, so
        # it must not move the headline % either way.
        counts = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
                  "llm": 0, "nosource": 0, "missing": 0, "unknown": 0}
        for g in grades:
            b = bucket(g)
            if b == "unknown":
                counts["unknown"] += 1
                continue
            counts["total"] += 1
            counts[b] += 1
            if b in ("llm", "nosource"):
                counts["missing"] += 1
        return counts

    # (grade, is_uncertain) pairs: a flagged binding buckets as ``uncertain`` however
    # strong its quote is (see bucket()).
    binding_grades = [_node_grade(b, _binding_grade(b))
                      for d in drugs for b in d.get("bindings", [])]
    # The binding's DIRECTION, split out as its own node (see _binding_action_grade):
    # "this drug binds this target" and "it does so as an agonist/antagonist" are two
    # claims with two different backings, and only the first one a Ki can attest. One
    # node per binding, so a Ki-only binding reads as a missing direction instead of
    # disappearing into a verified binding. It carries the SAME uncertainty flag as the
    # binding: those bullets are precisely about whether the quote attributes the
    # action to this drug, which is the direction claim and nothing else.
    binding_action_grades = [_node_grade(b, _binding_action_grade(b))
                             for d in drugs for b in d.get("bindings", [])]
    # Measured-affinity (PDSP Ki) coverage: a SEPARATE data-quality signal from the
    # grade tally. A binding can be legitimately backed by a Stahl quote with no Ki
    # (the grade counts it as sourced), so "no Ki" is NOT "unsourced"; this figure
    # instead tracks how much of the corpus carries a *measured* affinity and names the
    # drugs where one was never looked up (the "we didn't even bother to look" case the
    # % sourced can't see). Combo drugs ("A + B") are Ki-exempt by design, so they are
    # excluded here (``drugs_io.is_combination``, which js/data.js's +/–/— test mirrors).
    ki_drugs = [d for d in drugs if d.get("bindings") and not is_combination(d)]
    ki_bindings = [b for d in ki_drugs for b in d["bindings"]]
    with_ki = [b for b in ki_bindings if b.get("ki")]
    drugs_no_ki = [d for d in ki_drugs
                   if not any(b.get("ki") for b in d["bindings"])]
    ki_coverage = {
        "bindings_total": len(ki_bindings),
        "bindings_with_ki": len(with_ki),
        "pct_bindings_with_ki": (round(100 * len(with_ki) / len(ki_bindings))
                                 if ki_bindings else 0),
        "drugs_total": len(ki_drugs),
        "drugs_without_ki": len(drugs_no_ki),
        "drugs_without_ki_ids": sorted(d["id"] for d in drugs_no_ki),
    }
    # The one-claim-per-drug scalar kinds (see DRUG_SCALAR_KINDS), keyed by kind.
    holders = [h for d in drugs for h in product_holders(d)]
    scalar = {kind: tally([_strongest_grade(d.get(f"{field}_sources"))
                           for d in (holders if per_product else drugs) if d.get(field)])
              for kind, field, per_product in DRUG_SCALAR_KINDS}
    # Commercial-brand nodes ("this drug is marketed as <brand>"), one per authored
    # brand across all drugs, graded by that brand's own sources (Stahl for na,
    # Wikipedia for eu/fr; see apply_brand_sources.py).
    # A formulation (drug_formulations) holds the brands / Tmax / T½ a source tied
    # to one release type, in the molecule's own shape: they are the same kinds,
    # tallied wherever they sit (see data_generators/formulations.py).
    brand_grades = [_node_grade(br) for d in holders for br in d.get("brands", [])]
    # Drug class-classification nodes ("this drug is an SSRI/..."), one per drug that
    # has categories: the emitted category_provenance (llm unless overridden/sourced).
    category_grades = [d.get("category_provenance", DEFAULT_PROVENANCE)
                       for d in drugs if d.get("categories")]
    # Formulation nodes ("this drug is sold as an extended-release product"), ONE per
    # formulation, graded by the source naming its release type.
    formulation_grades = [_strongest_grade(f.get("release_sources"))
                          for d in drugs for f in d.get("formulations", [])]
    # Regulatory history: ONE node per market withdrawal (a drug never withdrawn has
    # none: absence is not a claim); see apply_drug_history.py.
    withdrawal_grades = [_node_grade(w) for d in drugs for w in d.get("withdrawals", [])]
    # Who the drug comes from (data_generators/origin.py): ONE holder node per (drug,
    # market).
    holder_grades = [_node_grade(h) for d in drugs for h in d.get("holders", [])]
    # Physicochemistry and brain entry (data_generators/physchem.py): ONE node per drug
    # for each of its computed XLogP3, its computed polar surface and its B3DB label.
    # Not in DRUG_SCALAR_KINDS: presence is key membership (``in``), not truthiness, so
    # a measured 0 still counts.
    physchem_grades = {f: [_strongest_grade(d.get(f"{f}_sources")) for d in drugs if f in d]
                       for f in ("xlogp", "tpsa", "bbb")}
    # Pre-prescription workup (data_generators/workup.py, BETA): ONE node per (drug,
    # test, timing) row the French RCP asks for.
    workup_grades = [_node_grade(r) for d in drugs for r in d.get("workup", []) or []]
    # Drug-metabolism nodes ("<drug> is a substrate of / inhibits / induces <enzyme>"),
    # one per (drug, enzyme, role) row. A pharmacokinetic claim, independent of the
    # drug's receptor bindings: it is what the derived drug -> drug interaction edges
    # in the viewer are built from, so it earns its own kind rather than riding along
    # with the class or half-life node.
    # A (grade, is_uncertain) pair like a binding's: a row another corpus denies buckets
    # as ``uncertain`` however strong its own quote is (quotes/contradictions.py).
    enzyme_grades = [_node_grade(e)
                     for d in drugs for e in d.get("enzymes", [])]
    # HOW MUCH of the clearing that isoform does (major/minor, strong/weak), split out of
    # the row for the same reason a pathway's transmitter is (quotes/attestation.py): the
    # CYP quote gate checks the isoform is named, never the tier. A row stating no tier
    # makes no claim and contributes no node.
    enzyme_strength_grades = [_node_grade(entry, entry["grade"])
                              for d in drugs
                              for e in d.get("enzymes", [])
                              if (entry := (e.get("claims") or {}).get("strength"))]
    # CPIC prescribing guidance (corpus #15), one node per (drug, gene, phenotype) row.
    # Its own kind, not a sub-claim of the enzyme row above, because it is a different
    # kind of statement: the enzyme row says who clears the drug, this says what a
    # person who clears it slowly should expect. Two citations per node (implication,
    # recommendation), so the grade is the strongest of the two, as everywhere else.
    pgx_grades = [_strongest_grade(r.get("sources"))
                  for d in drugs for block in d.get("pgx", [])
                  for r in block.get("rows", [])]
    # Active-metabolite identity nodes ("<name> is an active metabolite of <drug>"),
    # one per authored metabolite across all drugs, graded by that metabolite's own
    # sources (the Stahl line naming it). The metabolite's optional T½ is an extra
    # sourced fact shown in the panel; its receptor BINDINGS are their own tally kind
    # below (each a graded graph edge appearing on the receptor's Interacting drugs).
    # A (grade, is_uncertain) pair: a link another corpus denies is active buckets as
    # ``uncertain`` however strong its own quote (CONTRADICTIONS).
    metabolite_grades = [_node_grade(m) for d in drugs for m in d.get("metabolites", [])]
    # Which enzyme FORMS each active metabolite, one node per (parent, metabolite,
    # enzyme). The mirror of the enzyme nodes above (there the drug is the substrate,
    # here the metabolite is the product), and its own kind because it is separately
    # sourced and separately missing: only 14 of the metabolites have a corpus that
    # names their forming enzyme. Counted per PARENT, unlike the bindings below: "CYP2D6
    # makes X out of A" and "... out of B" are two different reactions, not one fact
    # about the molecule.
    metabolite_enzyme_grades = [_node_grade(f) for d in drugs for m in d.get("metabolites", [])
                                for f in m.get("formed_by", [])]
    # Non-modeled-metabolite receptor bindings, graded exactly like a drug binding
    # (quote source or measured Ki). A separate kind from drug_bindings so the drug Ki
    # coverage figures are unperturbed; authored by apply_metabolite_bindings.py.
    # Walked over the one-per-molecule metabolite store, not the parents: mCPP's
    # bindings are a property of the molecule, so nefazodone AND trazodone listing it
    # count them once. (The identity node above legitimately stays per-parent: "X is a
    # metabolite of A" and "X is a metabolite of B" are two separately sourced claims.)
    metabolite_binding_grades = [_node_grade(b, _binding_grade(b))
                                 for m in metabolites for b in m.get("bindings", [])]
    # A metabolite's binding direction is the same claim as a drug's, so it is counted
    # in the SAME drug_binding_action kind (a ligand's binding direction either way).
    binding_action_grades.extend(_binding_action_grade(b) for m in metabolites
                                 for b in m.get("bindings", []))
    # (grade, is_uncertain) pairs, like the bindings above: a pathway the book states
    # only as a blanket sweep buckets as ``uncertain`` however strong its quote is.
    projection_grades = [_node_grade(p)
                         for p in projections]
    # The two sub-claims split out of that same arrow (see quotes/attestation.py): what
    # transmitter it carries, and, for the glutamate/GABA ones, its excitatory/inhibitory
    # sign. Each is its own node for the same reason a receptor's four classification
    # attributes are: one sentence rarely attests all of them, and the sign in particular
    # colours every arrow in the viewer's Potential mode. A modulatory system makes no
    # sign claim at all, so it contributes no ``projection_sign`` node (not an unsourced
    # one). The uncertainty flag stays on the pathway node: a blanket sweep is doubt about
    # which regions the arrow reaches, not about what it releases.
    def _claim_grades(name: str) -> list[tuple[str, bool]]:
        return [_node_grade(entry, entry["grade"]) for p in projections
                if (entry := (p.get("claims") or {}).get(name))]
    projection_transmitter_grades = _claim_grades("transmitter")
    projection_sign_grades = _claim_grades("sign")
    # Functional-circuit + projection-group nodes: each a "these structures / pathways
    # form a system" claim, graded by its own sources (rank 0 => missing when unsourced,
    # matching the viewer's NOSOURCE pill). All missing today (no circuit/group is
    # document-backed yet).
    circuit_grades = [_node_grade(c) for c in circuits]
    projection_group_grades = [_node_grade(g) for g in projection_groups]
    # Receptor classification is FOUR independent nodes per receptor, one per
    # attribute (family / receptor_class / sign / synaptic), each graded on its own
    # so an unsourced GPCR/sign/site claim shows honestly instead of borrowing a
    # neighbouring quote's grade. A pure stub (no CNS role: no locations, not
    # ubiquitous, no description) is not a node, so it is skipped. The receptor's
    # *expression regions* are a separate node kind (receptor_locations), one node
    # per region, not folded in here.
    scored_receptors = [r for r in receptors
                        if r.get("ubiquitous") or r.get("locations")
                        or r.get("description")]

    # A (grade, is_uncertain) pair: an attribute another corpus denies buckets
    # ``uncertain`` however strong its own quote (quotes/contradictions.py).
    def _attr_grade(r: dict[str, Any], attr: str) -> tuple[str, bool]:
        entry = (r.get("classification") or {}).get(attr)
        if not entry:
            return (DEFAULT_PROVENANCE, False)
        return _node_grade(entry, entry["grade"])
    receptor_family_grades = [_attr_grade(r, "family") for r in scored_receptors]
    receptor_class_grades = [_attr_grade(r, "receptor_class") for r in scored_receptors]
    receptor_sign_grades = [_attr_grade(r, "sign") for r in scored_receptors]
    receptor_synaptic_grades = [_attr_grade(r, "synaptic") for r in scored_receptors]
    # Expression-region nodes ("Found in"), one node PER (owner, region): the claim
    # "owner O is expressed in region B", distinct from O's classification node. Each
    # region's grade = the strongest of that region's location_sources (default llm
    # when unsourced). A ubiquitous receptor is one "throughout the brain" node (its
    # "ALL"-keyed sources). Shared by receptors and their non-receptor-target mirror.
    _llm_rank = _GRADE_RANK[DEFAULT_PROVENANCE]
    targets = list(own_targets(drug_targets).values())
    # The owners of the gene-keyed node kinds (effects, demographics, variants):
    # receptors and non-receptor targets alike.
    gene_owners = (*receptors, *targets)

    # A (grade, is_uncertain) pair, a region its animal-only evidence flags
    # (quotes/animal_evidence.py, ``location_uncertainty``) bucketing ``uncertain``.
    def location_grades(owner: dict[str, Any], regions_key: str) -> list[tuple[int, bool]]:
        loc_sources = owner.get("location_sources", {})
        doubted = owner.get("location_uncertainty") or {}
        bases = ["ALL"] if owner.get("ubiquitous") else owner.get(regions_key, [])
        return [(max(_strongest_grade(loc_sources.get(base)), _llm_rank), base in doubted)
                for base in bases]

    receptor_location_grades = [g for r in receptors
                                for g in location_grades(r, "locations")]
    # Expression-DENSITY nodes ("and it is concentrated in these regions"), ONE per owner
    # that carries a measured profile (an owner without one is simply not a node here,
    # like a drug with no half-life). Distinct from the presence nodes above: presence and
    # concentration are different claims and can be sourced independently.
    receptor_density_grades = [r["density"]["grade"] for r in receptors if r.get("density")]
    # Non-receptor drug target classifications (type / system), graded per target.
    # Receptor-linked targets are skipped (already counted as receptors, not twice).
    target_grades = [t.get("classification_provenance", DEFAULT_PROVENANCE)
                     for t in targets]
    # Target expression-region nodes: the mirror of receptor_locations (a target never
    # sets ubiquitous, so only the per-region branch runs; receptor-linked targets are
    # skipped, their regions counted as the receptor's).
    target_location_grades = [g for t in targets for g in location_grades(t, "regions")]
    target_density_grades = [t["density"]["grade"] for t in targets if t.get("density")]
    # Target tone-polarity sub-claims: one graded node per non-receptor target that
    # carries a direction-flipping flag (vesicular / sign / synaptic). Kept distinct
    # from the target's type/system classification so a wrong direction shows honestly.
    target_polarity_grades = [t["polarity_provenance"] for t in targets
                              if "polarity_provenance" in t]
    # Clinical-effect nodes (kind receptor_effect, BETA): one per (owner, mode, effect),
    # on receptors and non-receptor targets alike. Like a density profile, a node exists
    # only once sourced, and it is a stored quoted claim, so it sits in the headline.
    # An owner whose effects were searched everywhere with no hit (``effects_unknown``,
    # data_generators/unknown.py) adds one UNKNOWN, outside the denominator.
    # A (grade, is_uncertain) pair: an effect backed by isolated tissue only buckets
    # ``uncertain`` however strong its quote (receptor_effects.EFFECT_EVIDENCE).
    receptor_effect_grades = [_node_grade(e, e["grade"]) for o in gene_owners
                              for e in o.get("effects", [])] + [
        "unknown" for o in gene_owners if o.get("effects_unknown")]
    # Release-modulation nodes (kind receptor_release_modulation, BETA): one per (receptor,
    # kind, site, transmitter, direction); exists only once sourced, so in the headline.
    release_modulation_grades = [_node_grade(n, n["grade"]) for r in receptors
                                 for n in r.get("release_modulation", [])]
    # Availability-across-age/sex nodes (kind receptor_demographic, BETA): one per (owner,
    # factor, direction, structure), receptors and non-receptor targets alike.
    demographic_grades = [_node_grade(n, n["grade"]) for o in gene_owners
                          for n in o.get("demographics", [])]
    # Gene-variant associations (kind receptor_variant, ClinPGx #20): one per (owner,
    # clinical annotation), receptors and non-receptor targets alike.
    variant_grades = [n["grade"] for o in gene_owners for n in o.get("variants", [])]
    # Brain-region anatomy (existence / group / position), graded per emitted
    # structure record (both hemispheres of a pair count, one line each).
    structure_grades = [_node_grade(s, s.get("classification_provenance", DEFAULT_PROVENANCE))
                        for s in structures]
    # Wikipedia reference links across every owner kind. Non-receptor targets only
    # (a receptor is already counted via the receptor records, not twice); a missing
    # link is a rank-0 "missing" so the gap shows in the coverage.
    ref_grades: list[int] = []
    for rec in (*structures, *receptors, *drugs):
        ref_grades.append(_GRADE_RANK.get(rec.get("wikipedia_provenance"), 0)
                          if rec.get("wikipedia") else 0)
    for tgt in targets:
        ref_grades.append(_GRADE_RANK.get(tgt.get("wikipedia_provenance"), 0)
                          if tgt.get("wikipedia") else 0)

    # Addon nodes (see data_generators/addons.py): one node per authored annotation,
    # graded by its own quote sources. Its *slot* is where it draws, not what it
    # claims, so it tallies like any other claim: the whole point of the kind is that
    # a panel-placed caveat is held to the same sourcing bar as a binding.
    # A ``dataset`` addon is a statement about this dataset, not knowledge (see
    # addons.ADDON_BASES), so it is not a node of the tally at all.
    addon_grades = [_strongest_grade(a.get("sources")) for a in addons
                    if a.get("basis", "claim") != "dataset"]

    # Enzyme variability (kind ``enzyme_variability``): one node per isoform carrying a
    # metabolizer-status profile. An isoform PharmFreq does not cover is not a node at
    # all rather than an unsourced one, because "we have no frequencies for CYP3A4" is
    # a gap in the corpus, not an unbacked claim we made.
    variability_grades = [_strongest_grade((e.get("variability") or {}).get("sources"))
                          for e in (enzymes or {}).values() if e.get("variability")]

    by_kind = {
        "addons": tally(addon_grades),
        "enzyme_variability": tally(variability_grades),
        "drug_bindings": tally(binding_grades),
        "drug_binding_action": tally(binding_action_grades),
        "drug_nbn": scalar["drug_nbn"],
        "drug_brands": tally(brand_grades),
        "drug_categories": tally(category_grades),
        "drug_half_life": scalar["drug_half_life"],
        "drug_tmax": scalar["drug_tmax"],
        "drug_formulations": tally(formulation_grades),
        "drug_first_approval": scalar["drug_first_approval"],
        "drug_withdrawals": tally(withdrawal_grades),
        "drug_holders": tally(holder_grades),
        "drug_originator": scalar["drug_originator"],
        "drug_originator_country": scalar["drug_originator_country"],
        "drug_prodrug": scalar["drug_prodrug"],
        "drug_constituents": scalar["drug_constituents"],
        "drug_therapeutic_range": scalar["drug_therapeutic_range"],
        "drug_alert_level": scalar["drug_alert_level"],
        "drug_lipophilicity": tally(physchem_grades["xlogp"]),
        "drug_polar_surface": tally(physchem_grades["tpsa"]),
        "drug_bbb": tally(physchem_grades["bbb"]),
        "drug_workup": tally(workup_grades),
        "drug_enzymes": tally(enzyme_grades),
        "drug_enzyme_strength": tally(enzyme_strength_grades),
        "drug_pgx": tally(pgx_grades),
        "drug_metabolites": tally(metabolite_grades),
        "drug_metabolite_enzyme": tally(metabolite_enzyme_grades),
        "drug_metabolite_bindings": tally(metabolite_binding_grades),
        "projections": tally(projection_grades),
        "projection_transmitter": tally(projection_transmitter_grades),
        "projection_sign": tally(projection_sign_grades),
        "circuits": tally(circuit_grades),
        "projection_groups": tally(projection_group_grades),
        "receptors": tally(receptor_family_grades),
        "receptor_class": tally(receptor_class_grades),
        "receptor_sign": tally(receptor_sign_grades),
        "receptor_synaptic": tally(receptor_synaptic_grades),
        "receptor_locations": tally(receptor_location_grades),
        "receptor_density": tally(receptor_density_grades),
        "targets": tally(target_grades),
        "target_polarity": tally(target_polarity_grades),
        "target_locations": tally(target_location_grades),
        "target_density": tally(target_density_grades),
        "receptor_effect": tally(receptor_effect_grades),
        "receptor_release_modulation": tally(release_modulation_grades),
        "receptor_demographic": tally(demographic_grades),
        "receptor_variant": tally(variant_grades),
        "structures": tally(structure_grades),
        "references": tally(ref_grades),
    }
    # The headline sums over the one roster (node_kinds.py); a by_kind key outside it
    # would be tallied yet silently left out of the headline, so refuse the drift.
    drift = set(by_kind) ^ set(node_kinds_mod.NODE_KINDS + node_kinds_mod.TALLY_ONLY_KINDS)
    if drift:
        raise ValueError(f"by_kind keys out of sync with node_kinds.py: {sorted(drift)}")
    node_kinds = node_kinds_mod.NODE_KINDS
    nodes = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
             "llm": 0, "nosource": 0, "missing": 0, "unknown": 0}
    for kind in node_kinds:
        for key in nodes:
            nodes[key] += by_kind[kind][key]
    # ``uncertain`` counts as backed: the claim does rest on a real, quote-checked
    # document, and the badge says what is doubtful about it. Moving it out of
    # ``verified`` is the honest part; moving it out of ``backed`` would not be.
    backed = node_kinds_mod.backed(nodes)
    nodes["backed"] = backed
    nodes["pct_backed"] = (
        round(100 * backed / nodes["total"]) if nodes["total"] else 0)
    return {"by_kind": by_kind, "nodes": nodes, "ki_coverage": ki_coverage}
