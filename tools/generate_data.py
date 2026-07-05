#!/usr/bin/env python
"""Generate the neurarium brain visualizer data artifacts.

This script is the *single source of truth* for the anatomy shown by the
viewer. Editing the structures/projections lists here and re-running keeps the
consumed artifacts in sync without duplicating anatomical data:

- ``data/`` : the dataset, split by record type for clarity (one file per kind;
  the file a record lives in encodes its type, so there is no ``type`` field on
  the lines). ``meta.json`` is a single object carrying the presentation maps
  (arrow colours + legend headings); ``structures.jsonl`` (one brain region per
  line: id, group, anatomical position, color, ...), ``projections.jsonl`` (one
  directed neuron pathway between two structures per line) and ``circuits.jsonl``
  (one named functional loop per line) are JSONL. The viewer reads these to know
  *what* to draw and *how things relate*.
- ``data/shapes/<name>.json``: one file per distinct *form* (ellipsoid radii +
  organic deformation parameters). The actual mesh deformation happens in JS
  (see ``js/shapes.js``); these files just carry the parameters so the form of a
  region can be tweaked independently of its position/relationships. Symmetric
  left/right pairs share a single right-side file (the left member reflects it
  via a ``mirror`` flag), so there is no per-side duplication; midline
  structures each have their own file.

Why a generator instead of hand-written files: the project is expected to grow
complex, and most regions come in symmetric left/right pairs. Defining a region
once here and mirroring it avoids the duplication that hand-authoring ~20 files
would create. The generated files are committed so the static site can fetch
them directly; regenerate them whenever this script changes.

Stdlib-only on purpose (argparse/json/pathlib): this is build tooling that must
run offline with a bare ``python`` interpreter, so it avoids the usual
click/loguru dependencies.

Usage
-----
    python tools/generate_data.py            # writes into ../public/data/ (meta.json + *.jsonl + shapes/)
    python tools/generate_data.py --root /some/dir
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("generate_data")


# ---------------------------------------------------------------------------
# Presentation maps (emitted into the data so the dataset is self-describing)
#
# Display metadata, not anatomy, but the viewer reads them straight from the
# data (``meta.json``) rather than hardcoding them in JS: a projection
# ``kind`` -> arrow colour, and a structure ``group`` -> legend heading. Keeping
# them here (the single source of truth) means another engine consuming the
# dataset gets the colours + headings for free, with no copy to keep in sync
# in the viewer. build_records() validates that every kind/group used by the
# data has an entry here, so an unmapped value fails loudly at generation.
# ---------------------------------------------------------------------------

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
}
SIGN_COLORS: dict[str, str] = {
    "excitatory": "#e15759",  # red, same as the excitatory kind
    "inhibitory": "#4e79a7",  # blue, same as the inhibitory kind
    "modulatory": "#9aa0a6",  # neutral grey: no single excit/inhib sign
}
SIGN_LABELS: dict[str, str] = {
    "excitatory": "Excitatory",
    "inhibitory": "Inhibitory",
    "modulatory": "Modulatory",
}

# Per-drug "by-mechanism flow" overlay (js/drug-anim.js): focusing a drug also
# lights flowing beads along the projections of its target transmitter *system*.
# This maps a drug target's ``system`` (the neurotransmitter family: a DRUG_TARGETS
# ``system`` or a receptor ``family``) to the projection ``kind`` that carries it,
# but *only* for the diffuse ascending modulatory systems with a brainstem source
# nucleus modeled (serotonin / raphe, noradrenaline / locus coeruleus, dopamine /
# VTA + substantia nigra, acetylcholine / septum). Fast point-to-point systems
# (glutamatergic / gabaergic) and unmodeled ones (histaminergic, ...) are absent on
# purpose: mapping them would flood the view with every excitatory/inhibitory arrow
# instead of a drug-specific fan. A drug whose systems aren't here gets no flow,
# just its dots + wash. Emitted into meta.json so the viewer hardcodes no table.
SYSTEM_FLOW_KINDS: dict[str, str] = {
    "serotonergic": "serotonergic",
    "adrenergic": "noradrenergic",
    "dopaminergic": "dopaminergic",
    "cholinergic": "cholinergic",
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

# ---------------------------------------------------------------------------
# Receptor presentation maps (emitted into meta.json), analogous to the maps
# above. Receptors (see RECEPTORS below) are neurotransmitter receptors expressed
# in the modeled structures; the viewer lists them in a legend section grouped by
# neurotransmitter *family*, and focusing one lights glowing dots on every
# structure where it is expressed. Each map is a key -> display label; the
# per-receptor excit/inhib/modulatory ``sign`` reuses SIGN_COLORS / SIGN_LABELS
# above (so the receptor legend swatch matches the arrow sign colours). Object key
# order is the legend display order. build_records validates that every
# family/class/sign/synaptic value used by a receptor has an entry here.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Drug presentation maps + binding vocabularies (DRUG_* + DRUG_TARGETS +
# TARGET_TYPE_*) live in data_generators.drugs.
# ---------------------------------------------------------------------------
from data_generators.drugs import (  # noqa: E402
    DRUG_ACTIONS,
    DRUG_CATEGORY_LABELS,
    DRUG_EFFECT_COLORS,
    DRUG_EFFECT_LABELS,
    DRUG_TARGETS,
    TARGET_TYPE_COLORS,
    TARGET_TYPE_LABELS,
)

# ---------------------------------------------------------------------------
# Source provenance: grades, override registries, SOURCE_CORPORA + the quote /
# binding / Ki source validators live in data_generators.provenance.
# ---------------------------------------------------------------------------
from data_generators.provenance import (  # noqa: E402
    DEFAULT_PROVENANCE,
    DRUG_CATEGORY_PROVENANCE,
    PROVENANCE_LEVELS,
    RECEPTOR_LOCATION_SOURCES,
    RECEPTOR_PROVENANCE,
    SOURCE_CORPORA,
    STRUCTURE_PROVENANCE,
    TARGET_LOCATION_SOURCES,
    TARGET_POLARITY_PROVENANCE,
    TARGET_PROVENANCE,
    WIKIPEDIA_DEFAULT_PROVENANCE,
    WIKIPEDIA_PROVENANCE,
    _binding_sources,
    _ki_annotation,
    _location_sources,
    _lookup_provenance,
    _provenance,
    _quote_sources,
    _receptor_provenance,
    _structure_provenance,
    _target_polarity_provenance,
    _target_provenance,
    _wiki_provenance,
)


# ---------------------------------------------------------------------------
# Internationalization (en / fr): the FR translation table, the _t()/_side_name
# wrappers and the missing-translation guard live in data_generators.i18n.
# ---------------------------------------------------------------------------
from data_generators.i18n import (  # noqa: E402
    FR,
    TRANSLATIONS,
    _FR_LEFT,
    _FR_RIGHT,
    _MISSING_TRANSLATIONS,
    _side_name,
    _t,
    externalize,
    reset_translations,
)

# The receptor classification records (pure data, one module per neurotransmitter
# family) live in the data_generators.receptors package. See the schema comment at
# the RECEPTORS use-site below.
from data_generators.receptors import RECEPTORS  # noqa: E402


# ---------------------------------------------------------------------------
# Anatomy definition (the single source of truth)
#
# Coordinate convention (arbitrary units, brain centered on the origin):
#   x : left (-) .. right (+)
#   y : inferior/down (-) .. superior/up (+)
#   z : posterior/back (-) .. anterior/front-of-face (+)
#
# Each "half" entry below is given with a RIGHT-hemisphere position (x > 0) and
# is mirrored to the left automatically: the left member reuses the same shape
# file reflected across x (a true geometric mirror, not a copy), so asymmetric
# forms like the C-shaped caudate flip sides correctly. Midline structures are
# listed separately and emitted once (never mirrored).
# ---------------------------------------------------------------------------

# Per-structure shape params (default "blob" = noise-deformed ellipsoid):
#   radii  : (rx, ry, rz) ellipsoid half-extents before deformation
#   seed   : integer making the organic deformation deterministic & unique
#   detail : icosphere subdivision level (higher = smoother/more vertices)
#   noise  : deformation amplitude as a fraction of radius (0 = clean ellipsoid)
#
# An entry may instead carry an explicit ``shape=dict(type=...)`` payload for a
# non-ellipsoid form. Currently the only other type is "curve": a tapered tube
# swept along a Catmull-Rom spline (see js/shapes.js buildCurveGeometry), used
# for the strongly C-shaped caudate. Its params:
#   points  : spine control points [(x,y,z), ...] head -> tail (local coords)
#   profile : tube radius sampled head -> tail (interpolated along the spine)
#   seed/noise/radial_segments/tubular_segments : surface wobble + tessellation

# Cortical-dome geometry helpers and the brain-region anatomy records were split
# out verbatim into data_generators.geometry and data_generators.regions.
# MIDLINE_GAP is reused by the blob clip logic further below.
from data_generators.geometry import MIDLINE_GAP  # noqa: E402
from data_generators.regions import MIDLINE, PAIRED  # noqa: E402

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

# Reference registry. A pathway cites one or more of these by short key (see the
# ``sources`` field on PROJECTIONS); the generator expands each key into the full
# ``{citation, url, provenance}`` object inside every projection record, so a
# reference shared by several pathways is written exactly once here (no
# duplication) yet the emitted data stays self-contained (the viewer never
# resolves keys). An entry may set its own ``provenance`` grade (see
# :data:`PROVENANCE_LEVELS`); omitting it defaults to :data:`DEFAULT_PROVENANCE`.
#
# These are landmark/textbook references for the classic circuitry. The ``url``
# is left as the literal "TODO" rather than a guessed DOI: fill in a verified
# link per entry. (The viewer renders a source with a real http(s) url as a
# clickable link and a "TODO" url as plain text.)

# Directed neuron projections drawn as arrows. Each entry is a connection with
# metadata so the viewer can show what the pathway is and what supports it:
#   from, to        : structure ids (e.g. "putamen_R"); the arrow points from->to
#   kind            : functional/transmitter class, selects the arrow color
#                     (key of PROJECTION_COLORS in js/arrows.js + the legend)
#   neurotransmitter: the specific transmitter molecule (Glutamate/GABA/Dopamine)
#   label           : short pathway name
#   description     : one-line plain-language summary (shown in the info panel)
#   sources         : list backing the connection; each item is an inline
#                     {corpus, page, quote, provenance} dict (a quote-level source
#                     against a SOURCE_CORPORA corpus, the drug-binding shape). A
#                     "verified" quote, checked present on its page by check_data.py,
#                     promotes the pathway's grade. (A pathway's verified Kandel quote
#                     is supplied from PROJECTION_QUOTES, not inline.)
#   bidirectional   : optional; True draws a cone at BOTH ends (reciprocal /
#                     commissural pathways like the corpus callosum)
#   symmetric       : optional generator hint (default True); see below
#
# Bilateral by default: each entry is auto-mirrored to the left hemisphere (``_R``
# <-> ``_L`` on both endpoints, midline endpoints kept), so a symmetric pathway is
# defined once on the right. Set ``"symmetric": False`` for a pathway that already
# spans both sides (e.g. a commissure with explicit _L and _R endpoints) so it is
# not mirrored into a duplicate. ``symmetric`` is stripped from the emitted data.

def _kandel(page: int, quote: str) -> dict[str, Any]:
    """A verified Kandel quote-source (the drug-binding ``{corpus,page,quote}`` shape)."""
    return dict(corpus="kandel", page=page, provenance="verified", quote=quote)


def _nieuwenhuys(page: int, quote: str) -> dict[str, Any]:
    """A verified Nieuwenhuys atlas quote-source (``page`` = the PDF/.md page number)."""
    return dict(corpus="nieuwenhuys", page=page, provenance="verified", quote=quote)


# Verified quote-sources for the pathways, keyed by the RIGHT-side ``(from, to)``
# endpoint pair (matching how PROJECTIONS defines each pathway once on the right).
# Most are Kandel (the ``_kandel`` helper); a few connectivity claims Kandel does
# not state in prose are backed by the Nieuwenhuys atlas (``_nieuwenhuys``). Each
# quote carries its own ``corpus``, so the table is corpus-agnostic.
# ``_projection_records`` merges the matching quote into that entry's ``sources``
# before mirroring, so both hemispheres inherit it; a single sentence that backs
# several pathways (e.g. one naming the whole striatal output) is written once here,
# not duplicated per entry. Every key must match a PROJECTIONS entry or
# ``build_records`` raises (typo guard). This is the projection analogue of the
# per-binding drug sources; ``check_data.py`` confirms each quote is verbatim on its
# cited page (the verify gate).
_KQ_NIGROSTRIATAL = _kandel(982,
    "The substantia nigra pars compacta/ventral tegmental area contain an "
    "important population of dopaminergic neurons. These neurons represent the "
    "third major input station of the basal ganglia and give rise to the "
    "nigrostriatal and mesolimbic/mesocortical dopamine projections.")
_KQ_STRIATOPALLIDAL = _kandel(982,
    "Most connections of the globus pallidus are with other basal ganglia nuclei, "
    "including inhibitory (GABAergic) input from the striatum and excitatory "
    "(glutamatergic) input from the subthalamus.")
_KQ_STRIATONIGRAL = _kandel(982,
    "The substantia nigra pars reticulata is the second principal output nucleus. "
    "It also receives afferents from other basal ganglia nuclei and provides "
    "efferent connections to the thalamus and brain stem. Inhibitory (GABAergic) "
    "inputs come from the striatum and globus pallidus (external) and excitatory "
    "input from the subthalamus.")
_KQ_CORTICOSTRIATAL = _kandel(981,
    "The striatum is the largest nucleus of the basal ganglia. It receives direct "
    "input from most regions of the cerebral cortex and limbic structures, "
    "including the amygdala and hippocampus.")
_KQ_VTA_REWARD = _kandel(1558,
    "The reward circuitry comprises the dopaminergic projections from the ventral "
    "tegmental area of the midbrain to forebrain targets, including the nucleus "
    "accumbens, habenula, prefrontal cortex, hippocampus, and amygdala "
    "(Chapter 43).")
_KQ_CORPUS_CALLOSUM = _kandel(549,
    "A major fiber bundle called the corpus callosum connects the two hemispheres, "
    "transmitting information across the midline.")
_KQ_CORTICOPONTINE = _kandel(958,
    "The cerebral cortex projects to the lateral cerebellum through relays in the "
    "pontine nuclei.")
_KQ_PAPEZ = _kandel(1096,
    "The outputs of the hypothalamus reach the cingulate via the anterior "
    "thalamus, and the outputs of the cingulate reach the hypothalamus via the "
    "hippocampus.")
_KQ_MONOAMINE_INNERV = _kandel(1052,
    "The noradrenergic locus ceruleus, serotonergic dorsal and median raphe "
    "nuclei, dopaminergic A10 neurons, and histaminergic tuberomammillary neurons "
    "innervate the thalamus, hypothalamus, basal forebrain, and cerebral cortex.")
_KQ_MONOAMINE_LIMBIC = _kandel(1560,
    "Serotonergic and noradrenergic neurons in the pons and medulla project widely "
    "to highly diverse terminal fields in brain regions that include the "
    "hypothalamus, hippocampus, amygdala, basal ganglia, and cerebral cortex "
    "(Figures 61–5 and 61–6).")
# The two basal-ganglia loops named as such (Kandel's Albin-scheme passage); these
# back the bg_direct / bg_indirect CIRCUITS nodes, so they live outside PROJECTION_QUOTES
# (which is keyed by projection endpoints, not circuit ids).
_KQ_BG_DIRECT = _kandel(983,
    "Output of the basal ganglia is determined by the balance between a direct "
    "pathway from the striatum to the output nuclei.")
_KQ_BG_INDIRECT = _kandel(983,
    "Striatal neurons containing enkephalin and expressing mainly D2 dopamine "
    "receptors make excitatory contact with the output nuclei via relays in the "
    "globus pallidus and subthalamus: the indirect pathway.")

PROJECTION_QUOTES: dict[tuple[str, str], dict[str, Any]] = {
    # Dopaminergic nigrostriatal (one sentence covers both striatal targets).
    ("substantia_nigra_R", "putamen_R"): _KQ_NIGROSTRIATAL,
    ("substantia_nigra_R", "caudate_R"): _KQ_NIGROSTRIATAL,
    # Direct pathway: striatum -> output nuclei (GABA).
    ("putamen_R", "globus_pallidus_R"): _KQ_STRIATOPALLIDAL,
    ("caudate_R", "globus_pallidus_R"): _KQ_STRIATOPALLIDAL,
    ("putamen_R", "substantia_nigra_R"): _KQ_STRIATONIGRAL,
    ("caudate_R", "substantia_nigra_R"): _KQ_STRIATONIGRAL,
    # Corticostriatal: parietal + temporal covered by the general striatum-input
    # sentence; frontal targets get their own more specific sentences.
    ("parietal_R", "caudate_R"): _KQ_CORTICOSTRIATAL,
    ("temporal_R", "caudate_R"): _KQ_CORTICOSTRIATAL,
    ("frontal_R", "caudate_R"): _kandel(918,
        "The substantia nigra is suppressed by the caudate nucleus, which in turn "
        "is excited by the frontal eye fields."),
    ("frontal_R", "putamen_R"): _kandel(986,
        "the sensorimotor territories of the dorsolateral striatum receive "
        "collateral fibers from motor cortex axons that send signals to the "
        "spinal cord."),
    # Hyperdirect: cortex -> STN (glutamate).
    ("frontal_R", "subthalamic_nucleus_R"): _kandel(986,
        "The subthalamus therefore receives phasic excitatory (glutamatergic) "
        "signals from the cerebral cortex, thalamus, and brain stem."),
    # Indirect pathway: external pallidum -> STN (GABA).
    ("globus_pallidus_R", "subthalamic_nucleus_R"): _kandel(986,
        "Following cortical activation, short-latency excitatory effects in the "
        "subthalamus are thought to be mediated via these \"hyperdirect\" "
        "connections, whereas longer-latency suppressive effects are more likely "
        "to come from indirect inhibitory inputs from other basal ganglia nuclei, "
        "principally the external globus pallidus."),
    # STN -> pallidum (glutamate).
    ("subthalamic_nucleus_R", "globus_pallidus_R"): _kandel(982,
        "The subthalamic nucleus is the only component of the basal ganglia that "
        "has excitatory (glutamatergic) output connections. These project to both "
        "output nuclei and to the intrinsic external globus pallidus."),
    # Basal-ganglia output -> thalamus (GABA).
    ("globus_pallidus_R", "thalamus_R"): _kandel(982,
        "Neurons of the internal globus pallidus are themselves GABAergic and "
        "have high levels of tonic activity. Under normal circumstances, this "
        "imposes powerful inhibitory effects on targets in the thalamus, lateral "
        "habenula, and brain stem."),
    ("substantia_nigra_R", "thalamus_R"): _kandel(982,
        "Pars reticulata neurons are also GABAergic and impose strong inhibitory "
        "control over parts of the thalamus and brain stem, including the superior "
        "colliculus, pedunculopontine nucleus, and parts of the midbrain and "
        "medullary reticular formation."),
    # Thalamus -> cortex closure (glutamate).
    ("thalamus_R", "frontal_R"): _kandel(130,
        "The ventral anterior and ventral lateral nuclei are important for motor "
        "control and carry information from the basal ganglia and cerebellum to "
        "the motor cortex."),
    # Mesolimbic / mesocortical dopamine: one VTA reward-projection sentence backs
    # all four VTA targets (the substantia-nigra->accumbens entry is left
    # unsourced: Kandel assigns the accumbens to the VTA, the nigra to the dorsal
    # striatum, so that pathway is suspect, see STATUS note).
    ("vta_R", "accumbens_R"): _KQ_VTA_REWARD,
    ("vta_R", "amygdala_R"): _KQ_VTA_REWARD,
    ("vta_R", "frontal_R"): _KQ_VTA_REWARD,
    ("vta_R", "hippocampus_R"): _KQ_VTA_REWARD,
    # Interhemispheric corpus callosum (homologous cortical areas across midline);
    # the anterior commissure (temporal) + claustro-cortical pathways stay
    # unsourced (Kandel has no temporal-commissure sentence and never mentions the
    # claustrum), and the insula->cingulate "salience" link is only stated as a
    # symmetric connection, so it is not a directional source.
    ("frontal_L", "frontal_R"): _KQ_CORPUS_CALLOSUM,
    ("parietal_L", "parietal_R"): _KQ_CORPUS_CALLOSUM,
    ("occipital_L", "occipital_R"): _KQ_CORPUS_CALLOSUM,
    # Cerebellar loop: one relay sentence backs cortex -> pons and pons ->
    # cerebellum; the dentate -> thalamus output is its own sentence.
    ("frontal_R", "pons"): _KQ_CORTICOPONTINE,
    ("pons", "cerebellum"): _KQ_CORTICOPONTINE,
    ("cerebellum", "thalamus_R"): _kandel(964,
        "The output is transmitted through the dentate nucleus, which projects via "
        "the thalamus to contralateral motor, premotor, parietal, and prefrontal "
        "cortices."),
    # Limbic / Papez circuit. One Papez sentence backs cingulate->hippocampus and
    # anterior-thalamus->cingulate; the fornix tract (hippocampus->fornix->
    # mammillary) and the septal->hypothalamus link stay unsourced (Kandel
    # describes the fornix only as a figure label).
    ("cingulate_R", "hippocampus_R"): _KQ_PAPEZ,
    ("thalamus_R", "cingulate_R"): _KQ_PAPEZ,
    ("mammillary_R", "thalamus_R"): _kandel(130,
        "The _anterior group_ receives its major input from the mammillary nuclei "
        "of the hypothalamus and from the presubiculum of the hippocampal "
        "formation."),
    ("temporal_R", "hippocampus_R"): _kandel(1387,
        "In the indirect pathway, the axons of neurons in layer II of the "
        "entorhinal cortex project through the _perforant pathway_ to excite the "
        "granule cells of the dentate gyrus (an area considered part of the "
        "hippocampus)."),
    ("amygdala_R", "hypothalamus_R"): _kandel(1380,
        "These nuclei project to the central nucleus, which projects to the "
        "hypothalamus and brain stem."),
    ("amygdala_R", "accumbens_R"): _kandel(1124,
        "This work is beginning to define the distinct roles that various "
        "glutamatergic projections to the nucleus accumbens— from the prefrontal "
        "cortex, hippocampus, amygdala, and thalamus—play in controlling different "
        "cell types in the nucleus accumbens and the broader reward circuitry and "
        "in producing distinct addiction-related behavioral abnormalities."),
    # Sensory corticothalamic feedback, olfactory output, neuroendocrine axis.
    # (olfactory bulb -> amygdala stays unsourced: Kandel states it only across two
    # separate sentences, never one.)
    ("occipital_R", "thalamus_R"): _kandel(149,
        "In most cases, two areas that have feedforward connections also have "
        "feedback connections; for example, there are numerous connections from "
        "primary visual cortex back to the thalamus."),
    ("olfactory_bulb_R", "insula_R"): _kandel(735,
        "The axons of the mitral and tufted relay neurons of the olfactory bulb "
        "project through the lateral olfactory tract to the olfactory cortex "
        "(Figure 29–8 and see Figure 29–1)."),
    ("hypothalamus_R", "pituitary"): _kandel(1074,
        "Hormone secretion from these cells is controlled by stimulatory and "
        "inhibitory factors released by hypothalamic neurons into a specialized "
        "circulatory system that carries blood from the base of the brain (median "
        "eminence) to the anterior pituitary."),
    # Ascending monoamine + cholinergic systems (diffuse). Two innervation
    # sentences back most LC/raphe targets; LC->amygdala and septum->hippocampus
    # get their own sentences.
    ("locus_coeruleus_R", "amygdala_R"): _kandel(1379,
        "This form of learning requires postsynaptic NMDA receptors and "
        "voltagegated calcium channels in the lateral amygdala, and it is enhanced "
        "by norepinephrine released in lateral amygdala from the locus ceruleus."),
    ("locus_coeruleus_R", "frontal_R"): _KQ_MONOAMINE_INNERV,
    ("locus_coeruleus_R", "thalamus_R"): _KQ_MONOAMINE_INNERV,
    ("locus_coeruleus_R", "hippocampus_R"): _KQ_MONOAMINE_LIMBIC,
    ("raphe", "frontal_R"): _KQ_MONOAMINE_INNERV,
    ("raphe", "hypothalamus_R"): _KQ_MONOAMINE_INNERV,
    ("raphe", "amygdala_R"): _KQ_MONOAMINE_LIMBIC,
    ("raphe", "hippocampus_R"): _KQ_MONOAMINE_LIMBIC,
    ("septal_nuclei_R", "hippocampus_R"): _kandel(1048,
        "Rather, scientists refer to the cholinergic neurons by their location, eg, "
        "the pedunculopontine (Ch6) and laterodorsal tegmental (Ch5) neurons in the "
        "pons, which project widely from the cerebral cortex to the medulla, and "
        "the basal forebrain (Ch1–Ch4) groups, which project to the cerebral "
        "cortex, hippocampus, and amygdala."),
    # Ventral striatopallidal: accumbens -> ventral pallidum (the indirect-pathway
    # relay of the reward circuit).
    ("accumbens_R", "globus_pallidus_R"): _kandel(1117,
        "There are also GABAergic projections from the NAc to the VTA, with some in "
        "a direct pathway innervating the VTA and some in an indirect pathway "
        "innervating the VTA via intervening GABAergic neurons in the ventral "
        "pallidum"),
    # Limbic / olfactory / commissural pathways Kandel does not state in prose,
    # backed by the Nieuwenhuys atlas.
    ("olfactory_bulb_R", "amygdala_R"): _nieuwenhuys(412,
        "Secondary olfactory fibres originating from the olfactory bulb pass by "
        "way of the lateral olfactory tract to the amygdala, where they terminate "
        "mainly in the cortical nucleus"),
    ("hippocampus_R", "fornix_R"): _nieuwenhuys(387,
        "Contrary to what was believed for almost a century, the entire "
        "postcommissural fornix and considerable part of the precommissural "
        "fornix originate from the subiculum rather than from Ammon's horn."),
    ("fornix_R", "mammillary_R"): _nieuwenhuys(383,
        "The main bundle of the fornix or postcommissural fornix finally "
        "traverses the hypothalamus, where most of its fibres terminate in the "
        "mamillary body."),
    ("hippocampus_R", "septal_nuclei_R"): _nieuwenhuys(389,
        "The precommissural fornix fibres originating from Ammon's horn "
        "terminate exclusively in the lateral septal nucleus."),
    ("septal_nuclei_R", "hypothalamus_R"): _nieuwenhuys(939,
        "Comparable functional specializations have been observed in the "
        "organization of the projections from the lateral septal complex to the "
        "medial preoptico-hypothalamic zone."),
    ("temporal_L", "temporal_R"): _nieuwenhuys(617,
        "Commissural fibres from the inferotemporal cortex cross in the posterior "
        "part of the body of the corpus callosum and in the anterior commissure"),
    ("insula_R", "cingulate_R"): _nieuwenhuys(655,
        "a considerable number of limbic cortical areas, including the "
        "entorhinal, perirhinal, temporopolar, posterior orbitofrontal and "
        "cingulate cortices, as well as the amygdaloid complex, are reciprocally "
        "connected with agranular and dysgranular sectors in the anterior and "
        "anterobasal parts of the insula"),
}

# Verified quote-sources for the region-anatomy claims (a structure's existence /
# classification / location), keyed by base id. Most are Kandel (``_kandel``); the
# claustrum + fornix, which Kandel does not describe in prose, are backed by the
# Nieuwenhuys atlas (``_nieuwenhuys``). Each quote carries its own ``corpus``.
# _structure_record attaches the quote as the structure's `sources` and upgrades its
# `classification_provenance` to the quote's grade; both hemispheres share it.
# Every key must be a real structure base or build_records raises (typo guard).
# Same verify gate as the pathways: check_data confirms the quote is on its page.
_KSQ_STRIATUM = _kandel(981,
    "The striatum (a collective term for the caudate nucleus and putamen; see "
    "Figure 38–1), subthalamic nucleus, and substantia nigra pars compacta/ventral "
    "tegmental area are the three major input nuclei of the basal ganglia, "
    "receiving signals directly and indirectly from structures distributed "
    "throughout the neuraxis (Figure 38–2).")
_KSQ_LOBES = _kandel(63,
    "The frontal lobe is largely concerned with short-term memory, planning future "
    "actions, and control of movement; the parietal lobe mediates somatic "
    "sensation, forming a body image and relating it to extrapersonal space; the "
    "occipital lobe is concerned with vision; and the temporal lobe processes "
    "hearing, the recognition of objects and faces, and—through its deep "
    "structures, the hippocampus and amygdaloid nuclei—learning, memory, and "
    "emotion.")

STRUCTURE_QUOTES: dict[str, dict[str, Any]] = {
    # Cortical lobes: one compound sentence names all four; the insula its own.
    "frontal": _KSQ_LOBES,
    "parietal": _KSQ_LOBES,
    "occipital": _KSQ_LOBES,
    "temporal": _KSQ_LOBES,
    "insula": _kandel(59,
        "The insular cortex, which lies buried within the overlying frontal, "
        "parietal, and temporal lobes, plays an important role in emotion, "
        "homeostasis, and taste perception."),
    # Basal ganglia (caudate + putamen share the striatum sentence).
    "caudate": _KSQ_STRIATUM,
    "putamen": _KSQ_STRIATUM,
    "globus_pallidus": _kandel(59,
        "The basal ganglia, which include the caudate, putamen, and globus "
        "pallidus, regulate movement execution and motor- and habit-learning, two "
        "forms of memory that are referred to as implicit memory; the hippocampus "
        "is critical for storage of memory of people, places, things, and events, "
        "a form of memory that is referred to as explicit; and the amygdaloid "
        "nuclei coordinate the autonomic and endocrine responses of emotional "
        "states, including memory of threats, another form of implicit memory."),
    "subthalamic_nucleus": _kandel(982,
        "The subthalamic nucleus is the only component of the basal ganglia that "
        "has excitatory (glutamatergic) output connections."),
    "substantia_nigra": _kandel(59,
        "The various brain regions described above are often divided into three "
        "broader regions: the hindbrain (comprising the medulla oblongata, pons, "
        "and cerebellum); midbrain (comprising the tectum, substantia nigra, "
        "reticular formation, and periaqueductal gray matter); and forebrain "
        "(comprising the diencephalon and cerebrum)."),
    "accumbens": _kandel(1114,
        "These neurons project to several areas of the brain, including the "
        "nucleus accumbens (the major component of the ventral striatum), the "
        "ventromedial portion of the head of the caudate nucleus (in the dorsal "
        "striatum), the basal forebrain, and regions of the prefrontal cortex "
        "(Figure 43–1B)."),
    "thalamus": _kandel(129,
        "The thalamus is an egg-shaped structure that constitutes the dorsal "
        "portion of the diencephalon."),
    # Brainstem source nuclei.
    "locus_coeruleus": _kandel(1561,
        "Norepinephrine is synthesized in several brain stem nuclei, the largest "
        "of which is the nucleus locus ceruleus, a pigmented nucleus located just "
        "beneath the floor of the fourth ventricle in the rostrolateral pons."),
    "raphe": _kandel(1560,
        "Serotonin is synthesized in a group of brain stem nuclei called the "
        "raphe nuclei."),
    "vta": _kandel(982,
        "The substantia nigra pars compacta/ventral tegmental area contain an "
        "important population of dopaminergic neurons."),
    # Diencephalon.
    "hypothalamus": _kandel(1025,
        "Neurons controlling the internal environment are concentrated in the "
        "hypothalamus, a small area of the diencephalon that comprises less than "
        "1% of the total brain volume."),
    "mammillary": _kandel(1096,
        "The sensory cortex then projects to both the cingulate cortex and the "
        "hippocampus, which in turn makes connections with the mammillary bodies "
        "of the hypothalamus, thus completing the loop"),
    "pituitary": _kandel(1058,
        'The neuroendocrine system works differently, by secreting several '
        'peptide hormones from the pituitary, the "master gland," located just '
        'beneath the hypothalamus.'),
    # Hindbrain (each a distinct sentence in Kandel's Box 1-2 on p59).
    "cerebellum": _kandel(59,
        "The cerebellum, behind the pons, modulates the force and range of "
        "movement and is involved in the learning of motor skills."),
    "medulla": _kandel(59,
        "The medulla oblongata, directly rostral to the spinal cord, includes "
        "several centers responsible for vital autonomic functions, such as "
        "digestion, breathing, and the control of heart rate."),
    "midbrain": _kandel(59,
        "The midbrain, rostral to the pons, controls many sensory and motor "
        "functions, including eye movement and the coordination of visual and "
        "auditory reflexes."),
    "pons": _kandel(59,
        "The pons, rostral to the medulla, conveys information about movement "
        "from the cerebral hemispheres to the cerebellum."),
    # Limbic. Claustrum + fornix are not in Kandel's prose, so the Nieuwenhuys
    # atlas backs them.
    "claustrum": _nieuwenhuys(421,
        "The claustrum is a thin sheet of grey matter, embedded in the white "
        "matter of the cerebral hemispheres and largely situated between the "
        "putamen and the insular cortex."),
    "fornix": _nieuwenhuys(64,
        "the fornix, a large fibre system that connects the hippocampal "
        "formation with the septum and the hypothalamus."),
    "amygdala": _kandel(531,
        "Parabrachial neurons project to the amygdala, a critical nucleus of the "
        "limbic system, which regulates emotional states (Chapter 42)."),
    "cingulate": _kandel(59,
        "The cingulate cortex lies dorsal to the corpus callosum and is important "
        "for regulation of emotion, pain perception, and cognition."),
    "hippocampus": _kandel(140,
        "We know that a structure called the hippocampus (or more properly the "
        "hippocampal formation, since it is several cortical regions) is a key "
        "component of a medial temporal lobe memory system that encodes and "
        "stores memories of our lives (Figure 4–17)."),
    "olfactory_bulb": _kandel(734,
        "The axons of olfactory sensory neurons project to the ipsilateral "
        "olfactory bulb, whose rostral end lies just above the olfactory "
        "epithelium."),
    "septal_nuclei": _kandel(1047,
        "Those in the basal forebrain are divided into the medial septum, the "
        "nuclei of the vertical and horizontal limbs of the diagonal band, and "
        "the nucleus basalis of Meynert."),
}


def _stahl_ess(page: int, quote: str) -> dict[str, Any]:
    """A verified Stahl Essential Psychopharmacology quote-source."""
    return dict(corpus="stahl_essential", page=page,
                provenance="verified", quote=quote)


# Verified Stahl Essential quote-sources for the receptor + non-receptor-target
# classification claims, keyed by receptor id / DRUG_TARGETS id. _receptor_record
# and _build_drug_targets attach the quote as `sources` and upgrade
# classification_provenance; a key that is not a real id fails the build. One
# mechanism sentence often backs a whole receptor family, so it is written once.
# Shared mechanism sentences (one classifies a whole receptor family / target group).
_SE_MUSCARINIC = _stahl_ess(522,
    "Muscarinic acetylcholine receptors are G-protein-linked and can be either "
    "excitatory or inhibitory.")
_SE_NICOTINIC = _stahl_ess(79,
    "The state of inactivation may be best characterized for nicotinic cholinergic "
    "receptors, ligand-gated ion channels that are normally responsive to the "
    "endogenous neurotransmitter acetylcholine.")
_SE_IONO_GLU = _stahl_ess(117,
    "NMDA ( _N_ -methyl-D-asparate), AMPA (α-amino3-hydroxy-5-methyl-4-isoxazole-"
    "propionic acid), and kainate receptors for glutamate, named after the "
    "agonists that selectively bind to them, are all members of the ligand-gated "
    "ion-channel family of receptors (Figure 4-23 and Table 4-2).")
_SE_META_GLU = _stahl_ess(116,
    "Metabotropic glutamate receptors are those glutamate receptors that are "
    "linked to G proteins.")
_SE_PENTAMERIC = _stahl_ess(92,
    "One subclass of ligand-gated ion channels has a pentameric structure, and "
    "includes GABAA receptors, nicotinic cholinergic receptors, 5HT3 receptors, "
    "and certain glycine receptors.")
_SE_5HT1BD = _stahl_ess(406,
    "Serotonin inhibits primary afferent terminals via postsynaptic 5HT1B/D "
    "receptors (Figure 9-2). These inhibitory receptors are G-protein-coupled, and "
    "indirectly influence ion channels to hyperpolarize the nerve terminal and "
    "inhibit nociceptive neurotransmitter release.")
_SE_D2LIKE = _stahl_ess(97,
    "The second group is the D2-like receptors, including D2, D3, and D4 receptors. "
    "D2-like receptors are inhibitory and negatively linked to adenylate cyclase "
    "(Figure 4-4, right).")
_SE_CHE = _stahl_ess(521,
    'ACh\'s actions are terminated by one of two enzymes, either '
    'acetylcholinesterase (AChE) or butyrylcholinesterase (BuChE), sometimes also '
    'called "pseudocholinesterase" or "nonspecific cholinesterase" (Figure 12-25).')
_SE_VSC = _stahl_ess(25,
    "Electrical impulses open ion channels – both voltage-sensitive sodium "
    "channels (VSSCs) and voltage-sensitive calcium channels (VSCCs) – by changing "
    "the ionic charge across neuronal membranes.")
_SE_NE_GROUPS = _stahl_ess(270,
    "Other NE receptors are classified as α1, α2A, α2B, or α2C, or as β1, β2, or β3 "
    "(Figure 6-14).")
# GABAA and its ρ-subunit variant (GABA-A-ρ, historically "GABAC") are both
# ligand-gated inhibitory chloride channels; one sentence names both.
_SE_GABAAC = _stahl_ess(275,
    "GABAA and GABAC receptors are ligand-gated ion channels; they are part of "
    "a macromolecular complex that forms an inhibitory chloride channel.")
# One sign sentence classifies the postsynaptic 5HT subtypes: 5HT2A/2C/4/6/7 as
# excitatory, 5HT1A/5A as inhibitory (shared across those receptors).
_SE_5HT_SIGN = _stahl_ess(136,
    "both excitatory (e.g., at 5HT2A, 5HT2C, 5HT4, 5HT6, and 5HT7 receptors) and "
    "inhibitory (at 5HT1A, 5HT5, and possibly postsynaptic 5HT1B heteroreceptors)")
# The presynaptic-autoreceptor list (p131): names 5HT1A, 5HT1B/D, 5HT2B as presynaptic
# autoreceptors. Backs the presynaptic half of a "both" synaptic value (paired with the
# postsynaptic 5HT1B/D quote for 1B/1D) and is 5HT2B's family quote.
_SE_5HT_PRESYN_AUTO = _stahl_ess(131,
    "Presynaptic serotonin (5HT) receptors include 5HT1A, 5HT1B/D, and 5HT2B, "
    "all of which act as autoreceptors")
# One sentence names both melatonin receptors (backs MT1 + MT2 + the melatonin target).
_SE_MELATONIN = _stahl_ess(455,
    "There are three types of receptors for melatonin: MT1 and MT2, which are "
    "both involved in sleep, and MT3, which is actually the enzyme NRH–quinine "
    "oxidoreductase 2 and not thought to be involved in sleep physiology.")

STAHL_ESSENTIAL_RECEPTOR_QUOTES: dict[str, dict[str, Any]] = {
    "m1": _SE_MUSCARINIC, "m2": _SE_MUSCARINIC, "m3": _SE_MUSCARINIC,
    "m4": _SE_MUSCARINIC, "m5": _SE_MUSCARINIC,
    "nachr_a4b2": _SE_NICOTINIC, "nachr_a7": _SE_NICOTINIC,
    "nachr_muscle": _SE_NICOTINIC,
    "nmda": _SE_IONO_GLU, "ampa": _SE_IONO_GLU, "kainate": _SE_IONO_GLU,
    "mglur1": _SE_META_GLU, "mglur2": _SE_META_GLU, "mglur3": _SE_META_GLU,
    "mglur4": _SE_META_GLU, "mglur5": _SE_META_GLU, "mglur6": _SE_META_GLU,
    "mglur7": _SE_META_GLU,
    "gaba_a": _SE_GABAAC, "gaba_a_rho": _SE_GABAAC,
    "gaba_b": _stahl_ess(275,
        "GABAB receptors are G-protein-linked receptors that may be coupled with "
        "calcium or potassium channels."),
    "glycine": _SE_PENTAMERIC,
    "5ht3": _SE_PENTAMERIC,
    "h1": _stahl_ess(421,
        "When histamine binds to postsynaptic histamine 1 (H1) receptors, it "
        "activates a G-protein-linked second-messenger system that activates "
        "phosphatidylinositol (PI) and the transcription factor cFOS."),
    "h2": _stahl_ess(421,
        "When histamine binds to postsynaptic H2 receptors it activates a "
        "G-proteinlinked second-messenger system with cyclic adenosine "
        "monophosphate (cAMP), phosphokinase A (PKA), and the gene product CREB."),
    "5ht1b": _SE_5HT1BD, "5ht1d": _SE_5HT1BD,
    "d1": _stahl_ess(473,
        "D1 receptors, on the other hand, are linked to the cAMP signaling system "
        "via the stimulatory G protein (Gs) (Figure 11-17)."),
    "d2": _stahl_ess(208,
        "With full agonists, the receptor conformation is such that there is "
        "robust signal transduction through the G-protein-linked second-messenger "
        "system of D2 receptors (left)."),
    "d3": _SE_D2LIKE, "d4": _SE_D2LIKE,
    "d5": _stahl_ess(97,
        "The first group is the D1-like receptors, including both D1 and D5 "
        "receptors. D1-like receptors are excitatory, and positively linked to "
        "adenylate cyclase (Figure 4-4, left)."),
    "alpha2a": _stahl_ess(473,
        "Alpha-2A receptors are linked to the molecule cyclic adenosine "
        "monophosphate (cAMP) via the inhibitory G protein (Gi) (Figure 11-17)."),
    # Other adrenergic subtypes: the NE-receptor enumeration classifies them.
    # (α2D is not named in the book, so it stays llm; α2A keeps its own quote above.)
    "alpha1a": _SE_NE_GROUPS, "alpha1b": _SE_NE_GROUPS,
    "alpha1c": _SE_NE_GROUPS, "alpha1d": _SE_NE_GROUPS,
    "alpha2b": _SE_NE_GROUPS, "alpha2c": _SE_NE_GROUPS,
    "beta1": _SE_NE_GROUPS, "beta2": _SE_NE_GROUPS, "beta3": _SE_NE_GROUPS,
    # Serotonin subtypes (5HT1E/1F are absent from this corpus, so they stay llm).
    "5ht1a": _SE_5HT_SIGN, "5ht2a": _SE_5HT_SIGN, "5ht2c": _SE_5HT_SIGN,
    "5ht4": _SE_5HT_SIGN, "5ht5a": _SE_5HT_SIGN, "5ht6": _SE_5HT_SIGN,
    "5ht2b": _SE_5HT_PRESYN_AUTO,
    "5ht7": _stahl_ess(146, "5HT7 receptors are postsynaptic, excitatory, and"),
    # Opioid receptors (endogenous-opioid passage; each names the receptor + postsynaptic).
    "mu": _stahl_ess(575,
        "synapse with postsynaptic sites containing μ-opioid receptors"),
    "delta": _stahl_ess(575,
        "neurons that release enkephalin synapse with postsynaptic δ-opioid receptors"),
    "kappa": _stahl_ess(575,
        "neurons that release dynorphin synapse with postsynaptic κ-opioid receptors"),
    "cb1": _stahl_ess(581,
        "The endocannabinoid then binds to a presynaptic cannabinoid receptor, "
        "causing the inhibition of neurotransmitter release"),
    "a2a": _stahl_ess(457,
        "an antagonist at purine receptors, and in particular adenosine receptors"),
    "sigma1": _stahl_ess(311,
        "The physiological function of σ1 sites is still a mystery, and thus "
        "sometimes called the “sigma enigma”"),
    "mt1": _SE_MELATONIN, "mt2": _SE_MELATONIN,
    "h3": _stahl_ess(421, "Histamine 3 (H3) receptors are presynaptic autoreceptors"),
    "h4": _stahl_ess(422, "There is a fourth type of histamine receptor, H4"),
}

# A receptor's classification is NOT one claim but four independent ones, each its
# own graded node: neurotransmitter `family`, mechanism `receptor_class`
# (GPCR/ionotropic), `sign` (excitatory/inhibitory), and `synaptic` site
# (pre/postsynaptic). A single Stahl quote almost never substantiates all four, so
# attaching it to the whole record over-grades the attributes it never addressed
# (the reported bug: 5-HT2C's *sign* quote falsely lent a verified pill to its GPCR
# and postsynaptic claims). This table records, per receptor, exactly which
# attributes its STAHL_ESSENTIAL_RECEPTOR_QUOTES sentence actually backs; every
# other attribute stays at the base grade (llm unless RECEPTOR_PROVENANCE lifts it).
# Coverage is assigned conservatively: an attribute is listed ONLY when the quote
# states that receptor's *specific* value, never when it merely could be inferred
# or when the quote and the record disagree (e.g. 5-HT2B's quote calls it a
# presynaptic autoreceptor while the record says postsynaptic, so only `family` is
# backed and the record's synaptic value is left honestly unsourced).
CLASSIFICATION_ATTRS = ("family", "receptor_class", "sign", "synaptic")
_F = ("family",)
_FG = ("family", "sign")
_FY = ("family", "synaptic")
_FGY = ("family", "sign", "synaptic")
_FC = ("family", "receptor_class")
_FCG = ("family", "receptor_class", "sign")
_FCY = ("family", "receptor_class", "synaptic")
RECEPTOR_CLASSIFICATION_COVERAGE: dict[str, tuple[str, ...]] = {
    # G-protein / ion-channel quotes give family + class, but not a specific sign or site.
    "m1": _FC, "m2": _FC, "m3": _FC, "m4": _FC, "m5": _FC,
    "nachr_a4b2": _FC, "nachr_a7": _FC, "nachr_muscle": _FC,
    "nmda": _FC, "ampa": _FC, "kainate": _FC,
    "mglur1": _FC, "mglur2": _FC, "mglur3": _FC, "mglur4": _FC, "mglur5": _FC,
    "mglur6": _FC, "mglur7": _FC,
    "gaba_b": _FC, "glycine": _FC, "5ht3": _FC,
    "d1": _FC, "d2": _FC, "alpha2a": _FC,
    # Ion-channel + inhibitory chloride: family + class + sign.
    "gaba_a": _FCG, "gaba_a_rho": _FCG,
    # D-quotes that state the sign (excitatory / inhibitory) + G-protein coupling.
    "d3": _FCG, "d4": _FCG, "d5": _FCG,
    # "postsynaptic ... G-protein-linked" histamine quotes: family + class + site.
    "h1": _FCY, "h2": _FCY,
    # 5-HT1B/D: "inhibitory ... G-protein-coupled" backs family + class + sign. Its
    # record synaptic="both" is backed by TWO quotes via RECEPTOR_ATTR_QUOTES below (the
    # main quote's "postsynaptic 5HT1B/D" + the p131 presynaptic-autoreceptor list), so
    # `synaptic` is covered there, not here.
    "5ht1b": _FCG, "5ht1d": _FCG,
    # Pure NE enumeration: only names the family, nothing mechanistic.
    "alpha1a": _F, "alpha1b": _F, "alpha1c": _F, "alpha1d": _F,
    "alpha2b": _F, "alpha2c": _F, "beta1": _F, "beta2": _F, "beta3": _F,
    # 5-HT sign sentence: family + the excitatory/inhibitory sign it lists.
    "5ht1a": _FG, "5ht2a": _FG, "5ht2c": _FG, "5ht4": _FG, "5ht5a": _FG, "5ht6": _FG,
    # 5-HT2B quote calls it a *presynaptic autoreceptor*; the record's synaptic was
    # corrected to "presynaptic" to match, so family + site are backed (sign/class not).
    "5ht2b": _FY,
    # "5HT7 receptors are postsynaptic, excitatory": family + sign + site.
    "5ht7": _FGY,
    # Opioid quote says only "synapse with postsynaptic sites", but the record is
    # synaptic="both" (opioid receptors are genuinely pre- AND postsynaptic
    # autoreceptors/heteroreceptors). Stahl Essential never states the presynaptic
    # half anywhere in the corpus, so the postsynaptic-only quote cannot back "both":
    # family alone is covered and synaptic stays honestly llm (cf. 5-HT1B/D, which
    # DID have a presynaptic p131 quote to complete its "both" via RECEPTOR_ATTR_QUOTES).
    "mu": _F, "delta": _F, "kappa": _F,
    # CB1 "presynaptic ... inhibition of release" but record sign="modulatory", so
    # only the presynaptic site is backed, not the sign.
    "cb1": _FY,
    # Existence-only / enumeration quotes: family alone.
    "a2a": _F, "sigma1": _F, "mt1": _F, "mt2": _F, "h4": _F,
    # H3 "presynaptic autoreceptors": family + site.
    "h3": _FY,
}

# Per-attribute quote overrides. A quote need not be the same across the four
# classification attributes: when an attribute needs a DIFFERENT sentence than the
# receptor's main STAHL_ESSENTIAL_RECEPTOR_QUOTES quote, or several sentences to back a
# compound value, list them here as {receptor_id: {attr: [quote, ...]}}. An attribute
# listed here is graded from these quotes (and marked covered) instead of the main quote;
# an unlisted attribute keeps the main-quote-via-COVERAGE behaviour. This is how a
# `synaptic="both"` earns `verified`: it needs one quote per direction.
RECEPTOR_ATTR_QUOTES: dict[str, dict[str, list[dict[str, Any]]]] = {
    # 5-HT1B/D are both pre- and postsynaptic: the p406 quote states "postsynaptic
    # 5HT1B/D", the p131 list states they are presynaptic autoreceptors. Together the two
    # directions back the record's synaptic="both".
    "5ht1b": {"synaptic": [_SE_5HT1BD, _SE_5HT_PRESYN_AUTO]},
    "5ht1d": {"synaptic": [_SE_5HT1BD, _SE_5HT_PRESYN_AUTO]},
}

STAHL_ESSENTIAL_TARGET_QUOTES: dict[str, dict[str, Any]] = {
    "sert": _stahl_ess(131,
        "There is also a presynaptic transport pump selective for serotonin, "
        "called the serotonin transporter (SERT), which clears serotonin out of "
        "the synapse and back into the presynaptic neuron."),
    "net": _stahl_ess(271,
        "The norepinephrine transporter (NET) exists presynaptically and is "
        "responsible for clearing excess norepinephrine out of the synapse."),
    "dat": _stahl_ess(96,
        "Dopamine can be transported out of the synaptic cleft and back into the "
        "presynaptic neuron via the dopamine transporter (DAT), where it may be "
        "repackaged for future use."),
    "gat": _stahl_ess(274,
        "GABA's synaptic actions are terminated by the presynaptic GABA "
        "transporter (GAT), also known as the GABA reuptake pump (Figure 6-18), "
        "analogous to similar transporters for other neurotransmitters discussed "
        "throughout this text."),
    # p191 names VMAT2 in the *dopamine* context (backs system=dopaminergic) and
    # states it packages monoamines *into* vesicles for storage (backs the vesicular
    # polarity: inhibiting it depletes -> lowers tone). Preferred over the p269 NE
    # sentence, which named only norepinephrine and so did not source the dopaminergic
    # system this target is filed under.
    "vmat2": _stahl_ess(191,
        "The VMAT2 is an intraneuronal transporter located on synaptic vesicles. "
        "VMAT2 takes intraneuronal monoamines, including dopamine, up into the "
        "synaptic vesicles so that they can be stored until they are needed for "
        "release during neurotransmission."),
    "mao_a": _stahl_ess(355,
        "The enzyme MAO-A metabolizes serotonin (5HT) and norepinephrine (NE) as "
        "well as dopamine (DA) (left panels)."),
    "mao_b": _stahl_ess(96,
        "Other enzymes that break down dopamine are monoamine oxidase A (MAO-A) "
        "and monoamine oxidase B (MAO-B), which are present in mitochondria within "
        "the presynaptic neuron and in other cells such as glia."),
    "ache": _SE_CHE, "bche": _SE_CHE,
    "nav": _SE_VSC, "cav": _SE_VSC,
    "cav_a2d": _stahl_ess(413,
        "Alpha-2-delta ligands such as gabapentin or pregabalin bind to the α2δ "
        "subunit of voltage-sensitive calcium channels (VSCCs), changing their "
        "conformation to reduce calcium influx and therefore reduce excessive "
        "stimulation of postsynaptic receptors."),
    "sv2a": _stahl_ess(51,
        "A novel 12-transmembrane-region synaptic vesicle transporter of uncertain "
        "mechanism and with unclear substrates, called the SV2A transporter and "
        "localized within the synaptic vesicle membrane, binds the anticonvulsant "
        "levetiracetam, perhaps interfering with neurotransmitter release and "
        "thereby reducing seizures."),
    "muscarinic": _SE_MUSCARINIC,
    "nicotinic": _stahl_ess(524,
        "Acetylcholine neurotransmission can be regulated by ligand-gated "
        "excitatory ion channels known as nicotinic acetylcholine receptors, "
        "shown here."),
    "alpha1": _SE_NE_GROUPS, "alpha2": _SE_NE_GROUPS, "beta": _SE_NE_GROUPS,
    "glutamate": _stahl_ess(92,
        "The other subclass of ligand-gated ion channels has a tetrameric "
        "structure, and includes many glutamate receptors, including the AMPA, "
        "kainate, and NMDA subtypes."),
    "melatonin": _SE_MELATONIN,
    "orexin": _stahl_ess(425,
        "Orexin neurotransmission is mediated by two types of postsynaptic "
        "G-protein-coupled receptors, orexin 1 (OX1R) and orexin 2 (OX2R)."),
}

# A non-receptor target's tone POLARITY (does engaging it raise or lower the
# system's tone) is a *separate, direction-bearing* claim from its type/system
# classification: the `vesicular` / `sign` / `synaptic` flags flip the drug-flow
# overlay's sign (js/data.js toneSignOf), so a wrong flag inverts a drug's
# apparent effect on tone (this is exactly the VMAT2 boost/block bug). It is
# therefore its own graded node (kind `target_polarity`) instead of silently
# inheriting the classification grade from a quote that never addressed direction.
# Only targets carrying a polarity flag get one. Absent from this dict -> honestly
# `llm` (unchecked), even if the flag is textbook-correct.
TARGET_POLARITY_QUOTES: dict[str, dict[str, Any]] = {
    # The same Stahl-Essential sentence that names VMAT2 also states it packages
    # monoamines *into* vesicles, so inhibiting it depletes -> lowers tone. That
    # genuinely backs the `vesicular` flag, so its polarity is verified.
    "vmat2": STAHL_ESSENTIAL_TARGET_QUOTES["vmat2"],
    # NOTE: `alpha2` is deliberately NOT here. Its classification quote
    # (_SE_NE_GROUPS) only classifies α2 as an NE receptor family; it does NOT
    # state the presynaptic *inhibitory autoreceptor* character its sign/synaptic
    # flags encode. That claim is textbook-correct but not yet quote-verified, so
    # its polarity honestly grades `llm`. TODO: add an α2-autoreceptor quote
    # (author-side, quote-gated) to upgrade it.
}

PROJECTIONS: list[dict[str, Any]] = [
    # --- Corticostriatal input (glutamate): cortex drives the striatum ---
    dict(**{"from": "frontal_R", "to": "putamen_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (motor)",
         description="Sensorimotor frontal cortex drives the putamen, the motor "
                     "input nucleus of the basal ganglia."),
    dict(**{"from": "frontal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (associative)",
         description="Prefrontal cortex drives the caudate (associative striatum)."),
    dict(**{"from": "parietal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (parietal)",
         description="Posterior parietal association cortex projects to the caudate."),
    dict(**{"from": "temporal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (temporal)",
         description="Temporal association cortex projects to the striatum."),
    # --- Hyperdirect (glutamate): cortex excites the STN directly ---
    dict(**{"from": "frontal_R", "to": "subthalamic_nucleus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Hyperdirect (corticosubthalamic)",
         description="Cortex excites the subthalamic nucleus directly, the fast "
                     "'hyperdirect' brake on movement."),
    # --- Direct pathway (GABA): striatum inhibits the output nuclei ---
    dict(**{"from": "putamen_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatopallidal (direct)",
         description="Direct-pathway striatal neurons inhibit the internal "
                     "pallidum, releasing (disinhibiting) the thalamus."),
    dict(**{"from": "caudate_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatopallidal (direct)",
         description="Caudate direct-pathway output to the internal pallidum."),
    dict(**{"from": "putamen_R", "to": "substantia_nigra_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatonigral (direct)",
         description="Direct-pathway striatal output to the substantia nigra "
                     "pars reticulata."),
    dict(**{"from": "caudate_R", "to": "substantia_nigra_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatonigral (direct)",
         description="Caudate direct-pathway output to the substantia nigra."),
    # --- Indirect pathway (GABA out, glutamate back via STN) ---
    dict(**{"from": "globus_pallidus_R", "to": "subthalamic_nucleus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Pallidosubthalamic (indirect)",
         description="External pallidum inhibits the STN in the indirect pathway."),
    dict(**{"from": "subthalamic_nucleus_R", "to": "globus_pallidus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Subthalamopallidal",
         description="The STN excites the pallidum, amplifying basal-ganglia "
                     "output (indirect/hyperdirect pathways)."),
    # --- Dopaminergic modulation (nigrostriatal) ---
    dict(**{"from": "substantia_nigra_R", "to": "putamen_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Nigrostriatal",
         description="Substantia nigra pars compacta dopamine sets the balance "
                     "between the direct and indirect striatal pathways."),
    dict(**{"from": "substantia_nigra_R", "to": "caudate_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Nigrostriatal",
         description="Dopaminergic modulation of the caudate."),
    # --- Basal-ganglia output to the thalamus (GABA) ---
    dict(**{"from": "globus_pallidus_R", "to": "thalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Pallidothalamic",
         description="The internal pallidum tonically inhibits the motor "
                     "thalamus, the output gate of the loop."),
    dict(**{"from": "substantia_nigra_R", "to": "thalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Nigrothalamic",
         description="Substantia nigra pars reticulata inhibitory output to the "
                     "thalamus."),
    # --- Thalamocortical closure + sensory corticothalamic (glutamate) ---
    dict(**{"from": "thalamus_R", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Thalamocortical",
         description="Motor thalamus excites frontal cortex, closing the "
                     "cortico-basal-ganglia-thalamo-cortical loop."),
    dict(**{"from": "occipital_R", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticothalamic (visual)",
         description="Occipital (visual) cortex reciprocally connects with the "
                     "thalamus (pulvinar / lateral geniculate)."),
    # --- Cortico-ponto-cerebellar and cerebellar output ---
    dict(**{"from": "frontal_R", "to": "pons"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticopontine",
         description="Cortex projects to the pontine nuclei (pons), the "
                     "first leg of the cortico-ponto-cerebellar route."),
    dict(**{"from": "pons", "to": "cerebellum"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Pontocerebellar (mossy fibers)",
         description="Pontine nuclei send mossy fibers to the cerebellar cortex."),
    dict(**{"from": "cerebellum", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Cerebellothalamic (dentatothalamic)",
         description="Deep cerebellar nuclei drive the motor thalamus, feeding "
                     "the cerebellar loop back to cortex."),
    # --- Limbic (Papez) circuit ---
    dict(**{"from": "temporal_R", "to": "hippocampus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Perforant path",
         description="Entorhinal (medial temporal) cortex drives the hippocampus "
                     "via the perforant path."),
    dict(**{"from": "hippocampus_R", "to": "fornix_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Fornix (hippocampal output)",
         description="The major hippocampal output gathers into the fornix, the "
                     "great arching tract of the Papez circuit."),
    dict(**{"from": "fornix_R", "to": "mammillary_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Postcommissural fornix",
         description="The fornix carries hippocampal output forward to the "
                     "mammillary bodies (Papez circuit)."),
    dict(**{"from": "mammillary_R", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Mammillothalamic tract",
         description="Mammillary bodies project to the anterior thalamic nuclei, "
                     "continuing the Papez circuit."),
    dict(**{"from": "thalamus_R", "to": "cingulate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Anterior thalamocingulate",
         description="The anterior thalamic nuclei project to the cingulate "
                     "gyrus, the next leg of the Papez circuit."),
    dict(**{"from": "cingulate_R", "to": "hippocampus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Cingulum (to hippocampus)",
         description="The cingulate gyrus projects back to the hippocampus via "
                     "the cingulum, closing the Papez loop."),
    # --- Olfactory, amygdalar and septal limbic links ---
    dict(**{"from": "olfactory_bulb_R", "to": "amygdala_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Olfactory projection (to amygdala)",
         description="Mitral cells of the olfactory bulb project to the "
                     "corticomedial amygdala."),
    dict(**{"from": "olfactory_bulb_R", "to": "insula_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Olfactory projection (to olfactory cortex)",
         description="Bulbar output reaches the piriform / insular olfactory "
                     "cortex."),
    dict(**{"from": "amygdala_R", "to": "hypothalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Stria terminalis",
         description="The amygdala projects to the hypothalamus via the stria "
                     "terminalis, driving autonomic / endocrine responses."),
    dict(**{"from": "hippocampus_R", "to": "septal_nuclei_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Hippocamposeptal projection",
         description="Hippocampal fibers run in the precommissural fornix to the "
                     "septal nuclei."),
    dict(**{"from": "septal_nuclei_R", "to": "hippocampus_R"},
         kind="cholinergic", neurotransmitter="Acetylcholine",
         label="Septohippocampal pathway",
         description="Medial septal cholinergic neurons project to the "
                     "hippocampus, pacing the hippocampal theta rhythm."),
    # --- Ventral striatum (reward) and the neuroendocrine outflow ---
    # (The mesolimbic dopamine pathway is vta -> accumbens, defined below; the
    # substantia nigra projects to the dorsal striatum, i.e. the nigrostriatal
    # caudate/putamen arrows above, not to the accumbens.)
    dict(**{"from": "accumbens_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Accumbens to ventral pallidum",
         description="Nucleus accumbens medium spiny neurons project to the "
                     "(ventral) pallidum, the ventral-striatal output."),
    dict(**{"from": "hypothalamus_R", "to": "pituitary"},
         kind="neuroendocrine", neurotransmitter="Releasing hormones",
         label="Hypothalamo-hypophyseal axis",
         description="Hypothalamic neurons drive the pituitary via the median "
                     "eminence / portal system and the posterior hypophyseal "
                     "tract."),
    # --- Ascending monoamine systems: the diffuse projections from the brainstem
    #     source nuclei (raphe = serotonin, locus coeruleus = noradrenaline, VTA =
    #     dopamine). These anchor the per-drug "by-mechanism flow" overlay: focusing
    #     an SSRI lights the serotonergic fan, an SNRI the noradrenergic one, etc.
    #     (see js/drug-anim.js). raphe is midline, so its arrows mirror only on the
    #     target side; locus coeruleus / VTA are paired and mirror fully. ---
    dict(**{"from": "raphe", "to": "frontal_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (prefrontal)",
         description="Dorsal raphe serotonin neurons project diffusely to the "
                     "prefrontal cortex, shaping mood and cognition."),
    dict(**{"from": "raphe", "to": "hippocampus_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (hippocampal)",
         description="Median raphe serotonin projects to the hippocampus."),
    dict(**{"from": "raphe", "to": "amygdala_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (amygdala)",
         description="Raphe serotonin modulates the amygdala, tuning emotional "
                     "reactivity."),
    dict(**{"from": "raphe", "to": "hypothalamus_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (hypothalamic)",
         description="Raphe serotonin projects to the hypothalamus, influencing "
                     "sleep, appetite and neuroendocrine rhythms."),
    dict(**{"from": "locus_coeruleus_R", "to": "frontal_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (prefrontal)",
         description="Locus coeruleus noradrenaline projects diffusely to the "
                     "cortex, driving arousal and attention."),
    dict(**{"from": "locus_coeruleus_R", "to": "hippocampus_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (hippocampal)",
         description="Locus coeruleus noradrenaline projects to the hippocampus."),
    dict(**{"from": "locus_coeruleus_R", "to": "amygdala_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (amygdala)",
         description="Locus coeruleus noradrenaline sharpens amygdala-dependent "
                     "emotional memory."),
    dict(**{"from": "locus_coeruleus_R", "to": "thalamus_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (thalamic)",
         description="Locus coeruleus noradrenaline projects to the thalamus."),
    dict(**{"from": "vta_R", "to": "accumbens_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic (VTA)",
         description="VTA dopamine projects to the nucleus accumbens, the core "
                     "of the reward pathway."),
    dict(**{"from": "vta_R", "to": "frontal_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesocortical",
         description="VTA dopamine projects to the prefrontal cortex, supporting "
                     "motivation and executive control."),
    dict(**{"from": "vta_R", "to": "amygdala_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic (amygdala)",
         description="VTA dopamine innervates the amygdala."),
    dict(**{"from": "vta_R", "to": "hippocampus_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic (hippocampal)",
         description="VTA dopamine projects to the hippocampus, gating "
                     "reward-related memory."),
    # --- Interhemispheric commissures (bidirectional, defined once across the
    #     midline so symmetric=False keeps them from mirroring into duplicates) ---
    dict(**{"from": "frontal_L", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (frontal)", bidirectional=True, symmetric=False,
         description="Homotopic callosal fibers linking the two frontal lobes."),
    dict(**{"from": "parietal_L", "to": "parietal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (parietal)", bidirectional=True, symmetric=False,
         description="Homotopic callosal fibers linking the two parietal lobes."),
    dict(**{"from": "occipital_L", "to": "occipital_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (splenium / occipital)", bidirectional=True,
         symmetric=False,
         description="Splenial callosal fibers linking the two occipital lobes."),
    dict(**{"from": "temporal_L", "to": "temporal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Anterior commissure", bidirectional=True, symmetric=False,
         description="Older commissure linking the temporal lobes (and olfactory "
                     "structures)."),
    # --- Plausible / speculative pathways (tentative=True) -------------------
    # Anatomically reasonable but less certain or more diffuse than the pathways
    # above. The viewer lists these in a separate, off-by-default legend section
    # and draws them as dotted arrows, so they read as "maybe" rather than fact.
    # ``tentative`` is carried through to the emitted projection record.
    dict(**{"from": "claustrum_R", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Claustro-frontal projection", bidirectional=True,
         description="Reciprocal claustro-cortical link with prefrontal cortex "
                     "(implicated in salience / attention)."),
    dict(**{"from": "claustrum_R", "to": "insula_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Claustro-insular projection", bidirectional=True,
         description="The claustrum tightly interconnects with the adjacent "
                     "insular cortex."),
    dict(**{"from": "insula_R", "to": "cingulate_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Salience network link", bidirectional=True,
         description="The anterior insula and the cingulate co-activate as the "
                     "salience network."),
    dict(**{"from": "amygdala_R", "to": "accumbens_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Basolateral amygdala to accumbens",
         description="Basolateral amygdala glutamatergic input to the ventral "
                     "striatum (motivational salience)."),
    # (No mammillary -> hypothalamus arrow: Kandel treats the mammillary bodies
    # as part of the posterior hypothalamus, so that is anatomical containment,
    # not a projection. The bodies' real efferent is the mammillothalamic tract,
    # mammillary -> thalamus, modeled above.)
    dict(**{"from": "septal_nuclei_R", "to": "hypothalamus_R"},
         kind="inhibitory", neurotransmitter="GABA", tentative=True,
         label="Septohypothalamic projection",
         description="The septal nuclei project to the hypothalamus, a limbic-"
                     "autonomic relay."),
]

# Named circuits: curated bundles of structures that, together, form a classic
# functional loop. The viewer adds a "Circuits" section to the legend; clicking a
# circuit isolates exactly its structures and lights only the projections *between
# them* (every other structure + arrow fades), so a whole pathway can be inspected
# at once.
#
# A circuit lists structures by their **base** id (no ``_R``/``_L`` suffix); the
# generator expands each to whatever was actually emitted (both hemispheres for a
# paired structure, the bare id for a midline one) and writes a ``circuit`` record
# with the concrete ids. The arrows are derived in the viewer (an arrow belongs to
# the circuit when *both* its endpoints are circuit structures), so circuits never
# duplicate the projection list: edit a pathway once in PROJECTIONS and the
# circuits that span it follow. ``structures`` must name real bases (the generator
# raises on a typo).
CIRCUITS: list[dict[str, Any]] = [
    dict(id="bg_direct", name="Direct pathway (motor)",
         wikipedia="https://en.wikipedia.org/wiki/Direct_pathway",
         sources=[_KQ_BG_DIRECT],
         description="The movement-promoting basal-ganglia loop: cortex excites "
                     "the striatum, which inhibits the GPi/SNr output, releasing "
                     "the thalamus to drive cortex.",
         description_fr="La boucle des noyaux gris centraux favorisant le "
                        "mouvement : le cortex active le striatum, qui inhibe la "
                        "sortie GPi/SNr, libérant le thalamus pour activer le "
                        "cortex.",
         # Cortex -> striatum -> GPi/SNr -> thalamus -> cortex: the movement-
         # promoting basal-ganglia loop (plus the nigrostriatal dopamine input).
         structures=["frontal", "putamen", "globus_pallidus",
                     "substantia_nigra", "thalamus"]),
    dict(id="bg_indirect", name="Indirect pathway",
         wikipedia="https://en.wikipedia.org/wiki/Indirect_pathway",
         sources=[_KQ_BG_INDIRECT],
         description="The movement-suppressing loop, routed through the subthalamic "
                     "nucleus, which drives the GPi/SNr to clamp the thalamus.",
         description_fr="La boucle supprimant le mouvement, passant par le noyau "
                        "sous-thalamique, qui active le GPi/SNr pour brider le "
                        "thalamus.",
         # The movement-suppressing loop, routing through the subthalamic nucleus
         # (and the cortico-subthalamic "hyperdirect" shortcut).
         structures=["frontal", "putamen", "globus_pallidus",
                     "subthalamic_nucleus", "thalamus"]),
    dict(id="nigrostriatal", name="Nigrostriatal (dopamine)",
         wikipedia="https://en.wikipedia.org/wiki/Nigrostriatal_pathway",
         sources=[_KQ_NIGROSTRIATAL],
         description="The dopaminergic projection from the substantia nigra to the "
                     "striatum whose loss causes Parkinson's disease.",
         description_fr="La projection dopaminergique de la substance noire vers le "
                        "striatum dont la perte cause la maladie de Parkinson.",
         # The dopaminergic projection whose loss causes Parkinson's, with the
         # reciprocal striatonigral return.
         structures=["substantia_nigra", "putamen", "caudate"]),
    dict(id="cerebellar_motor", name="Cortico-cerebellar (motor)",
         sources=[_KQ_CORTICOPONTINE],
         description="The coordination loop: cortex to pons to cerebellum to "
                     "thalamus and back, tuning the timing of movement.",
         description_fr="La boucle de coordination : cortex vers pont vers cervelet "
                        "vers thalamus et retour, ajustant le timing du mouvement.",
         # Cortex -> pons -> cerebellum -> thalamus -> cortex: the coordination
         # loop running through the pons and cerebellum.
         structures=["frontal", "pons", "cerebellum", "thalamus"]),
    dict(id="limbic_memory", name="Hippocampal / limbic (Papez)",
         wikipedia="https://en.wikipedia.org/wiki/Papez_circuit",
         sources=[_KQ_PAPEZ],
         description="The Papez circuit: the medial-temporal memory loop through "
                     "hippocampus, fornix, mammillary bodies, anterior thalamus "
                     "and cingulate.",
         description_fr="Le circuit de Papez : la boucle mnésique médio-temporale "
                        "par l'hippocampe, le fornix, les corps mammillaires, le "
                        "thalamus antérieur et le cingulum.",
         # The medial-temporal memory loop, now wired through the real fornix,
         # mammillary and cingulate nodes: temporal -> hippocampus -> fornix ->
         # mammillary -> (anterior) thalamus -> cingulate -> hippocampus.
         structures=["temporal", "hippocampus", "fornix", "mammillary",
                     "thalamus", "cingulate"]),
    dict(id="commissures", name="Commissures (interhemispheric)",
         wikipedia="https://en.wikipedia.org/wiki/Commissural_fiber",
         sources=[_KQ_CORPUS_CALLOSUM],
         description="The interhemispheric bridges (corpus callosum + anterior "
                     "commissure) linking matching cortical areas across the "
                     "midline.",
         description_fr="Les ponts interhémisphériques (corps calleux + commissure "
                        "antérieure) reliant les aires corticales homologues à "
                        "travers la ligne médiane.",
         # The left-right cortical bridges: corpus callosum + anterior commissure.
         # Only same-lobe cross-midline arrows fall *between* these structures.
         structures=["frontal", "parietal", "temporal", "occipital"]),
]

# Projection groups: the legend's per-pathway rows promoted to a sourced data
# structure (so a group row opens a detail panel like a structure / receptor /
# drug, not just a focus toggle). The viewer groups the projection arrows two
# ways depending on the arrow colour mode, so there is one record per group in
# BOTH modes:
#   mode="kind" : one per neurotransmitter kind (the default per-transmitter rows,
#                 e.g. "Serotonin (serotonergic)"); ``key`` is a PROJECTION_COLORS
#                 kind.
#   mode="sign" : one per coarse excit/inhib/modulatory sign (the "Potential"
#                 colour mode rows); ``key`` is a SIGN_LABELS sign.
# Each record carries a ``name`` + ``description`` (inline {en,fr}, so they bypass
# the shared FR table like the receptor descriptions), a ``wikipedia`` reference
# and optional ``sources`` (quote-level {corpus, page, quote, provenance} dicts).
# The member pathways are NOT listed here: the
# viewer derives them (the projections whose kind / sign matches ``key``), exactly
# as a circuit derives its arrows, so a group never duplicates the projection list.
# ``classification_provenance`` grades the grouping/description (LLM-authored); an
# optional ``sources`` list carries a verified quote backing the group's identity.
#
# Verified quote-sources for the group nodes, defined once and referenced by the
# entries below (no quote text duplicated). Transmitter groups get a defining
# sentence from Stahl Essential / Kandel; the two sign groups excitatory/inhibitory
# reuse their dominant transmitter's quote (glutamate = excitatory, GABA =
# inhibitory) and the dopaminergic group reuses the nigrostriatal quote already
# verified for its member projections.
_SG_GLUTAMATE = _stahl_ess(112,
    "Glutamate is the major excitatory neurotransmitter in the central nervous system")
_SG_GABA = _stahl_ess(271,
    "GABA is the principle inhibitory neurotransmitter in the brain, and normally "
    "serves an important regulatory role in reducing the activity of many neurons.")
_SG_ACH = _kandel(1047,
    "These neurons project throughout the cerebral cortex, hippocampus, and amygdala. "
    "Both groups play an important role in arousal, and the basal forebrain groups are "
    "also involved in more selective attention.")
_SG_NEUROENDOCRINE = _kandel(1075,
    "A group of hypothalamic peptide hormones that control pituitary hormone secretion "
    "from the five classic endocrine cell types in the anterior pituitary.")
_SG_SEROTONIN = _kandel(1048,
    "The B5-B7 neurons in the pons mainly provide serotonergic innervation of the "
    "thalamus, hypothalamus, and cerebral cortex.")
_SG_NORADRENALINE = _kandel(1561,
    "The major noradrenergic projection of the forebrain arises in the locus ceruleus.")
_SG_MODULATORY = _kandel(368,
    "Neuromodulators are substances that bind to receptors, most of which are "
    "metabotropic, to alter the excitability of neurons, the likelihood of transmitter "
    "release, or the functional state of receptors on postsynaptic neurons.")
PROJECTION_GROUPS: list[dict[str, Any]] = [
    # --- per-neurotransmitter (mode="kind"); name = the transmitter molecule -----
    dict(mode="kind", key="excitatory", name="Glutamate",
         sources=[_SG_GLUTAMATE],
         description="The brain's main excitatory transmitter: glutamatergic "
                     "projections drive their targets, including the "
                     "corticostriatal and thalamocortical pathways.",
         description_fr="Le principal neurotransmetteur excitateur du cerveau : les "
                        "projections glutamatergiques activent leurs cibles, dont "
                        "les voies cortico-striées et thalamo-corticales.",
         wikipedia="https://en.wikipedia.org/wiki/Glutamate_(neurotransmitter)"),
    dict(mode="kind", key="inhibitory", name="GABA",
         sources=[_SG_GABA],
         description="The brain's main inhibitory transmitter: GABAergic "
                     "projections suppress their targets, including the striatal "
                     "output of the basal ganglia.",
         description_fr="Le principal neurotransmetteur inhibiteur du cerveau : les "
                        "projections GABAergiques freinent leurs cibles, dont la "
                        "sortie striatale des noyaux gris centraux.",
         wikipedia="https://en.wikipedia.org/wiki/Gamma-Aminobutyric_acid"),
    dict(mode="kind", key="dopaminergic", name="Dopamine",
         sources=[_KQ_NIGROSTRIATAL],
         description="Dopaminergic projections from the midbrain (substantia "
                     "nigra, VTA) modulate movement, motivation and reward.",
         description_fr="Les projections dopaminergiques du mésencéphale (substance "
                        "noire, ATV) modulent le mouvement, la motivation et la "
                        "récompense.",
         wikipedia="https://en.wikipedia.org/wiki/Dopaminergic_pathways"),
    dict(mode="kind", key="cholinergic", name="Acetylcholine",
         sources=[_SG_ACH],
         description="Cholinergic projections modulate arousal, attention and "
                     "memory across the cortex and hippocampus.",
         description_fr="Les projections cholinergiques modulent l'éveil, "
                        "l'attention et la mémoire dans le cortex et l'hippocampe.",
         wikipedia="https://en.wikipedia.org/wiki/Cholinergic"),
    dict(mode="kind", key="neuroendocrine", name="Releasing hormones",
         sources=[_SG_NEUROENDOCRINE],
         description="Hypothalamic neuroendocrine projections release hormones "
                     "that control the pituitary and the body's endocrine axes.",
         description_fr="Les projections neuroendocrines de l'hypothalamus libèrent "
                        "des hormones qui contrôlent l'hypophyse et les axes "
                        "endocriniens.",
         wikipedia="https://en.wikipedia.org/wiki/Releasing_hormone"),
    dict(mode="kind", key="serotonergic", name="Serotonin",
         sources=[_SG_SEROTONIN],
         description="Serotonergic projections from the raphe nuclei diffusely "
                     "modulate mood, sleep and appetite throughout the brain.",
         description_fr="Les projections sérotoninergiques des noyaux du raphé "
                        "modulent diffusément l'humeur, le sommeil et l'appétit "
                        "dans tout le cerveau.",
         wikipedia="https://en.wikipedia.org/wiki/Serotonergic"),
    dict(mode="kind", key="noradrenergic", name="Noradrenaline",
         sources=[_SG_NORADRENALINE],
         description="Noradrenergic projections from the locus coeruleus modulate "
                     "arousal, vigilance and the stress response.",
         description_fr="Les projections noradrénergiques du locus coeruleus "
                        "modulent l'éveil, la vigilance et la réponse au stress.",
         wikipedia="https://en.wikipedia.org/wiki/Norepinephrine"),
    # --- per-sign (mode="sign"); name = the SIGN_LABELS heading ------------------
    dict(mode="sign", key="excitatory", name="Excitatory",
         sources=[_SG_GLUTAMATE],
         description="Excitatory pathways depolarize their target, making it more "
                     "likely to fire (mainly glutamatergic).",
         description_fr="Les voies excitatrices dépolarisent leur cible, la rendant "
                        "plus susceptible de décharger (surtout glutamatergiques).",
         wikipedia="https://en.wikipedia.org/wiki/Excitatory_postsynaptic_potential"),
    dict(mode="sign", key="inhibitory", name="Inhibitory",
         sources=[_SG_GABA],
         description="Inhibitory pathways hyperpolarize their target, making it "
                     "less likely to fire (mainly GABAergic).",
         description_fr="Les voies inhibitrices hyperpolarisent leur cible, la "
                        "rendant moins susceptible de décharger (surtout "
                        "GABAergiques).",
         wikipedia="https://en.wikipedia.org/wiki/Inhibitory_postsynaptic_potential"),
    dict(mode="sign", key="modulatory", name="Modulatory",
         sources=[_SG_MODULATORY],
         description="Modulatory pathways (the monoamines and acetylcholine) tune "
                     "the gain and excitability of their targets rather than "
                     "directly exciting or inhibiting them.",
         description_fr="Les voies modulatrices (monoamines et acétylcholine) "
                        "ajustent le gain et l'excitabilité de leurs cibles plutôt "
                        "que de les exciter ou inhiber directement.",
         wikipedia="https://en.wikipedia.org/wiki/Neuromodulation"),
]


# Neurotransmitter receptors. Each entry is one receptor (the clinically relevant
# brain receptors from Wikipedia's "Example neurotransmitter receptors" table plus
# a few major psychiatric ones it omits: CB1, A2A, sigma-1, MT1/MT2). The viewer
# lists them in a legend section grouped by ``family`` (the neurotransmitter
# system); focusing a receptor dims the brain and lights glowing dots on every
# structure in ``locations`` (both hemispheres), and opens an info panel built
# from these fields. See "Changing the data" in CLAUDE.md.
#
#   id              : short slug (also the DOM-safe handle in the viewer)
#   name            : technical display name (language-neutral, e.g. "5-HT2A")
#   family          : neurotransmitter system, key of RECEPTOR_FAMILY_LABELS
#   neurotransmitter: the endogenous ligand (translatable)
#   receptor_class  : "ionotropic" | "metabotropic" | "chaperone"
#                     (key of RECEPTOR_CLASS_LABELS)
#   sign            : "excitatory" | "inhibitory" | "modulatory" (reuses the arrow
#                     SIGN_COLORS / SIGN_LABELS so the legend swatch matches)
#   synaptic        : "presynaptic" | "postsynaptic" | "both"
#                     (key of SYNAPTIC_LABELS)
#   locations       : list of structure *base* ids where it is expressed, OR the
#                     sentinel "ALL" for a brain-wide receptor (emitted as
#                     ``ubiquitous`` so the viewer lights every structure). An
#                     EMPTY list (no description) is a deliberate "stub": a
#                     receptor with no meaningful CNS/psychiatric role, listed for
#                     completeness but not focusable.
#   description     : one-line {en}; description_fr is its French (authored inline,
#                     unique per receptor, so it bypasses the shared FR table).
#                     Omitted on stubs.
#   wikipedia       : source article (rendered as a link in the info panel)
#
# Sourced from each receptor's linked Wikipedia article (the receptor info panel
# shows that link). Locations were mapped onto the modeled structures (e.g.
# striatum -> caudate+putamen, "cortex" -> the four lobes, raphe/locus coeruleus/
# VTA -> the new source nuclei); peripheral-only sites (gut, heart, retina, spinal
# cord, immune) were dropped as out of scope for a brain viewer.
# RECEPTORS (the 63 per-family classification dicts) is imported at the top
# from data_generators.receptors; the field schema is documented above.


def _structure_record(entry: dict[str, Any], structure_id: str,
                      name: dict[str, str], base_name: dict[str, str],
                      position: tuple[float, float, float], shape_id: str,
                      mirror: bool = False,
                      images: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build one ``structure`` JSONL record (the non-geometric metadata).

    Parameters
    ----------
    entry
        Source definition from :data:`PAIRED` / :data:`MIDLINE`.
    structure_id
        Final id including hemisphere suffix (e.g. ``"putamen_R"``).
    name
        Bilingual ``{"en", "fr"}`` display name including the hemisphere
        prefix/suffix where relevant (``Right putamen`` / ``Putamen droit``).
    base_name
        Bilingual ``{"en", "fr"}`` base name without any hemisphere marker, used
        for the legend row so the two hemispheres collapse to one entry without
        the viewer string-stripping a language-specific "Right "/"Left " prefix.
    position
        Final ``(x, y, z)`` after any mirroring.
    shape_id
        Basename of the shared geometry file (``data/shapes/<shape_id>.json``). The
        two members of a symmetric pair point at the *same* right-side file; the
        left member sets ``mirror`` so the viewer reflects it across x.
    mirror
        When True, emit ``"mirror": true`` so ``js/shapes.js`` reflects the
        geometry across the sagittal plane (used only for the left member of a
        symmetric pair, never for midline structures).
    images
        Map of base id -> image record (see :func:`_load_structure_images` /
        ``tools/fetch_structure_images.py``); a match adds a ``structure_image`` url
        (the hero) and, when present, a ``structure_image_gallery`` list of further
        gif/svg urls the panel reveals on "show more". A non-match omits both.

    Returns
    -------
    dict
        Record ready to be JSON-serialized as one line of ``structures.jsonl``.
    """
    record = {
        "id": structure_id,
        "name": name,
        "base_name": base_name,
        "group": entry["group"],
        "position": [round(c, 3) for c in position],
        "color": entry["color"],
        "shape_file": f"data/shapes/{shape_id}.json",
        # Source grade backing this region's anatomy (its existence / group /
        # position), keyed by base so both hemispheres share one grade. Textbook
        # anatomy, so "llm" by default; override in STRUCTURE_PROVENANCE. Shown as
        # the panel's "Source" pill and counted in the coverage tally.
        "classification_provenance": _structure_provenance(entry["base"]),
    }
    # Attach a verified Kandel quote-source for the region's anatomy (keyed by base,
    # shared by both hemispheres) and upgrade the classification grade to match, so
    # the panel's Source pill carries the verbatim quote and the tally counts it.
    anatomy_quote = STRUCTURE_QUOTES.get(entry["base"])
    if anatomy_quote is not None:
        record["sources"] = [dict(anatomy_quote)]
        if _GRADE_RANK[anatomy_quote["provenance"]] > _GRADE_RANK[
                record["classification_provenance"]]:
            record["classification_provenance"] = anatomy_quote["provenance"]
    # External reference link (same article for both hemispheres of a pair),
    # tagged with its provenance grade for the source pill (see _wiki_provenance).
    wiki = WIKIPEDIA.get(entry["base"])
    if wiki:
        record["wikipedia"] = wiki
        record["wikipedia_provenance"] = _wiki_provenance(entry["base"])
    rec = images.get(entry["base"]) if images else None
    if rec and rec.get("url"):
        # Wikimedia url (not a local path): the GIFs are too large to vendor, so
        # the viewer hot-links them at runtime (spinner / silent-fail, see
        # showStructure). Keyed by base so both hemispheres share the one URL, and
        # only set when its base was resolved (so a structure without one renders no
        # image, no broken placeholder). The gallery (other gif/svg from the EN+FR
        # articles) rides alongside for the panel's "show more".
        record["structure_image"] = rec["url"]
        gallery = [g["url"] for g in rec.get("gallery", []) if g.get("url")]
        if gallery:
            record["structure_image_gallery"] = gallery
    if mirror:
        record["mirror"] = True
    return record


