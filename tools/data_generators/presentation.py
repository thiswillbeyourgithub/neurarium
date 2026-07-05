"""Presentation label maps + the Wikipedia link table, emitted into meta.json.

Extracted verbatim from generate_data.py: these are plain key -> display-label
dicts (and the per-structure Wikipedia URL table) that the viewer reads from
meta.json to build its legends. Kept out of the CLI module so the label
vocabularies live in one place; no i18n helpers are needed (the values are plain
strings, localized downstream at emit time).
"""

# Sign legend heading (excitatory / inhibitory / modulatory); the swatch colours
# live in SIGN_COLORS in generate_data.py.
SIGN_LABELS: dict[str, str] = {
    "excitatory": "Excitatory",
    "inhibitory": "Inhibitory",
    "modulatory": "Modulatory",
}

# Structure ``group`` -> legend heading, in legend display order (object key
# order is preserved through JSON, so the viewer's legend follows this order).
GROUP_LABELS: dict[str, str] = {
    "lobe": "Lobes",
    "basal_ganglia": "Basal ganglia / deep nuclei",
    "diencephalon": "Diencephalon",
    "limbic": "Limbic",
    "hindbrain": "Hindbrain",
    # The monoamine source nuclei (serotonin / noradrenaline / dopamine), added so
    # receptor expression in them (e.g. raphe 5-HT1A autoreceptors, locus
    # coeruleus alpha-2 autoreceptors) has somewhere to light up. Small deep
    # brainstem/midbrain nuclei, kept in their own group so they don't take part
    # in the cortex/deep-nuclei jigsaw clipping.
    "brainstem_nuclei": "Brainstem nuclei",
}

# Receptor presentation maps (emitted into meta.json). Each map is a key ->
# display label; the per-receptor excit/inhib/modulatory ``sign`` reuses
# SIGN_LABELS above. Object key order is the legend display order. build_records
# validates that every family/class/sign/synaptic value used by a receptor has an
# entry here.
RECEPTOR_FAMILY_LABELS: dict[str, str] = {
    "adrenergic": "Adrenergic",
    "cholinergic": "Cholinergic",
    "dopaminergic": "Dopaminergic",
    "gabaergic": "GABAergic",
    "glutamatergic": "Glutamatergic",
    "glycinergic": "Glycinergic",
    "histaminergic": "Histaminergic",
    "opioidergic": "Opioidergic",
    "serotonergic": "Serotonergic",
    "cannabinoid": "Cannabinoid",
    "purinergic": "Purinergic",
    "sigma": "Sigma",
    "melatonergic": "Melatonergic",
}
# Receptor mechanism class. "chaperone" is here for the sigma-1 receptor, which is
# neither a ligand-gated channel nor a GPCR but an intracellular ER chaperone.
RECEPTOR_CLASS_LABELS: dict[str, str] = {
    "ionotropic": "Ionotropic (ligand-gated ion channel)",
    "metabotropic": "Metabotropic (GPCR)",
    "chaperone": "Intracellular chaperone",
}
# Pre-/post-synaptic location of the receptor.
SYNAPTIC_LABELS: dict[str, str] = {
    "presynaptic": "Presynaptic",
    "postsynaptic": "Postsynaptic",
    "both": "Pre- and postsynaptic",
}

# Wikipedia article per structure, keyed by ``base`` id (so both hemispheres of a
# paired region share the one article, written once here). The generator attaches
# the URL to each structure record
# (``_structure_record``) and the viewer renders it as a link in the structure
# info panel. URLs were verified to resolve to the specific anatomical article
# (e.g. the insula's article is "Insular_cortex", the fornix's is
# "Fornix_(neuroanatomy)", the septal nuclei's is "Septal_area"). A structure
# absent from this map simply gets no link; an entry whose key is not a known
# structure base raises in :func:`build_records` (typo guard).
WIKIPEDIA: dict[str, str] = {
    "frontal": "https://en.wikipedia.org/wiki/Frontal_lobe",
    "parietal": "https://en.wikipedia.org/wiki/Parietal_lobe",
    "temporal": "https://en.wikipedia.org/wiki/Temporal_lobe",
    "occipital": "https://en.wikipedia.org/wiki/Occipital_lobe",
    "insula": "https://en.wikipedia.org/wiki/Insular_cortex",
    "caudate": "https://en.wikipedia.org/wiki/Caudate_nucleus",
    "putamen": "https://en.wikipedia.org/wiki/Putamen",
    "globus_pallidus": "https://en.wikipedia.org/wiki/Globus_pallidus",
    "thalamus": "https://en.wikipedia.org/wiki/Thalamus",
    "subthalamic_nucleus": "https://en.wikipedia.org/wiki/Subthalamic_nucleus",
    "substantia_nigra": "https://en.wikipedia.org/wiki/Substantia_nigra",
    "accumbens": "https://en.wikipedia.org/wiki/Nucleus_accumbens",
    "claustrum": "https://en.wikipedia.org/wiki/Claustrum",
    "hippocampus": "https://en.wikipedia.org/wiki/Hippocampus",
    "amygdala": "https://en.wikipedia.org/wiki/Amygdala",
    "cingulate": "https://en.wikipedia.org/wiki/Cingulate_cortex",
    "fornix": "https://en.wikipedia.org/wiki/Fornix_(neuroanatomy)",
    "olfactory_bulb": "https://en.wikipedia.org/wiki/Olfactory_bulb",
    "septal_nuclei": "https://en.wikipedia.org/wiki/Septal_area",
    "hypothalamus": "https://en.wikipedia.org/wiki/Hypothalamus",
    "mammillary": "https://en.wikipedia.org/wiki/Mammillary_body",
    "pituitary": "https://en.wikipedia.org/wiki/Pituitary_gland",
    "cerebellum": "https://en.wikipedia.org/wiki/Cerebellum",
    "midbrain": "https://en.wikipedia.org/wiki/Midbrain",
    "pons": "https://en.wikipedia.org/wiki/Pons",
    "medulla": "https://en.wikipedia.org/wiki/Medulla_oblongata",
    "raphe": "https://en.wikipedia.org/wiki/Raphe_nuclei",
    "locus_coeruleus": "https://en.wikipedia.org/wiki/Locus_coeruleus",
    "vta": "https://en.wikipedia.org/wiki/Ventral_tegmental_area",
}
