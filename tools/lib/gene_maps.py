"""The owner -> HGNC gene symbol maps, defined once: ``RECEPTOR_GENES`` (the GtoPdb
tissue pass, corpus #7) completed by ``EXTRA_RECEPTOR_GENES`` (the classification pass,
corpus #12) into ``receptor_genes()``, and ``TARGET_GENES`` (the non-receptor targets,
resolved for the Allen pass, corpus #8; a list, since a group target maps to several).

Read by the fetchers that join an external database by gene and by
``data_generators/genes.py`` (lookup links in the emitted data). Stdlib only.

Built with the help of Claude Code.
"""
from __future__ import annotations


# receptor id (our ids) -> HGNC gene symbol, the key GtoPdb resolves via
# ?geneSymbol=. Only receptors that carry an explicit region list are here
# (ubiquitous receptors state "throughout the brain", a single ALL node, and the
# locs=0 stubs have nothing to source). A heteromer/subfamily is mapped to its
# representative principal subunit (nAChR alpha4beta2 -> CHRNA4, 5-HT3 -> HTR3A,
# kainate -> GRIK1); the tissue-distribution join is by that gene.
RECEPTOR_GENES: dict[str, str] = {
    # serotonin
    "5ht1a": "HTR1A", "5ht1b": "HTR1B", "5ht1d": "HTR1D", "5ht1e": "HTR1E",
    "5ht1f": "HTR1F", "5ht2a": "HTR2A", "5ht2b": "HTR2B", "5ht2c": "HTR2C",
    "5ht3": "HTR3A", "5ht4": "HTR4", "5ht5a": "HTR5A", "5ht6": "HTR6", "5ht7": "HTR7",
    # dopamine
    "d1": "DRD1", "d2": "DRD2", "d3": "DRD3", "d4": "DRD4", "d5": "DRD5",
    # adrenergic
    "alpha1a": "ADRA1A", "alpha1b": "ADRA1B", "alpha1d": "ADRA1D",
    "alpha2a": "ADRA2A", "alpha2b": "ADRA2B", "alpha2c": "ADRA2C",
    "beta1": "ADRB1", "beta2": "ADRB2",
    # muscarinic + nicotinic
    "m1": "CHRM1", "m2": "CHRM2", "m3": "CHRM3", "m4": "CHRM4", "m5": "CHRM5",
    "nachr_a4b2": "CHRNA4", "nachr_a7": "CHRNA7",
    # histamine
    "h1": "HRH1", "h2": "HRH2", "h3": "HRH3",
    # opioid
    "mu": "OPRM1", "delta": "OPRD1", "kappa": "OPRK1",
    # glutamate (metabotropic + kainate representative)
    "mglur1": "GRM1", "mglur2": "GRM2", "mglur3": "GRM3", "mglur4": "GRM4",
    "mglur5": "GRM5", "kainate": "GRIK1",
    # others
    "cb1": "CNR1", "a2a": "ADORA2A", "mt1": "MTNR1A", "mt2": "MTNR1B",
    "sigma1": "SIGMAR1", "glycine": "GLRA1",
}


# The receptors ``RECEPTOR_GENES`` (the tissue pass) does not map, because that pass
# only needed receptors carrying an explicit region list. Classification applies to
# every receptor, so the map is completed here rather than widened there (the tissue
# fetcher's docstring explains why its own map is narrow). A heteromer is mapped to
# its representative principal subunit, exactly as there.
EXTRA_RECEPTOR_GENES: dict[str, str] = {
    "beta3": "ADRB3",
    "nachr_muscle": "CHRNA1",
    "gaba_a": "GABRA1",
    "gaba_a_rho": "GABRR1",
    "gaba_b": "GABBR1",
    "nmda": "GRIN1",
    "ampa": "GRIA1",
    "mglur6": "GRM6",
    "mglur7": "GRM7",
    "h4": "HRH4",
    # alpha2d is deliberately absent: it is a stub receptor (a rodent pharmacological
    # subtype with no human gene), not a counted node.
}


def receptor_genes() -> dict[str, str]:
    """Every receptor id we can resolve to a gene (tissue map + the completion)."""
    return {**RECEPTOR_GENES, **EXTRA_RECEPTOR_GENES}


# Non-receptor drug targets (the 25 target_locations owners) -> HGNC gene symbol(s). A
# multi-gene group (muscarinic, the adrenergic/nicotinic groups, ...) is "present in B" if
# ANY member gene detects there; the citation names the member gene that did.
TARGET_GENES = {
    "sert": ["SLC6A4"], "net": ["SLC6A2"], "dat": ["SLC6A3"], "gat": ["SLC6A1"],
    # NKCC1, the chloride-gradient setter (SLC12A1 is its kidney-only sibling).
    "nkcc1": ["SLC12A2"],
    "vmat2": ["SLC18A2"], "mao_a": ["MAOA"], "mao_b": ["MAOB"],
    "ache": ["ACHE"], "bche": ["BCHE"],
    "carbonic_anhydrase": ["CA2"], "pde5": ["PDE5A"],
    "nav": ["SCN1A", "SCN2A", "SCN3A", "SCN8A"],
    "cav": ["CACNA1A", "CACNA1B", "CACNA1C"],
    "cav_a2d": ["CACNA2D1", "CACNA2D2"],
    "cav_t": ["CACNA1G", "CACNA1H", "CACNA1I"],
    "sv2a": ["SV2A"],
    # GABA transaminase, the enzyme that degrades GABA (vigabatrin's target).
    "gaba_t": ["ABAT"],
    # DOPA decarboxylase (levodopa's enzyme) and catechol-O-methyltransferase.
    "aadc": ["DDC"], "comt": ["COMT"],
    # The CGRP receptor is a heterodimer, so both halves are read: CALCRL is the
    # GPCR, RAMP1 the accessory subunit that makes it CGRP-selective.
    "cgrp": ["CALCRL", "RAMP1"],
    "muscarinic": ["CHRM1", "CHRM2", "CHRM3", "CHRM4", "CHRM5"],
    "nicotinic": ["CHRNA4", "CHRNB2", "CHRNA7"],
    "alpha1": ["ADRA1A", "ADRA1B", "ADRA1D"],
    "alpha2": ["ADRA2A", "ADRA2B", "ADRA2C"],
    "beta": ["ADRB1", "ADRB2", "ADRB3"],
    "glutamate": ["GRIN1", "GRIA1", "GRIA2"],
    "melatonin": ["MTNR1A", "MTNR1B"],
    "orexin": ["HCRTR1", "HCRTR2"],
    "melanocortin": ["MC4R", "MC3R"],
}