def _scale_sdf(node: dict[str, Any], s: list[float]) -> dict[str, Any]:
    """Recursively scale an SDF node tree about the local origin by ``s`` =
    ``[sx, sy, sz]`` (lengths along each axis scale by the matching factor).

    Used by :func:`_shape_record` to seat a structure at an anatomically-correct
    size without re-authoring every primitive. Scalar-radius primitives (sphere,
    round-cone/capsule, tube) and the isotropic blend/relief knobs (``k``,
    displace ``amp``/``unit``) can only take ONE factor, so they use the mean of
    ``s`` (an anisotropic swept tube would need an elliptic cross-section the SDF
    cannot express); displace ``freq`` scales inversely so the surface texture
    scales WITH the shape. Returns a NEW node, does not mutate the input. Every
    value is rounded to 4 decimals to keep the emitted JSON clean.
    """
    sm = sum(s) / 3.0
    r = lambda v: round(v, 4)

    def sc(v):  # scale a 3-vector coordinate / extent
        return [r(v[0] * s[0]), r(v[1] * s[1]), r(v[2] * s[2])]

    n = dict(node)
    prim = n.get("prim")
    if prim == "sphere":
        n["center"] = sc(n["center"]); n["radius"] = r(n["radius"] * sm)
    elif prim == "ellipsoid":
        n["center"] = sc(n["center"]); n["radii"] = sc(n["radii"])
    elif prim == "box":
        n["center"] = sc(n["center"]); n["half"] = sc(n["half"])
        if n.get("round") is not None:
            n["round"] = r(n["round"] * sm)
    elif prim in ("capsule", "roundcone"):
        n["a"] = sc(n["a"]); n["b"] = sc(n["b"])
        for key in ("r1", "r2", "radius"):
            if n.get(key) is not None:
                n[key] = r(n[key] * sm)
    elif prim == "tube":
        n["points"] = [sc(p) for p in n["points"]]
        if n.get("profile") is not None:
            n["profile"] = [r(p * sm) for p in n["profile"]]
        if n.get("radius") is not None:
            n["radius"] = r(n["radius"] * sm)
    elif prim == "plane":
        # Half-space cut moves with the geometry: the offset is along the
        # (un-normalized) normal, so scale it by the factor along that direction.
        nm = n["normal"]
        ln = math.sqrt(nm[0] ** 2 + nm[1] ** 2 + nm[2] ** 2) or 1.0
        f = (abs(nm[0]) * s[0] + abs(nm[1]) * s[1] + abs(nm[2]) * s[2]) / ln
        if n.get("offset") is not None:
            n["offset"] = r(n["offset"] * f)
    else:
        # Op node: scale the blend radius + any displacement, recurse into kids.
        if n.get("k") is not None:
            n["k"] = r(n["k"] * sm)
        if n.get("op") == "displace":
            if n.get("amp") is not None:
                n["amp"] = r(n["amp"] * sm)
            if n.get("freq"):
                n["freq"] = r(n["freq"] / sm)
            if n.get("unit"):
                n["unit"] = r(n["unit"] * sm)
            if n.get("origin"):
                n["origin"] = sc(n["origin"])
        if n.get("nodes") is not None:
            n["nodes"] = [_scale_sdf(c, s) for c in n["nodes"]]
        if n.get("node") is not None:
            n["node"] = _scale_sdf(n["node"], s)
    return n


