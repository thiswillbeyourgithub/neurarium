"""Presentation label maps + the Wikipedia link table, emitted into meta.json.

Extracted verbatim from generate_data.py: these are plain key -> display-label
dicts (and the per-structure Wikipedia URL table) that the viewer reads from
meta.json to build its legends. Kept out of the CLI module so the label
vocabularies live in one place; no i18n helpers are needed (the values are plain
strings, localized downstream at emit time).
"""

# Arrow colour per projection ``kind`` (the functional class): glutamate ->
# excitatory (red), GABA -> inhibitory (blue), dopamine -> dopaminergic (green),
# acetylcholine -> cholinergic (gold), neurosecretory/hormonal -> neuroendocrine
# (purple), serotonin -> serotonergic (teal), noradrenaline -> noradrenergic
# (pink). The kind selects the arrow colour; the finer transmitter molecule is
# the projection's ``neurotransmitter`` field. The monoamine ascending kinds
# (dopaminergic / serotonergic / noradrenergic / cholinergic) are what the
# per-drug "by-mechanism flow" overlay rides: a focused drug lights flow along
# the projections whose kind matches its target transmitter system (see
# js/drug-anim.js).
PROJECTION_COLORS: dict[str, str] = {
    "excitatory": "#e15759",
    "inhibitory": "#4e79a7",
    "dopaminergic": "#59a14f",
    "cholinergic": "#edc948",
    "neuroendocrine": "#b07aa1",
    "serotonergic": "#76b7b2",
    "noradrenergic": "#ff9da7",
    "histaminergic": "#f0912e",  # warm orange: the tuberomammillary histamine fan
    "melatonergic": "#8d7be0",  # indigo: the night hormone, from the pineal gland
}

# The viewer offers two arrow colour modes (a toggle in the panel):
#   - "transmitter" (default): one colour per neurotransmitter, i.e. PROJECTION_
#     COLORS above (today each kind carries exactly one transmitter, so per-kind ==
#     per-transmitter);
#   - "sign": a coarse red/blue excitatory-vs-inhibitory view, with the
#     neuromodulatory kinds (dopaminergic / cholinergic / neuroendocrine /
#     serotonergic / noradrenergic) collapsed to a neutral "modulatory" grey since
#     they have no single excit/inhib sign.
# KIND_TO_SIGN folds each functional kind onto its sign; SIGN_COLORS / SIGN_LABELS
# give the sign its swatch + legend heading. All three are emitted into the meta
# record so the viewer can recolour + relabel the legend with no hardcoded palette.
KIND_TO_SIGN: dict[str, str] = {
    "excitatory": "excitatory",
    "inhibitory": "inhibitory",
    "dopaminergic": "modulatory",
    "cholinergic": "modulatory",
    "neuroendocrine": "modulatory",
    "serotonergic": "modulatory",
    "noradrenergic": "modulatory",
    "histaminergic": "modulatory",
    "melatonergic": "modulatory",
}
SIGN_COLORS: dict[str, str] = {
    "excitatory": "#e15759",  # red, same as the excitatory kind
    "inhibitory": "#4e79a7",  # blue, same as the inhibitory kind
    "modulatory": "#9aa0a6",  # neutral grey: no single excit/inhib sign
}

# Sign legend heading (excitatory / inhibitory / modulatory); the swatch colours
# live in SIGN_COLORS above.
SIGN_LABELS: dict[str, str] = {
    "excitatory": "Excitatory",
    "inhibitory": "Inhibitory",
    "modulatory": "Modulatory",
}

# Per-drug "by-mechanism flow" overlay (js/drug-anim.js): focusing a drug also
# lights flowing beads along the projections of its target transmitter *system*.
# This maps a drug target's ``system`` (the neurotransmitter family: a DRUG_TARGETS
# ``system`` or a receptor ``family``) to the projection ``kind`` that carries it,
# but *only* for the diffuse modulatory systems with a source modeled (serotonin /
# raphe, noradrenaline / locus coeruleus, dopamine / VTA + substantia nigra,
# acetylcholine / septum + nucleus basalis + pons, histamine / tuberomammillary,
# melatonin / pineal).
# Fast point-to-point systems (glutamatergic / gabaergic) are absent on
# purpose: mapping them would flood the view with every excitatory/inhibitory arrow
# instead of a drug-specific fan. A drug whose systems aren't here gets no flow,
# just its dots + wash. Emitted into meta.json so the viewer hardcodes no table.
SYSTEM_FLOW_KINDS: dict[str, str] = {
    "serotonergic": "serotonergic",
    "adrenergic": "noradrenergic",
    "dopaminergic": "dopaminergic",
    "cholinergic": "cholinergic",
    "histaminergic": "histaminergic",
    # Melatonin is the odd one: the route is hormonal, not axonal, and MT1/MT2 are
    # postsynaptic, so a melatonin agonist still sets no tone and rides no beads.
    # Mapped anyway so the group panel exists and the innervation check can see
    # that the system now has a source.
    "melatonergic": "melatonergic",
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
    "pineal": "https://en.wikipedia.org/wiki/Pineal_gland",
    "pituitary": "https://en.wikipedia.org/wiki/Pituitary_gland",
    "cerebellum": "https://en.wikipedia.org/wiki/Cerebellum",
    "midbrain": "https://en.wikipedia.org/wiki/Midbrain",
    "pons": "https://en.wikipedia.org/wiki/Pons",
    "medulla": "https://en.wikipedia.org/wiki/Medulla_oblongata",
    "raphe": "https://en.wikipedia.org/wiki/Raphe_nuclei",
    "locus_coeruleus": "https://en.wikipedia.org/wiki/Locus_coeruleus",
    "vta": "https://en.wikipedia.org/wiki/Ventral_tegmental_area",
    "tuberomammillary": "https://en.wikipedia.org/wiki/Tuberomammillary_nucleus",
    "nucleus_basalis": "https://en.wikipedia.org/wiki/Nucleus_basalis",
}