def _scale_triple(scale: Any) -> list[float]:
    """Normalize a ``scale`` (scalar or ``[sx, sy, sz]``) to a 3-list."""
    if isinstance(scale, (int, float)):
        return [float(scale)] * 3
    return [float(c) for c in scale]


def _shape_record(entry: dict[str, Any], px: float) -> dict[str, Any]:
    """Build the geometric ``data/shapes/<id>.json`` payload for a structure.

    Most structures are ``blob``s (a noise-deformed ellipsoid) described by the
    ``radii``/``seed``/``detail``/``noise`` keys. An entry may instead provide a
    ready-made ``shape`` dict (e.g. ``type="curve"`` or ``type="composite"``), in
    which case it is used verbatim; see ``js/shapes.js`` for the consumers.

    Parameters
    ----------
    entry
        Source definition from :data:`PAIRED` / :data:`MIDLINE`.
    px
        The right-side ``x`` position the shared shape is built for (paired
        entries) or the structure's own ``x`` (midline). A ``medial`` lobe's
        flat cut plane is derived from it; the left member reuses the same file
        mirrored across x, which flips the plane to the correct side.
    """
    if "shape" in entry:
        shape = dict(entry["shape"])
        # Optional anatomical rescale (scalar or [sx, sy, sz]): shrink/grow a
        # structure to its correct relative size without re-authoring primitives.
        # Applied here (once, on the shared right-side shape) so the mirrored left
        # member inherits it. SDF only; the lone `curve` (fornix) is left as-is.
        if entry.get("scale") is not None and shape.get("type") == "sdf":
            s = _scale_triple(entry["scale"])
            shape["root"] = _scale_sdf(shape["root"], s)
            if "bounds" in shape:
                lo, hi = shape["bounds"]
                shape["bounds"] = [[round(lo[i] * s[i], 4) for i in range(3)],
                                   [round(hi[i] * s[i], 4) for i in range(3)]]
        return shape
    blob: dict[str, Any] = {
        "type": "blob",
        "radii": list(entry["radii"]),
        "seed": entry["seed"],
        "detail": entry["detail"],
        "noise": entry["noise"],
    }
    # Optional surface-character knobs (see buildBlobGeometry in js/shapes.js).
    # Only emitted when set, so plain smooth nuclei keep a minimal payload:
    #   octaves   : fBm layers (>1 = layered wrinkles, e.g. gyrified cortex)
    #   ridged    : fold the noise into sharp gyri/folia creases
    #   frequency : noise lattice frequency (higher = finer folds)
    #   aniso     : per-axis frequency skew (parallel folia)
    #   clip      : explicit flat cut planes (rarely set by hand)
    for key in ("octaves", "ridged", "frequency", "aniso", "clip"):
        if key in entry:
            blob[key] = entry[key]
    # `medial` lobes get a flat wall at the midline so the hemispheres lock
    # together along the longitudinal fissure. The shared shape is always built
    # for the right side (px >= 0), so the cut is an `xmin` plane expressed in
    # the blob's *local* space (it is centered at the structure position), hence
    # the `- px` shift. The left member reuses this same file mirrored across x
    # (see build_records), which flips the wall to the correct (xmax) side
    # automatically, so we never need to author the left clip separately.
    if entry.get("medial"):
        blob.setdefault("clip", {})["xmin"] = round(MIDLINE_GAP - px, 3)
    # Optional anatomical rescale for a blob: scale the ellipsoid half-extents
    # (and any flat clip offsets, which live in local space) per axis.
    if entry.get("scale") is not None:
        s = _scale_triple(entry["scale"])
        blob["radii"] = [round(blob["radii"][i] * s[i], 4) for i in range(3)]
        if "clip" in blob:
            axis = {"x": 0, "y": 1, "z": 2}
            blob["clip"] = {k: round(v * s[axis[k[0]]], 4)
                            for k, v in blob["clip"].items()}
    return blob


def _directional_extent(radii: tuple[float, float, float], noise: float,
                        direction: tuple[float, float, float]) -> float:
    """How far a noise-inflated ellipsoid reaches along a unit ``direction``.

    The support of an axis-aligned ellipsoid with half-extents ``radii`` in a unit
    direction ``n`` is ``sqrt(sum (r_i * n_i)^2)``; the surface noise can push a
    vertex out by up to ``noise`` of the radius, so the reach is scaled by
    ``(1 + noise)``. Used to decide whether two regions overlap and where to seat
    the seam between them.

    Parameters
    ----------
    radii
        Ellipsoid half-extents ``(rx, ry, rz)`` before deformation.
    noise
        Deformation amplitude as a fraction of radius.
    direction
        Unit vector along which to measure the reach.

    Returns
    -------
    float
        Maximum distance from the centre to the surface along ``direction``.
    """
    rx, ry, rz = radii
    dx, dy, dz = direction
    return math.sqrt((rx * dx) ** 2 + (ry * dy) ** 2 + (rz * dz) ** 2) * (1 + noise)


def _bisecting_clip_planes(entry: dict[str, Any],
                           neighbours: list[dict[str, Any]]
                           ) -> list[dict[str, Any]]:
    """Local-space cut planes keeping ``entry`` from crossing its neighbours.

    For each same-group blob ``neighbour`` whose body would overlap ``entry``'s,
    place a flat cut plane at the radius-weighted boundary between the two centres
    with its normal pointing toward the neighbour. ``buildBlobGeometry`` clamps
    any vertex past such a plane onto it, so the two regions grow flat mating
    faces and tile flush instead of interpenetrating (the "jigsaw" look that sells
    the regions locking together at explode 0 and separating as they explode).

    Adjacency is derived from the geometry, not hand-listed: a pair gets a plane
    only when the centres are closer than the two bodies' combined reach toward
    each other, so non-touching pairs (e.g. frontal vs occipital) are skipped. The
    seam is split in proportion to each body's reach, so a large lobe keeps more
    of the shared volume than a small neighbour, and because the pair overlaps the
    seam always lies inside the overlap zone (never cutting past either surface,
    so no region is reduced to a sliver).

    Planes are authored in ``entry``'s *local* frame (its geometry is centred at
    the origin and positioned later), exactly like the medial wall. Paired entries
    are defined on the right hemisphere and the left member mirrors the whole
    geometry across x, which flips these planes to the correct side for free, so
    they are computed once from the right-side positions.

    Parameters
    ----------
    entry
        The blob whose planes are computed (must carry ``radii``/``noise``).
    neighbours
        Same-group blob entries to test for overlap (``entry`` itself is skipped).

    Returns
    -------
    list of dict
        ``{"point": [x, y, z], "normal": [x, y, z]}`` planes in local coords; the
        normal is a unit vector pointing toward the neighbour (the removed side).
    """
    planes: list[dict[str, Any]] = []
    cx, cy, cz = entry["pos"]
    for other in neighbours:
        if other is entry:
            continue
        ox, oy, oz = other["pos"]
        dx, dy, dz = ox - cx, oy - cy, oz - cz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-6:
            continue
        n = (dx / dist, dy / dist, dz / dist)
        reach_self = _directional_extent(entry["radii"], entry["noise"], n)
        reach_other = _directional_extent(
            other["radii"], other["noise"], (-n[0], -n[1], -n[2]))
        # No overlap along this axis: the surfaces never meet, nothing to cut.
        if dist >= reach_self + reach_other:
            continue
        # Seam distance from this centre toward the neighbour, split in proportion
        # to each body's reach. Since dist < reach_self + reach_other, this stays
        # < reach_self (and the complement < reach_other), so the cut sits inside
        # the overlap and never reaches past either surface.
        seam = dist * reach_self / (reach_self + reach_other)
        planes.append({
            "point": [round(n[0] * seam, 3), round(n[1] * seam, 3),
                      round(n[2] * seam, 3)],
            "normal": [round(n[0], 3), round(n[1], 3), round(n[2], 3)],
        })
    return planes


def _mirror_id(structure_id: str) -> str:
    """Flip a structure id to the other hemisphere (``_R`` <-> ``_L``).

    Midline ids (no hemisphere suffix) are returned unchanged, so a projection
    that touches a midline structure mirrors only its lateralized endpoint.
    """
    if structure_id.endswith("_R"):
        return structure_id[:-2] + "_L"
    if structure_id.endswith("_L"):
        return structure_id[:-2] + "_R"
    return structure_id


def _expand_sources(keys: list[Any], what: str = "projection") -> list[dict[str, Any]]:
    """Validate a projection/circuit/group ``sources`` list (quote-level dicts only).

    Every source is an inline ``{corpus, page, quote, provenance}`` dict against a
    :data:`SOURCE_CORPORA` corpus, the *same* shape a drug binding uses, validated by
    :func:`_quote_sources` (a ``verified`` grade needs a page + quote, which
    ``check_data.py`` confirms is really on that page). This is how a pathway earns a
    ``verified`` grade, e.g. a Kandel quote from :data:`PROJECTION_QUOTES`.

    Fabricated bibliographic citations are no longer carried: a pathway/circuit/group
    with no quote source is left ungraded (its provenance pill reads NOSOURCE), rather
    than cite an unverifiable paper an LLM produced from memory.
    """
    return _quote_sources(list(keys), what)


def _projection_records(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one projection definition into its JSONL record(s).

    Projections are bilateral by default: each is emitted as given and, unless
    it sets ``"symmetric": False``, also as a hemisphere-flipped twin (``_R`` <->
    ``_L`` on both endpoints). The twin is skipped when flipping changes nothing
    (e.g. a purely midline pathway) so no duplicate is produced. ``symmetric`` is
    a generator hint and is stripped from the emitted records.

    The ``sources`` key (a list of quote-level ``{corpus, page, quote, provenance}``
    dicts) is validated in place, and the metadata (``neurotransmitter``,
    ``label``, ``description``, ``bidirectional``, ...) is carried onto the
    mirrored twin unchanged so both hemispheres show the same details. The
    translatable display fields (``label``, ``description``, ``neurotransmitter``)
    are wrapped bilingually with :func:`_t` so the data file is self-describing in
    both languages.
    """
    symmetric = proj.get("symmetric", True)
    fields = {k: v for k, v in proj.items() if k != "symmetric"}
    # Merge this pathway's verified Kandel quote-source (keyed by the right-side
    # endpoints in PROJECTION_QUOTES) into its source list, so it is expanded + carried
    # onto the mirrored twin like any other source.
    src_keys = list(fields.get("sources", []))
    kandel_quote = PROJECTION_QUOTES.get((fields["from"], fields["to"]))
    if kandel_quote is not None:
        src_keys.append(kandel_quote)
    if src_keys:
        fields["sources"] = _expand_sources(
            src_keys, f"projection {fields.get('from')}->{fields.get('to')}")
    for key in ("label", "description", "neurotransmitter"):
        if key in fields:
            fields[key] = _t(fields[key])
    records = [fields]
    if symmetric:
        mirrored = {**fields,
                    "from": _mirror_id(fields["from"]),
                    "to": _mirror_id(fields["to"])}
        if (mirrored["from"], mirrored["to"]) != (fields["from"], fields["to"]):
            records.append(mirrored)
    return records


def _receptor_record(rec: dict[str, Any],
                     known_bases: set[str]) -> dict[str, Any]:
    """Build one ``receptor`` JSONL record from a :data:`RECEPTORS` entry.

    Validates the ``family`` / ``receptor_class`` / ``sign`` / ``synaptic`` keys
    against the presentation maps and every ``locations`` base against the known
    structure bases (so a typo fails the build). The translatable
    ``neurotransmitter`` is wrapped bilingually via :func:`_t`; ``description`` is
    already authored as an English/French pair inline on the entry (unique per
    receptor, so it bypasses the shared FR table) and is copied to an
    ``{"en", "fr"}`` object. A ``locations`` of the sentinel ``"ALL"`` marks a
    brain-wide receptor: it is emitted with ``ubiquitous: true`` and an empty
    location list, which the viewer expands to every structure. An empty
    ``locations`` with no ``description`` is a deliberate stub (a receptor with no
    meaningful CNS role) and is emitted as-is, focusable by nothing.
    """
    for key, table, what in (
        ("family", RECEPTOR_FAMILY_LABELS, "RECEPTOR_FAMILY_LABELS"),
        ("receptor_class", RECEPTOR_CLASS_LABELS, "RECEPTOR_CLASS_LABELS"),
        ("sign", SIGN_LABELS, "SIGN_LABELS"),
        ("synaptic", SYNAPTIC_LABELS, "SYNAPTIC_LABELS"),
    ):
        if rec[key] not in table:
            raise KeyError(
                f"Receptor {rec['id']!r} has {key}={rec[key]!r} with no {what} "
                f"entry")
    out: dict[str, Any] = {
        "id": rec["id"],
        "name": rec["name"],
        "family": rec["family"],
        "neurotransmitter": _t(rec["neurotransmitter"]),
        "receptor_class": rec["receptor_class"],
        "sign": rec["sign"],
        "synaptic": rec["synaptic"],
    }
    # A receptor's classification is FOUR independent graded sub-claims (family /
    # receptor_class / sign / synaptic), NOT one: a single Stahl quote is attached
    # only to the attributes it actually substantiates (RECEPTOR_CLASSIFICATION_
    # COVERAGE), so e.g. a sign quote never lends its grade to the GPCR or
    # pre/postsynaptic claim. Each attribute defaults to the base grade (llm unless
    # RECEPTOR_PROVENANCE lifts it) and is upgraded only when a covering quote is
    # present. The panel renders one pill per attribute row from this dict.
    base_grade = _receptor_provenance(rec["id"])
    rq = STAHL_ESSENTIAL_RECEPTOR_QUOTES.get(rec["id"])
    covered = set(RECEPTOR_CLASSIFICATION_COVERAGE.get(rec["id"], ()))
    attr_quotes = RECEPTOR_ATTR_QUOTES.get(rec["id"], {})
    classification: dict[str, dict[str, Any]] = {}
    for attr in CLASSIFICATION_ATTRS:
        entry: dict[str, Any] = {"grade": base_grade}
        # A per-attribute override wins; else the main quote if COVERAGE lists this attr.
        srcs = attr_quotes.get(attr)
        if srcs is None and rq is not None and attr in covered:
            srcs = [rq]
        if srcs:
            entry["sources"] = [dict(s) for s in srcs]
            best = max((s["provenance"] for s in srcs), key=lambda p: _GRADE_RANK[p])
            if _GRADE_RANK[best] > _GRADE_RANK[entry["grade"]]:
                entry["grade"] = best
        classification[attr] = entry
    out["classification"] = classification
    locations = rec["locations"]
    if locations == "ALL":
        out["ubiquitous"] = True
        out["locations"] = []
    else:
        for base in locations:
            if base not in known_bases:
                raise KeyError(
                    f"Receptor {rec['id']!r} location {base!r} is not a known "
                    f"structure base")
        out["locations"] = list(locations)
        # Per-region expression sources (upgrade individual "Found in" regions above
        # the default llm). Omitted when nothing is sourced, so a plain receptor's
        # every region honestly grades as llm in the viewer + the coverage tally.
        loc_sources = _location_sources(
            RECEPTOR_LOCATION_SOURCES, rec["id"], out["locations"], "Receptor")
        if loc_sources:
            out["location_sources"] = loc_sources
    if "description" in rec:
        out["description"] = {"en": rec["description"], "fr": rec["description_fr"]}
    if "wikipedia" in rec:
        out["wikipedia"] = rec["wikipedia"]
        out["wikipedia_provenance"] = _wiki_provenance(rec["id"])
    return out


def _build_drug_targets(receptors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build the emitted ``drug_targets`` map: DRUG_TARGETS + every receptor.

    A drug binding may target either one of the non-receptor :data:`DRUG_TARGETS`
    (transporters, enzymes, channels, ...) or any receptor id from
    ``receptors.jsonl`` directly. This merges both into one self-describing map the
    viewer reads: each entry is ``{name {en,fr}, system, receptor, regions,
    ubiquitous?}``. For a receptor-linked target the ``receptor`` field carries the
    receptor id and ``regions`` mirror the receptor's locations (so the viewer can
    just reuse that receptor's already-resolved lit regions); for a non-receptor
    target ``receptor`` is null and ``regions`` are the DRUG_TARGETS footprint.

    Parameters
    ----------
    receptors
        The already-built receptor records (each with ``id``/``name``/``family``/
        ``locations`` and optional ``ubiquitous``).

    Returns
    -------
    dict
        target id -> target descriptor, ready to emit into ``meta.json``.
    """
    targets: dict[str, dict[str, Any]] = {}
    for tid, spec in DRUG_TARGETS.items():
        targets[tid] = {
            "name": spec["name"],
            "type": spec["type"],
            "system": spec["system"],
            "receptor": None,
            "regions": list(spec["regions"]),
            # Source grade backing this target's classification (its type / system /
            # region footprint), shown as the panel's "Source" pill and counted in
            # the coverage tally. "llm" by default; override in TARGET_PROVENANCE.
            "classification_provenance": _target_provenance(tid),
        }
        # Optional tone-polarity hints the viewer's flow overlay reads (js/data.js
        # toneSignOf): `vesicular` marks a vesicular transporter (inhibiting it
        # depletes -> lowers tone), and `sign`/`synaptic` give a receptor_group the
        # presynaptic-autoreceptor character a specific receptor carries on its own
        # record (the α2 family). Absent for a target with no tone effect.
        has_polarity = False
        for opt in ("vesicular", "sign", "synaptic"):
            if opt in spec:
                targets[tid][opt] = spec[opt]
                has_polarity = True
        # The tone-polarity flags above flip the flow-overlay direction, so the
        # claim "engaging this target raises/lowers tone" is its own graded node
        # (kind target_polarity), NOT an inheritance of the classification grade
        # from a quote that never spoke to direction. Emitted only when the target
        # actually carries a polarity flag. Default llm; a TARGET_POLARITY_QUOTES
        # quote (checked against the specific direction claim) upgrades it.
        if has_polarity:
            pol_grade = _target_polarity_provenance(tid)
            pq = TARGET_POLARITY_QUOTES.get(tid)
            if pq is not None:
                targets[tid]["polarity_sources"] = [dict(pq)]
                if _GRADE_RANK[pq["provenance"]] > _GRADE_RANK[pol_grade]:
                    pol_grade = pq["provenance"]
            targets[tid]["polarity_provenance"] = pol_grade
        # Per-region expression sources ("Found in"): each region is its own graded
        # node (kind target_locations), llm unless sourced here. Omitted when empty.
        tloc = _location_sources(
            TARGET_LOCATION_SOURCES, tid, spec["regions"], "Target")
        if tloc:
            targets[tid]["location_sources"] = tloc
        if spec.get("wikipedia"):
            targets[tid]["wikipedia"] = spec["wikipedia"]
            targets[tid]["wikipedia_provenance"] = _wiki_provenance(tid)
        # Verified Stahl Essential quote-source for this target's classification.
        tq = STAHL_ESSENTIAL_TARGET_QUOTES.get(tid)
        if tq is not None:
            targets[tid]["sources"] = [dict(tq)]
            if _GRADE_RANK[tq["provenance"]] > _GRADE_RANK[
                    targets[tid]["classification_provenance"]]:
                targets[tid]["classification_provenance"] = tq["provenance"]
    for rec in receptors:
        # A receptor id is also a valid target; link it so the viewer reuses the
        # receptor's lit regions. Receptor ids and DRUG_TARGETS keys never collide
        # (the latter are transporters/enzymes/channels), but guard anyway.
        if rec["id"] in targets:
            raise KeyError(f"Drug target id {rec['id']!r} collides with a receptor")
        targets[rec["id"]] = {
            "name": {"en": rec["name"], "fr": rec["name"]},
            "type": "receptor",
            "system": rec["family"],
            "receptor": rec["id"],
            "regions": list(rec.get("locations", [])),
            "ubiquitous": bool(rec.get("ubiquitous")),
        }
    return targets


def _drug_record(drug: dict[str, Any], valid_targets: set[str],
                 known_bases: set[str],
                 molecule_ids: set[str]) -> dict[str, Any]:
    """Validate + normalize one authored drug into its ``drugs.jsonl`` record.

    The authored drug (from ``tools/drugs_data.jsonl``) is mostly passed through;
    this validates it against the drug vocabularies (categories / targets /
    actions / effect overrides). The drug's real provenance lives per-claim: each
    binding's quote ``sources`` + ``ki`` and the ``nbn_sources``, all against the
    Stahl corpus (:data:`SOURCE_CORPORA`); there is no drug-level citation node.
    Translatable free text (``description``, per-binding ``note``, ``nbn``) is
    authored inline as ``{en, fr}`` (or the literal ``"TODO"``), so it does not go
    through the shared FR table. A drug with no bindings at all is emitted
    ``focusable: false`` (listed but not clickable, like a receptor stub).

    Parameters
    ----------
    drug
        One authored drug dict: ``id``, ``name``, ``categories``, ``bindings``
        and optional ``nbn`` / ``description`` / ``wikipedia``.
    valid_targets
        The set of valid binding target ids (DRUG_TARGETS keys + receptor ids).
    known_bases
        Known structure base ids (unused targets validation is by id, kept for
        symmetry with the receptor builder).
    molecule_ids
        Drug ids that have a vendored structure SVG under
        ``public/data/molecules/`` (see :func:`_available_molecule_ids` /
        ``tools/fetch_molecules.py``); a match adds a ``structure_image`` path the
        viewer embeds, a non-match simply omits it.

    Returns
    -------
    dict
        Record ready to be JSON-serialized as one line of ``drugs.jsonl``.
    """
    for key in ("id", "name", "categories", "bindings"):
        if key not in drug:
            raise KeyError(f"Drug {drug.get('id', drug.get('name'))!r} missing "
                           f"required field {key!r}")
    for cat in drug["categories"]:
        if cat not in DRUG_CATEGORY_LABELS:
            raise KeyError(f"Drug {drug['id']!r} category {cat!r} has no "
                           f"DRUG_CATEGORY_LABELS entry")
    bindings: list[dict[str, Any]] = []
    for b in drug["bindings"]:
        if b["target"] not in valid_targets:
            raise KeyError(f"Drug {drug['id']!r} binding target {b['target']!r} "
                           f"is not a known target (DRUG_TARGETS key or receptor id)")
        # An `affinity_only` binding is PDSP-derived: we know the drug binds the
        # target (with a measured Ki) but not the functional direction (agonist vs
        # antagonist), so it carries no action/effect and is listed in the panel but
        # excluded from the 3D animation (see js/data.js). Every other binding must
        # name a known action.
        affinity_only = bool(b.get("affinity_only"))
        if affinity_only:
            out_b: dict[str, Any] = {"target": b["target"], "affinity_only": True}
        else:
            if b["action"] not in DRUG_ACTIONS:
                raise KeyError(f"Drug {drug['id']!r} binding action {b['action']!r} "
                               f"has no DRUG_ACTIONS entry")
            out_b = {"target": b["target"], "action": b["action"]}
            if "effect" in b:
                if b["effect"] not in DRUG_EFFECT_COLORS:
                    raise KeyError(f"Drug {drug['id']!r} binding effect "
                                   f"{b['effect']!r} has no DRUG_EFFECT_COLORS entry")
                out_b["effect"] = b["effect"]
        if b.get("note"):
            out_b["note"] = b["note"]
        if b.get("tentative"):
            out_b["tentative"] = True
        # Per-claim sources ({corpus, page, quote, provenance}); the verbatim quote
        # is what check_data.py confirms is present in the cited corpus page. See
        # _binding_sources / SOURCE_CORPORA.
        binding_sources = _binding_sources(drug["id"], b)
        if binding_sources:
            out_b["sources"] = binding_sources
        # PDSP measured binding affinity (its own verified source; see _ki_annotation).
        ki = _ki_annotation(drug["id"], b)
        if ki:
            out_b["ki"] = ki
        bindings.append(out_b)
    out: dict[str, Any] = {
        "id": drug["id"],
        "name": drug["name"],
        "categories": list(drug["categories"]),
        "bindings": bindings,
        "focusable": len(bindings) > 0,
    }
    # The drug's class classification ("this drug is an SSRI/...") is its own graded
    # node (kind drug_categories), one per drug: default llm, overridable in
    # DRUG_CATEGORY_PROVENANCE, and upgraded by any quote-level `category_sources`
    # authored on the drug (validated + quote-checked like a binding). The emitted
    # grade is the stronger of the override and the sources.
    cat_provenance = _lookup_provenance(
        DRUG_CATEGORY_PROVENANCE, drug["id"], f"drug class for {drug['id']!r}")
    cat_sources = _quote_sources(
        drug.get("category_sources"), f"Drug {drug['id']!r} category")
    if cat_sources:
        out["category_sources"] = cat_sources
        best = max(cat_sources, key=lambda s: _GRADE_RANK[s["provenance"]])
        if _GRADE_RANK[best["provenance"]] > _GRADE_RANK[cat_provenance]:
            cat_provenance = best["provenance"]
    out["category_provenance"] = cat_provenance
    if drug.get("nbn"):
        out["nbn"] = drug["nbn"]
        # Newer drugs Stahl has not assigned a formal Neuroscience-based
        # Nomenclature to carry `nbn_nonstandard`: their nomenclature value is
        # Stahl's drug-*class* descriptor (sourced from the "Class" line, not an
        # "Neuroscience-based Nomenclature:" line), so the viewer can flag it as
        # non-standard. Set programmatically by apply_nbn_sources.py's fallback.
        if drug.get("nbn_nonstandard"):
            out["nbn_nonstandard"] = True
        # The NbN is quote-sourced like a binding: Stahl prints a verbatim
        # "Neuroscience-based Nomenclature: ..." line on each drug's first page
        # (the Class line for a non-standard entry).
        nbn_sources = _quote_sources(drug.get("nbn_sources"), f"Drug {drug['id']!r} nbn")
        if nbn_sources:
            out["nbn_sources"] = nbn_sources
    # Drug descriptions are intentionally NOT baked: the panel fetches the current
    # Wikipedia lead at runtime (js/wiki.js), exactly like a structure/target, so the
    # text stays up to date and the dataset ships no copyrighted prose. A drug whose
    # live lead fails to load simply shows no description.
    if drug.get("wikipedia"):
        out["wikipedia"] = drug["wikipedia"]
        out["wikipedia_provenance"] = _wiki_provenance(drug["id"])
    if drug["id"] in molecule_ids:
        # Path from the site root (like a structure's shape_file); the viewer
        # embeds it as an <img>. Only set when the SVG was actually fetched, so a
        # drug without one renders no image (no broken-image placeholder).
        out["structure_image"] = f"data/molecules/{drug['id']}.svg"
    return out


def _available_molecule_ids() -> set[str]:
    """Drug ids that have a vendored structure SVG under ``public/data/molecules/``.

    Those files are produced by the authoring tool ``tools/fetch_molecules.py``
    (which hits the network); this offline generator only *checks for their
    presence*. The presence of ``<id>.svg`` is the single source of truth for
    whether a drug gets a ``structure_image`` (see :func:`_drug_record`), so the
    set of embedded molecules stays in lock-step with what was actually fetched.
    """
    mol_dir = Path(__file__).resolve().parent.parent / "public" / "data" / "molecules"
    if not mol_dir.exists():
        return set()
    return {p.stem for p in mol_dir.glob("*.svg")}


def _load_image_sources(filename: str) -> dict[str, dict[str, Any]]:
    """Map ``key -> image record`` from a ``tools/<filename>`` sources JSON.

    Unlike the drug molecule SVGs (vendored same-origin), the structure / circuit
    illustration GIFs are too large to commit, so the viewer **hot-links** them
    from Wikimedia at runtime (with a spinner / silent-fail, see ``showStructure`` /
    ``showCircuit``): only the URL is stored in the data, not the binary. The URLs are
    resolved author-side by ``tools/fetch_structure_images.py`` (which hits the
    network) and recorded in that small JSON; this offline generator just reads it, so
    an owner gets a ``structure_image`` (the lead hero) plus a
    ``structure_image_gallery`` (the other gif/svg from its EN+FR articles, for the
    panel's "show more") iff its key has an entry with a url. A missing file is fine
    (no images). Keyed by structure base id / circuit id respectively.
    """
    src = Path(__file__).resolve().parent / filename
    if not src.exists():
        return {}
    data = json.loads(src.read_text(encoding="utf-8"))
    return {key: rec for key, rec in data.items() if rec.get("url")}


def _load_structure_images() -> dict[str, dict[str, Any]]:
    """Structure image sources (see :func:`_load_image_sources`), keyed by base id."""
    return _load_image_sources("structure_images_sources.json")


def _load_circuit_images() -> dict[str, dict[str, Any]]:
    """Circuit image sources (see :func:`_load_image_sources`), keyed by circuit id."""
    return _load_image_sources("circuit_images_sources.json")


def _load_drugs() -> list[dict[str, Any]]:
    """Read the authored drug list from ``tools/drugs_data.jsonl`` (if present).

    The drug data is kept in a sibling JSONL file rather than inline in this
    module because it is large and comes from extraction (Stahl's Prescriber's
    Guide); keeping it separate keeps this generator readable. A missing file is
    not an error (the drugs feature is simply empty), so the generator still runs
    on a checkout without it.
    """
    import drugs_io
    if not drugs_io.DRUGS_PATH.exists():
        log.warning("no %s; drugs.jsonl will be empty", drugs_io.DRUGS_PATH.name)
        return []
    return drugs_io.load_drugs()


# Provenance ranks for the dataset-wide sourcing tally (meta.provenance_stats):
# a higher rank is a stronger grade, 0 = no source/grade at all. Mirrors
# PROVENANCE_LEVELS but as an order so a list of sources can be reduced to its best.
_GRADE_RANK = {"llm": 1, "sourced": 2, "verified": 3}


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


def _provenance_stats(structures: list[dict[str, Any]],
                      projections: list[dict[str, Any]],
                      circuits: list[dict[str, Any]],
                      projection_groups: list[dict[str, Any]],
                      receptors: list[dict[str, Any]],
                      drugs: list[dict[str, Any]],
                      drug_targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
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
        rank = (rank_or_grade if isinstance(rank_or_grade, int)
                else _GRADE_RANK.get(rank_or_grade, 0))
        # rank <= 1 (no source object, or a bare ``llm`` grade) => no document => missing.
        return ("verified" if rank == 3 else
                "sourced" if rank == 2 else "missing")

    def tally(grades: list[Any]) -> dict[str, int]:
        counts = {"total": 0, "verified": 0, "sourced": 0, "missing": 0}
        for g in grades:
            counts["total"] += 1
            counts[bucket(g)] += 1
        return counts

    binding_grades = [_binding_grade(b)
                      for d in drugs for b in d.get("bindings", [])]
    nbn_grades = [_strongest_grade(d.get("nbn_sources"))
                  for d in drugs if d.get("nbn")]
    # Drug class-classification nodes ("this drug is an SSRI/..."), one per drug that
    # has categories: the emitted category_provenance (llm unless overridden/sourced).
    category_grades = [d.get("category_provenance", DEFAULT_PROVENANCE)
                       for d in drugs if d.get("categories")]
    projection_grades = [_strongest_grade(p.get("sources")) for p in projections]
    # Functional-circuit + projection-group nodes: each a "these structures / pathways
    # form a system" claim, graded by its own sources (rank 0 => missing when unsourced,
    # matching the viewer's NOSOURCE pill). All missing today (no circuit/group is
    # document-backed yet).
    circuit_grades = [_strongest_grade(c.get("sources")) for c in circuits]
    projection_group_grades = [_strongest_grade(g.get("sources"))
                               for g in projection_groups]
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

    def _attr_grade(r: dict[str, Any], attr: str) -> str:
        entry = (r.get("classification") or {}).get(attr)
        return entry["grade"] if entry else DEFAULT_PROVENANCE
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

    def location_grades(owner: dict[str, Any], regions_key: str) -> list[int]:
        loc_sources = owner.get("location_sources", {})
        if owner.get("ubiquitous"):
            return [max(_strongest_grade(loc_sources.get("ALL")), _llm_rank)]
        return [max(_strongest_grade(loc_sources.get(base)), _llm_rank)
                for base in owner.get(regions_key, [])]

    receptor_location_grades = [g for r in receptors
                                for g in location_grades(r, "locations")]
    # Non-receptor drug target classifications (type / system), graded per target.
    # Receptor-linked targets are skipped (already counted as receptors, not twice).
    target_grades = [t.get("classification_provenance", DEFAULT_PROVENANCE)
                     for t in drug_targets.values() if t.get("type") != "receptor"]
    # Target expression-region nodes: the mirror of receptor_locations (a target never
    # sets ubiquitous, so only the per-region branch runs; receptor-linked targets are
    # skipped, their regions counted as the receptor's).
    target_location_grades = [g for t in drug_targets.values()
                              if t.get("type") != "receptor"
                              for g in location_grades(t, "regions")]
    # Target tone-polarity sub-claims: one graded node per non-receptor target that
    # carries a direction-flipping flag (vesicular / sign / synaptic). Kept distinct
    # from the target's type/system classification so a wrong direction shows honestly.
    target_polarity_grades = [t["polarity_provenance"]
                              for t in drug_targets.values()
                              if t.get("type") != "receptor"
                              and "polarity_provenance" in t]
    # Brain-region anatomy (existence / group / position), graded per emitted
    # structure record (both hemispheres of a pair count, one line each).
    structure_grades = [s.get("classification_provenance", DEFAULT_PROVENANCE)
                        for s in structures]
    # Wikipedia reference links across every owner kind. Non-receptor targets only
    # (a receptor is already counted via the receptor records, not twice); a missing
    # link is a rank-0 "missing" so the gap shows in the coverage.
    ref_grades: list[int] = []
    for rec in (*structures, *receptors, *drugs):
        ref_grades.append(_GRADE_RANK.get(rec.get("wikipedia_provenance"), 0)
                          if rec.get("wikipedia") else 0)
    for tgt in drug_targets.values():
        if tgt.get("type") == "receptor":
            continue
        ref_grades.append(_GRADE_RANK.get(tgt.get("wikipedia_provenance"), 0)
                          if tgt.get("wikipedia") else 0)

    by_kind = {
        "drug_bindings": tally(binding_grades),
        "drug_nbn": tally(nbn_grades),
        "drug_categories": tally(category_grades),
        "projections": tally(projection_grades),
        "circuits": tally(circuit_grades),
        "projection_groups": tally(projection_group_grades),
        "receptors": tally(receptor_family_grades),
        "receptor_class": tally(receptor_class_grades),
        "receptor_sign": tally(receptor_sign_grades),
        "receptor_synaptic": tally(receptor_synaptic_grades),
        "receptor_locations": tally(receptor_location_grades),
        "targets": tally(target_grades),
        "target_polarity": tally(target_polarity_grades),
        "target_locations": tally(target_location_grades),
        "structures": tally(structure_grades),
        "references": tally(ref_grades),
    }
    # The knowledge-node kinds (every node that carries a claim + a grade) are every
    # by_kind entry except "references" (a reference points *at* a node, so it is
    # tallied but excluded from the headline). Derived from the one by_kind dict above,
    # so adding a node kind is a single-line edit (add it to by_kind) with no second
    # list to keep in sync.
    node_kinds = tuple(k for k in by_kind if k != "references")
    nodes = {"total": 0, "verified": 0, "sourced": 0, "missing": 0}
    for kind in node_kinds:
        for key in nodes:
            nodes[key] += by_kind[kind][key]
    backed = nodes["verified"] + nodes["sourced"]
    nodes["backed"] = backed
    nodes["pct_backed"] = (
        round(100 * backed / nodes["total"]) if nodes["total"] else 0)
    return {"by_kind": by_kind, "nodes": nodes}


def build_records() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Expand the anatomy definition into the per-type record sets + shapes.

    Paired entries are emitted twice (``_R`` and ``_L``) but share a *single*
    right-side shape file: the left member references the same file and is
    reflected across x at load time (``mirror``), so the two hemispheres are
    true mirror images rather than copies, and there is exactly one geometry
    file per distinct form (no duplication). Midline entries are emitted once.

    Returns
    -------
    data
        ``{"meta": <dict>, "structures": [...], "projections": [...],
        "circuits": [...]}`` -- one entry per output file (``meta.json`` plus the
        three ``*.jsonl``). Records carry **no** ``type`` field: the file a record
        lives in encodes its type, so it is not duplicated onto every line.
    shapes
        Mapping of shape-file basename -> shape payload dict.
    """
    structures: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    circuits: list[dict[str, Any]] = []
    projection_groups: list[dict[str, Any]] = []
    receptors: list[dict[str, Any]] = []
    drugs: list[dict[str, Any]] = []
    shapes: dict[str, dict[str, Any]] = {}

    # Same-group blob neighbours for the inter-region jigsaw clipping. Only
    # default blobs take part: curve/composite forms have no clip support and the
    # C-shaped caudate / cerebellum sit apart anyway. Pairs are kept within a
    # group so the small deep nuclei still nest inside the cortex; within a group,
    # overlap is detected per pair.
    blob_groups: dict[str, list[dict[str, Any]]] = {}
    for entry in PAIRED:
        if "shape" not in entry:
            blob_groups.setdefault(entry["group"], []).append(entry)

    # Wikimedia image records resolved author-side (offline read of the sources
    # JSON); a structure whose base has one gets a hot-linked structure_image (the
    # hero) + structure_image_gallery (the GIFs are too large to vendor, unlike the
    # drug molecule SVGs). Circuits get the same, keyed by circuit id.
    structure_images = _load_structure_images()
    circuit_images = _load_circuit_images()

    for entry in PAIRED:
        x, y, z = entry["pos"]
        base = entry["base"]
        # One shared shape file, built for the RIGHT side. Because the left
        # member is reflected across x (mirror=True), building from the right
        # side also flips the medial clip plane to the correct side for free.
        shape = _shape_record(entry, x)
        if "shape" not in entry:
            planes = _bisecting_clip_planes(entry, blob_groups[entry["group"]])
            if planes:
                shape["clip_planes"] = planes
        shapes[base] = shape
        # Bilingual base name (e.g. {"en": "Putamen", "fr": "Putamen"}); the
        # per-hemisphere display names are composed from it (English prefix,
        # French gender/number-agreed suffix). ``fr_gender`` tunes the agreement.
        base_name = _t(entry["name"])
        gender = entry.get("fr_gender", "m")
        structures.append(
            _structure_record(entry, f"{base}_R", _side_name(base_name, gender, "R"),
                              base_name, (x, y, z), base,
                              images=structure_images))
        structures.append(
            _structure_record(entry, f"{base}_L", _side_name(base_name, gender, "L"),
                              base_name, (-x, y, z), base, mirror=True,
                              images=structure_images))

    for entry in MIDLINE:
        sid = entry["base"]
        # Midline structures have no hemisphere, so the full name is the base.
        name = _t(entry["name"])
        structures.append(
            _structure_record(entry, sid, name, name, entry["pos"], sid,
                              images=structure_images))
        shapes[sid] = _shape_record(entry, entry["pos"][0])

    for proj in PROJECTIONS:
        projections.extend(_projection_records(proj))
    # Typo guard: every PROJECTION_QUOTES key must address a real PROJECTIONS entry,
    # else its quote silently sources nothing.
    unmatched = set(PROJECTION_QUOTES) - {(p["from"], p["to"]) for p in PROJECTIONS}
    if unmatched:
        raise KeyError(
            f"PROJECTION_QUOTES keys match no PROJECTIONS entry: {sorted(unmatched)}")
    unmatched_bases = set(STRUCTURE_QUOTES) - {
        e["base"] for e in (*PAIRED, *MIDLINE)}
    if unmatched_bases:
        raise KeyError(
            f"STRUCTURE_QUOTES keys are not structure bases: "
            f"{sorted(unmatched_bases)}")
    unmatched_rq = set(STAHL_ESSENTIAL_RECEPTOR_QUOTES) - {r["id"] for r in RECEPTORS}
    if unmatched_rq:
        raise KeyError(
            f"STAHL_ESSENTIAL_RECEPTOR_QUOTES keys are not receptor ids: "
            f"{sorted(unmatched_rq)}")
    # Every quoted receptor needs a coverage entry (else its quote would grade
    # nothing) and vice-versa (a coverage entry with no quote grades nothing), and
    # each covered attribute must be a real classification attribute. This keeps the
    # per-attribute grading honest: a quote can only lift the attributes it names.
    cov_no_quote = set(RECEPTOR_CLASSIFICATION_COVERAGE) - set(STAHL_ESSENTIAL_RECEPTOR_QUOTES)
    quote_no_cov = set(STAHL_ESSENTIAL_RECEPTOR_QUOTES) - set(RECEPTOR_CLASSIFICATION_COVERAGE)
    if cov_no_quote or quote_no_cov:
        raise KeyError(
            "RECEPTOR_CLASSIFICATION_COVERAGE must match the receptor-quote keys "
            f"(coverage without quote: {sorted(cov_no_quote)}; quote without "
            f"coverage: {sorted(quote_no_cov)})")
    bad_attrs = {a for attrs in RECEPTOR_CLASSIFICATION_COVERAGE.values()
                 for a in attrs if a not in CLASSIFICATION_ATTRS}
    if bad_attrs:
        raise KeyError(
            f"RECEPTOR_CLASSIFICATION_COVERAGE has unknown attributes: "
            f"{sorted(bad_attrs)} (valid: {CLASSIFICATION_ATTRS})")
    # Per-attribute quote overrides must key real receptors and real attributes.
    aq_no_receptor = set(RECEPTOR_ATTR_QUOTES) - {r["id"] for r in RECEPTORS}
    if aq_no_receptor:
        raise KeyError(
            f"RECEPTOR_ATTR_QUOTES keys are not receptor ids: {sorted(aq_no_receptor)}")
    bad_aq_attrs = {a for m in RECEPTOR_ATTR_QUOTES.values()
                    for a in m if a not in CLASSIFICATION_ATTRS}
    if bad_aq_attrs:
        raise KeyError(
            f"RECEPTOR_ATTR_QUOTES has unknown attributes: {sorted(bad_aq_attrs)} "
            f"(valid: {CLASSIFICATION_ATTRS})")
    unmatched_tq = set(STAHL_ESSENTIAL_TARGET_QUOTES) - set(DRUG_TARGETS)
    if unmatched_tq:
        raise KeyError(
            f"STAHL_ESSENTIAL_TARGET_QUOTES keys are not DRUG_TARGETS ids: "
            f"{sorted(unmatched_tq)}")
    # A polarity quote must key a target that actually carries a polarity flag,
    # else it grades a direction claim that is never emitted.
    _polarity_ids = {tid for tid, spec in DRUG_TARGETS.items()
                     if any(f in spec for f in ("vesicular", "sign", "synaptic"))}
    unmatched_pq = set(TARGET_POLARITY_QUOTES) - _polarity_ids
    if unmatched_pq:
        raise KeyError(
            f"TARGET_POLARITY_QUOTES keys have no polarity flag in DRUG_TARGETS: "
            f"{sorted(unmatched_pq)}")
    unmatched_pp = set(TARGET_POLARITY_PROVENANCE) - _polarity_ids
    if unmatched_pp:
        raise KeyError(
            f"TARGET_POLARITY_PROVENANCE keys have no polarity flag in "
            f"DRUG_TARGETS: {sorted(unmatched_pp)}")

    # Circuits: expand each base structure id to whatever was emitted (both
    # hemispheres for a paired form, the bare id for a midline one). Built from
    # the structure records already collected, so it can't reference a structure
    # that doesn't exist.
    structure_ids = {r["id"] for r in structures}
    for circuit in CIRCUITS:
        ids: list[str] = []
        for base in circuit["structures"]:
            members = [sid for sid in (base, f"{base}_R", f"{base}_L")
                       if sid in structure_ids]
            if not members:
                raise KeyError(
                    f"Circuit {circuit['id']!r} references unknown structure "
                    f"{base!r} (no {base}, {base}_R or {base}_L emitted).")
            ids.extend(members)
        record = {
            "id": circuit["id"],
            "name": _t(circuit["name"]),
            "structures": ids,
        }
        if circuit.get("description"):
            record["description"] = {"en": circuit["description"],
                                     "fr": circuit["description_fr"]}
        if circuit.get("sources"):
            record["sources"] = _expand_sources(
                circuit["sources"], f"circuit {circuit['id']!r}")
        # Optional Wikipedia reference (+ its own grade), so the circuit panel shows
        # a "read more" link and live-fetches the current lead as a sourced
        # description, exactly like a structure/target. A present link defaults to
        # WIKIPEDIA_DEFAULT_PROVENANCE (sourced); override in WIKIPEDIA_PROVENANCE.
        if circuit.get("wikipedia"):
            record["wikipedia"] = circuit["wikipedia"]
            record["wikipedia_provenance"] = _wiki_provenance(circuit["id"])
        # Hot-linked Wikipedia illustration (hero + gallery), keyed by circuit id, the
        # same treatment a structure gets (see _load_circuit_images). Only set when the
        # circuit was resolved, so an unillustrated one renders no image.
        cimg = circuit_images.get(circuit["id"])
        if cimg and cimg.get("url"):
            record["structure_image"] = cimg["url"]
            cgallery = [g["url"] for g in cimg.get("gallery", []) if g.get("url")]
            if cgallery:
                record["structure_image_gallery"] = cgallery
        circuits.append(record)

    # Projection groups: the legend's per-pathway rows as a sourced data structure
    # (see PROJECTION_GROUPS). One record per group, in BOTH colour modes; the
    # member pathways are derived in the viewer (the projections whose kind / sign
    # matches), so a group never duplicates the projection list. ``key`` is
    # validated against the kind / sign vocabularies (typo guard).
    seen_group_ids: set[str] = set()
    for group in PROJECTION_GROUPS:
        mode, key = group["mode"], group["key"]
        if mode == "kind":
            if key not in PROJECTION_COLORS:
                raise KeyError(
                    f"Projection group references unknown kind {key!r}")
        elif mode == "sign":
            if key not in SIGN_LABELS:
                raise KeyError(
                    f"Projection group references unknown sign {key!r}")
        else:
            raise KeyError(f"Projection group {key!r} has unknown mode {mode!r}")
        gid = f"{mode}_{key}"
        if gid in seen_group_ids:
            raise KeyError(f"Duplicate projection-group id {gid!r}")
        seen_group_ids.add(gid)
        record = {
            "id": gid,
            "mode": mode,
            "key": key,
            "name": _t(group["name"]),
            "description": {"en": group["description"],
                            "fr": group["description_fr"]},
            "classification_provenance": _provenance(
                group.get("classification_provenance", DEFAULT_PROVENANCE),
                f"projection group {gid!r}"),
        }
        if group.get("wikipedia"):
            record["wikipedia"] = group["wikipedia"]
            record["wikipedia_provenance"] = _lookup_provenance(
                WIKIPEDIA_PROVENANCE, gid, f"wikipedia reference for {gid!r}",
                default=WIKIPEDIA_DEFAULT_PROVENANCE)
        if group.get("sources"):
            record["sources"] = _expand_sources(
                group["sources"], f"projection group {gid!r}")
        projection_groups.append(record)

    # Receptors: validate + normalize each against the known structure bases
    # (locations reference bases like circuits do; the viewer expands them to
    # both hemispheres). Duplicate ids fail the build.
    receptor_bases = {e["base"] for e in PAIRED} | {e["base"] for e in MIDLINE}
    seen_receptor_ids: set[str] = set()
    for rec in RECEPTORS:
        if rec["id"] in seen_receptor_ids:
            raise KeyError(f"Duplicate receptor id {rec['id']!r}")
        seen_receptor_ids.add(rec["id"])
        receptors.append(_receptor_record(rec, receptor_bases))

    # Drugs: authored in tools/drugs_data.jsonl, validated against the drug
    # vocabularies + the merged target map (DRUG_TARGETS + receptor ids). Every
    # DRUG_TARGETS region must be a known structure base (typo guard), like a
    # receptor location. Duplicate drug ids fail the build.
    for tid, spec in DRUG_TARGETS.items():
        if spec["type"] not in TARGET_TYPE_LABELS or spec["type"] == "receptor":
            raise KeyError(
                f"DRUG_TARGETS[{tid!r}] type {spec['type']!r} is not a "
                f"non-receptor TARGET_TYPE_LABELS key")
        wiki = spec.get("wikipedia")
        if wiki is not None and not str(wiki).startswith(("http://", "https://")):
            raise ValueError(
                f"DRUG_TARGETS[{tid!r}] wikipedia must be an http(s) URL or absent")
        for base in spec["regions"]:
            if base not in receptor_bases:
                raise KeyError(
                    f"DRUG_TARGETS[{tid!r}] region {base!r} is not a known "
                    f"structure base")
    drug_targets = _build_drug_targets(receptors)
    valid_targets = set(drug_targets.keys())
    molecule_ids = _available_molecule_ids()
    seen_drug_ids: set[str] = set()
    for drug in _load_drugs():
        if drug["id"] in seen_drug_ids:
            raise KeyError(f"Duplicate drug id {drug['id']!r}")
        seen_drug_ids.add(drug["id"])
        drugs.append(
            _drug_record(drug, valid_targets, receptor_bases, molecule_ids))

    # Fail loudly if the data uses a kind or group with no entry in the maps above.
    kinds = {r["kind"] for r in projections}
    missing_kinds = kinds - PROJECTION_COLORS.keys()
    if missing_kinds:
        raise KeyError(
            f"Projection kind(s) with no PROJECTION_COLORS entry: "
            f"{sorted(missing_kinds)}")
    groups = {r["group"] for r in structures}
    missing_groups = groups - GROUP_LABELS.keys()
    if missing_groups:
        raise KeyError(
            f"Structure group(s) with no GROUP_LABELS entry: "
            f"{sorted(missing_groups)}")
    known_bases = {e["base"] for e in PAIRED} | {e["base"] for e in MIDLINE}
    unknown_wiki = WIKIPEDIA.keys() - known_bases
    if unknown_wiki:
        raise KeyError(
            f"WIKIPEDIA entry for unknown structure base(s): "
            f"{sorted(unknown_wiki)}")
    # Every translatable string went through _t(); fail loudly (listing them all)
    # if any had no FR entry, so the data can't ship half-translated.
    if _MISSING_TRANSLATIONS:
        raise KeyError(
            "Missing FR translation for: "
            + "; ".join(repr(s) for s in sorted(_MISSING_TRANSLATIONS)))

    # Presentation metadata (its own meta.json) so a consumer reading the dataset
    # is self-contained: arrow colours + legend headings live in the data, not
    # only in the viewer's JS.
    meta = {
        # Both presentation maps are emitted bilingually: the kind->arrow colour
        # map is language-neutral, but kind_labels/group_labels carry {en, fr}
        # display strings the viewer resolves via window.__I18N__.pick.
        "projection_colors": PROJECTION_COLORS,
        "kind_labels": {kind: _t(kind) for kind in PROJECTION_COLORS},
        "group_labels": {g: _t(label) for g, label in GROUP_LABELS.items()},
        # Sign (excitatory / inhibitory) colour mode: kind->sign fold, sign->colour
        # swatch (language-neutral) and sign->{en,fr} legend heading. The viewer's
        # colour toggle reads these so neither palette nor labels are hardcoded.
        "kind_signs": KIND_TO_SIGN,
        "sign_colors": SIGN_COLORS,
        "sign_labels": {sign: _t(label) for sign, label in SIGN_LABELS.items()},
        # Drug target system -> projection kind, for the per-drug flow overlay (see
        # SYSTEM_FLOW_KINDS). Language-neutral keys both sides.
        "system_flow_kinds": SYSTEM_FLOW_KINDS,
        # Receptor legend maps: family -> heading, mechanism class -> label, and
        # pre/post-synaptic -> label (all bilingual). The per-receptor sign reuses
        # sign_colors / sign_labels above, so the receptor legend needs no extra
        # colour map. Object key order is the legend's family display order.
        "receptor_family_labels": {
            f: _t(label) for f, label in RECEPTOR_FAMILY_LABELS.items()},
        "receptor_class_labels": {
            c: _t(label) for c, label in RECEPTOR_CLASS_LABELS.items()},
        "synaptic_labels": {
            s: _t(label) for s, label in SYNAPTIC_LABELS.items()},
        # Drug legend + animation maps (already bilingual; see the drug schema
        # block near the top). drug_targets merges DRUG_TARGETS with every
        # receptor id so a binding can target either.
        "drug_category_labels": DRUG_CATEGORY_LABELS,
        # Merged binding-target map (DRUG_TARGETS + every receptor id), plus the
        # non-receptor target type -> {en,fr} tag and type -> swatch colour the
        # merged "Receptors & targets" legend reads (receptors keep their sign
        # swatch, so target_type_colors omits "receptor").
        "drug_targets": drug_targets,
        "target_type_labels": {
            ty: _t(label) for ty, label in TARGET_TYPE_LABELS.items()},
        "target_type_colors": TARGET_TYPE_COLORS,
        "drug_actions": DRUG_ACTIONS,
        "drug_effect_colors": DRUG_EFFECT_COLORS,
        "drug_effect_labels": DRUG_EFFECT_LABELS,
        # Source corpora the per-binding (and later per-field) drug sources cite,
        # keyed by id (see SOURCE_CORPORA). The viewer reads citation/url to render
        # each binding's source; check_data.py reads pages_dir to confirm quotes.
        # Self-describing so a port needs no hardcoded citation.
        "source_corpora": SOURCE_CORPORA,
        # Programmatic sourcing tally over the shipped data (per-kind + headline);
        # the About panel + README read it so the "% sourced" figure is a real
        # count, never hand-typed. See _provenance_stats.
        "provenance_stats": _provenance_stats(
            structures, projections, circuits, projection_groups,
            receptors, drugs, drug_targets),
    }

    return ({"meta": meta, "structures": structures,
             "projections": projections, "circuits": circuits,
             "projection_groups": projection_groups,
             "receptors": receptors, "drugs": drugs}, shapes)


def write_artifacts(root: Path) -> None:
    """Write the dataset under ``root`` (``data/`` + ``data/shapes/``).

    The dataset is split by record type for clarity: ``data/meta.json`` (a single
    object) plus one ``*.jsonl`` per collection (``structures``, ``projections``,
    ``circuits``); the file a record lives in encodes its type. The
    ``data/shapes`` directory is cleared of stale ``*.json`` first so removing a
    structure here also removes its orphaned shape file.
    """
    data, shapes = build_records()

    data_dir = root / "data"
    shapes_dir = data_dir / "shapes"
    data_dir.mkdir(parents=True, exist_ok=True)
    shapes_dir.mkdir(parents=True, exist_ok=True)

    for stale in shapes_dir.glob("*.json"):
        stale.unlink()

    # Externalize every bilingual {en,fr} dict to its English string at write time,
    # collecting the en->fr pairs into a single deduplicated side table
    # (translations.fr.json). The emitted data is English-only; French is recovered
    # by the viewer from the side table (see externalize() + js/i18n.js). Reset the
    # accumulator first so a second run in the same process starts clean.
    reset_translations()

    # meta is a single object -> pretty-printed meta.json; the collections are one
    # JSON object per line -> one *.jsonl each.
    meta_path = data_dir / "meta.json"
    meta_path.write_text(
        json.dumps(externalize(data["meta"]), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    log.info("wrote %s", meta_path)

    for name in ("structures", "projections", "circuits", "projection_groups",
                 "receptors", "drugs"):
        path = data_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for record in data[name]:
                fh.write(json.dumps(externalize(record), ensure_ascii=False) + "\n")
        log.info("wrote %s (%d lines)", path, len(data[name]))

    # The deduplicated French side table, keys sorted for stable diffs. Fetched by
    # the viewer only when the active language is French (see js/data.js).
    tr_path = data_dir / "translations.fr.json"
    tr_path.write_text(
        json.dumps(TRANSLATIONS, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    log.info("wrote %s (%d pairs)", tr_path, len(TRANSLATIONS))

    for sid, payload in shapes.items():
        path = shapes_dir / f"{sid}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log.info("wrote %d shape files to %s/", len(shapes), shapes_dir)


def main() -> None:
    """CLI entry point: parse ``--root`` and regenerate the artifacts."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        # This script lives in tools/; the data/ tree it generates (meta.json +
        # the *.jsonl + shapes/) is *served*, so it belongs under the public/ site root.
        default=Path(__file__).resolve().parent.parent / "public",
        help="Site root to write data/ (meta.json + *.jsonl + shapes/) into (default: ../public).",
    )
    args = parser.parse_args()
    write_artifacts(args.root)


if __name__ == "__main__":
    main()
