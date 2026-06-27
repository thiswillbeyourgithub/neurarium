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
# Drug presentation maps + binding vocabularies (emitted into meta.json).
#
# Drugs (the psychoactive medications authored in ``tools/drugs_data.json``, see
# "Changing the data") are sourced from Stahl's Prescriber's Guide, 8th ed. Each
# drug has one or more coarse ``categories`` (SSRI, tricyclic, ...) and a list of
# ``bindings`` to molecular targets (receptors, transporters, enzymes, ion
# channels), each binding carrying an ``action`` (antagonist, agonist, reuptake
# inhibitor, ...). Focusing a drug in the viewer dims the brain and animates its
# effect on every region carrying its targets, coloured by each action's net
# ``effect`` (boost / block / modulate).
#
# These four maps are the drug "schema": ``build_records`` validates every
# category / target / action / effect a drug uses against them (and every target
# region against the known structure bases), so a typo in the authored JSON fails
# the build. All are emitted bilingually ({en, fr}) straight into meta.json, so
# (like the receptor maps) the viewer needs no hardcoded drug palette or labels.
# Unlike the anatomy strings, the drug maps are authored bilingually inline rather
# than through the shared FR table: the drug data comes from extraction (a
# separate JSON), so keeping its translations self-contained avoids growing FR.
# ---------------------------------------------------------------------------

# Coarse drug category (a key) -> bilingual legend/search label. Object key order
# is the drug legend's category display order. A drug may list several (e.g. an
# SNRI that is also a chronic-pain treatment); the first is its primary heading.
DRUG_CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "ssri": {"en": "SSRI", "fr": "ISRS"},
    "snri": {"en": "SNRI", "fr": "IRSN"},
    "tricyclic": {"en": "Tricyclic / tetracyclic antidepressant",
                  "fr": "Antidépresseur tricyclique / tétracyclique"},
    "maoi": {"en": "MAO inhibitor", "fr": "Inhibiteur de la MAO"},
    "antidepressant_other": {"en": "Other antidepressant",
                             "fr": "Autre antidépresseur"},
    "antipsychotic_atypical": {"en": "Atypical antipsychotic",
                               "fr": "Antipsychotique atypique"},
    "antipsychotic_conventional": {"en": "Conventional antipsychotic",
                                   "fr": "Antipsychotique classique"},
    "anxiolytic": {"en": "Anxiolytic", "fr": "Anxiolytique"},
    "hypnotic": {"en": "Hypnotic / sedative", "fr": "Hypnotique / sédatif"},
    "benzodiazepine": {"en": "Benzodiazepine", "fr": "Benzodiazépine"},
    "mood_stabilizer": {"en": "Mood stabilizer / anticonvulsant",
                        "fr": "Thymorégulateur / anticonvulsivant"},
    "stimulant": {"en": "Stimulant / wake-promoting",
                  "fr": "Stimulant / éveillant"},
    "adhd_nonstimulant": {"en": "ADHD non-stimulant",
                          "fr": "Non-stimulant (TDAH)"},
    "cognitive_enhancer": {"en": "Cognitive enhancer",
                           "fr": "Activateur cognitif"},
    "substance_use": {"en": "Substance-use treatment",
                      "fr": "Traitement des addictions"},
    "opioid": {"en": "Opioid / opioid modulator",
               "fr": "Opioïde / modulateur opioïde"},
    "other": {"en": "Other", "fr": "Autre"},
}

# Binding action (a key) -> {label {en,fr}, effect}. ``effect`` (boost / block /
# modulate) is the net direction of the drug's action at that target and drives
# the animation colour (DRUG_EFFECT_COLORS). A binding may override ``effect`` for
# an edge case (e.g. an enzyme inhibitor that does not raise a transmitter).
DRUG_ACTIONS: dict[str, dict[str, Any]] = {
    "agonist": {"label": {"en": "Agonist", "fr": "Agoniste"}, "effect": "boost"},
    "partial_agonist": {"label": {"en": "Partial agonist", "fr": "Agoniste partiel"},
                        "effect": "modulate"},
    "antagonist": {"label": {"en": "Antagonist", "fr": "Antagoniste"},
                   "effect": "block"},
    "inverse_agonist": {"label": {"en": "Inverse agonist", "fr": "Agoniste inverse"},
                        "effect": "block"},
    "reuptake_inhibitor": {"label": {"en": "Reuptake inhibitor",
                                     "fr": "Inhibiteur de la recapture"},
                           "effect": "boost"},
    "releaser": {"label": {"en": "Releaser", "fr": "Libérateur"}, "effect": "boost"},
    "enzyme_inhibitor": {"label": {"en": "Enzyme inhibitor",
                                   "fr": "Inhibiteur enzymatique"}, "effect": "boost"},
    "pam": {"label": {"en": "Positive allosteric modulator",
                      "fr": "Modulateur allostérique positif"}, "effect": "boost"},
    "nam": {"label": {"en": "Negative allosteric modulator",
                      "fr": "Modulateur allostérique négatif"}, "effect": "block"},
    "blocker": {"label": {"en": "Channel blocker", "fr": "Bloqueur de canal"},
                "effect": "block"},
    "modulator": {"label": {"en": "Modulator", "fr": "Modulateur"},
                  "effect": "modulate"},
}

# Net-effect (a key) -> animation swatch colour and bilingual label. Distinct hues
# from the projection/sign palette so a drug focus reads as its own thing.
DRUG_EFFECT_COLORS: dict[str, str] = {
    "boost": "#34d399",     # emerald: increases activity / transmitter availability
    "block": "#fb7185",     # rose: blocks / dampens the target
    "modulate": "#c084fc",  # violet: mixed / context-dependent
}
DRUG_EFFECT_LABELS: dict[str, dict[str, str]] = {
    "boost": {"en": "Enhances", "fr": "Renforce"},
    "block": {"en": "Blocks", "fr": "Bloque"},
    "modulate": {"en": "Modulates", "fr": "Module"},
}

# Non-receptor binding targets (a key) -> {name {en,fr}, type, system, regions,
# optional wikipedia}. Receptors already modeled in RECEPTORS are ALSO valid targets
# (a binding may use any receptor id directly); the generator merges them into the
# emitted target map automatically (linking the receptor so its lit regions come
# from its locations), so this table holds only the targets the receptor dataset
# lacks: the reuptake pumps (the core of the SSRIs/SNRIs/TCAs/stimulants), metabolic
# enzymes, ion channels, and a few receptor groups not modeled individually.
# ``type`` is a TARGET_TYPE_LABELS key (transporter / enzyme / ion_channel /
# vesicle_protein / receptor_group), which drives the merged "Receptors & targets"
# legend's swatch colour + tag. ``system`` is a RECEPTOR_FAMILY_LABELS key (or None,
# grouped under "Other") used to slot the target under its neurotransmitter heading
# next to the matching receptors. ``regions`` are structure *base* ids the viewer
# lights for this target (it expands each to both hemispheres), the editorial
# anatomical footprint, mirroring how RECEPTORS map a transmitter system onto the
# modeled structures; an empty list means "no modeled footprint" (listed but
# unfocusable, like a receptor stub). ``wikipedia`` is an optional reference URL
# (left absent -> the panel shows a TODO pill until a real link is verified).
DRUG_TARGETS: dict[str, dict[str, Any]] = {
    # --- Monoamine / GABA transporters (reuptake pumps) ----------------------
    "sert": {"name": {"en": "Serotonin transporter (SERT)",
                      "fr": "Transporteur de la sérotonine (SERT)"},
             "type": "transporter", "system": "serotonergic",
             "wikipedia": "https://en.wikipedia.org/wiki/Serotonin_transporter",
             "regions": ["raphe", "frontal", "temporal", "cingulate", "hippocampus",
                         "amygdala", "thalamus", "hypothalamus", "accumbens"]},
    "net": {"name": {"en": "Norepinephrine transporter (NET)",
                     "fr": "Transporteur de la noradrénaline (NET)"},
            "type": "transporter", "system": "adrenergic",
            "wikipedia": "https://en.wikipedia.org/wiki/Norepinephrine_transporter",
            "regions": ["locus_coeruleus", "frontal", "hippocampus", "thalamus",
                        "hypothalamus", "amygdala", "cerebellum"]},
    "dat": {"name": {"en": "Dopamine transporter (DAT)",
                     "fr": "Transporteur de la dopamine (DAT)"},
            "type": "transporter", "system": "dopaminergic",
            "wikipedia": "https://en.wikipedia.org/wiki/Dopamine_transporter",
            "regions": ["vta", "substantia_nigra", "caudate", "putamen",
                        "accumbens", "frontal"]},
    "gat": {"name": {"en": "GABA transporter (GAT)",
                     "fr": "Transporteur du GABA (GAT)"},
            "type": "transporter", "system": "gabaergic",
            "wikipedia": "https://en.wikipedia.org/wiki/GABA_transporter",
            "regions": ["frontal", "temporal", "thalamus", "hippocampus",
                        "cerebellum"]},
    "vmat2": {"name": {"en": "Vesicular monoamine transporter (VMAT2)",
                       "fr": "Transporteur vésiculaire des monoamines (VMAT2)"},
              "type": "transporter", "system": "dopaminergic",
              "wikipedia":
                  "https://en.wikipedia.org/wiki/Vesicular_monoamine_transporter_2",
              "regions": ["vta", "substantia_nigra", "raphe", "locus_coeruleus",
                          "caudate", "putamen"]},
    # --- Metabolic enzymes ---------------------------------------------------
    "mao_a": {"name": {"en": "Monoamine oxidase A (MAO-A)",
                       "fr": "Monoamine oxydase A (MAO-A)"},
              "type": "enzyme", "system": "serotonergic",
              "wikipedia": "https://en.wikipedia.org/wiki/Monoamine_oxidase_A",
              "regions": ["raphe", "locus_coeruleus", "vta", "substantia_nigra",
                          "midbrain", "pons", "medulla"]},
    "mao_b": {"name": {"en": "Monoamine oxidase B (MAO-B)",
                       "fr": "Monoamine oxydase B (MAO-B)"},
              "type": "enzyme", "system": "dopaminergic",
              "wikipedia": "https://en.wikipedia.org/wiki/Monoamine_oxidase_B",
              "regions": ["substantia_nigra", "vta", "raphe", "midbrain", "pons", "medulla"]},
    "ache": {"name": {"en": "Acetylcholinesterase",
                      "fr": "Acétylcholinestérase"},
             "type": "enzyme", "system": "cholinergic",
             "wikipedia": "https://en.wikipedia.org/wiki/Acetylcholinesterase",
             "regions": ["frontal", "temporal", "hippocampus", "thalamus",
                         "septal_nuclei"]},
    "bche": {"name": {"en": "Butyrylcholinesterase",
                      "fr": "Butyrylcholinestérase"},
             "type": "enzyme", "system": "cholinergic",
             "wikipedia": "https://en.wikipedia.org/wiki/Butyrylcholinesterase",
             "regions": ["frontal", "temporal", "hippocampus"]},
    "carbonic_anhydrase": {"name": {"en": "Carbonic anhydrase",
                                    "fr": "Anhydrase carbonique"},
                           "type": "enzyme", "system": None, "regions": []},
    "pde5": {"name": {"en": "Phosphodiesterase 5 (PDE5)",
                      "fr": "Phosphodiestérase 5 (PDE5)"},
             "type": "enzyme", "system": None, "regions": []},
    # --- Ion channels / vesicle proteins -------------------------------------
    "nav": {"name": {"en": "Voltage-gated sodium channel",
                     "fr": "Canal sodique voltage-dépendant"},
            "type": "ion_channel", "system": None,
            "wikipedia": "https://en.wikipedia.org/wiki/Sodium_channel",
            "regions": ["frontal", "parietal", "temporal", "occipital",
                        "hippocampus", "thalamus"]},
    "cav": {"name": {"en": "Voltage-gated calcium channel",
                     "fr": "Canal calcique voltage-dépendant"},
            "type": "ion_channel", "system": None,
            "wikipedia":
                "https://en.wikipedia.org/wiki/Voltage-gated_calcium_channel",
            "regions": ["frontal", "temporal", "thalamus", "hippocampus"]},
    "cav_a2d": {"name": {"en": "Calcium channel α2δ subunit",
                         "fr": "Sous-unité α2δ du canal calcique"},
                "type": "ion_channel", "system": None,
                "wikipedia": "https://en.wikipedia.org/wiki/L-type_calcium_channel",
                "regions": ["frontal", "temporal", "thalamus", "hippocampus"]},
    "cav_t": {"name": {"en": "T-type calcium channel",
                       "fr": "Canal calcique de type T"},
              "type": "ion_channel", "system": None,
              "wikipedia": "https://en.wikipedia.org/wiki/T-type_calcium_channel",
              "regions": ["thalamus", "frontal", "temporal"]},
    "sv2a": {"name": {"en": "Synaptic vesicle protein 2A (SV2A)",
                      "fr": "Protéine 2A des vésicules synaptiques (SV2A)"},
             "type": "vesicle_protein", "system": None,
             "wikipedia": "https://en.wikipedia.org/wiki/SV2A",
             "regions": ["frontal", "temporal", "hippocampus", "thalamus"]},
    # --- Receptor groups not modeled individually in RECEPTORS ----------------
    "muscarinic": {"name": {"en": "Muscarinic receptors (M1–M5)",
                            "fr": "Récepteurs muscariniques (M1–M5)"},
                   "type": "receptor_group", "system": "cholinergic",
                   "wikipedia":
                       "https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor",
                   "regions": ["frontal", "temporal", "hippocampus", "caudate",
                               "putamen", "thalamus", "hypothalamus"]},
    "nicotinic": {"name": {"en": "Nicotinic receptors",
                           "fr": "Récepteurs nicotiniques"},
                  "type": "receptor_group", "system": "cholinergic",
                  "wikipedia":
                      "https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor",
                  "regions": ["frontal", "temporal", "hippocampus", "thalamus",
                              "vta"]},
    "alpha1": {"name": {"en": "α1 adrenergic receptors",
                        "fr": "Récepteurs α1 adrénergiques"},
               "type": "receptor_group", "system": "adrenergic",
               "wikipedia":
                   "https://en.wikipedia.org/wiki/Alpha-1_adrenergic_receptor",
               "regions": ["frontal", "parietal", "temporal", "occipital",
                           "hippocampus", "thalamus", "midbrain", "pons", "medulla"]},
    "alpha2": {"name": {"en": "α2 adrenergic receptors",
                        "fr": "Récepteurs α2 adrénergiques"},
               "type": "receptor_group", "system": "adrenergic",
               "wikipedia":
                   "https://en.wikipedia.org/wiki/Alpha-2_adrenergic_receptor",
               "regions": ["locus_coeruleus", "frontal", "hippocampus", "thalamus",
                           "hypothalamus", "midbrain", "pons", "medulla"]},
    "beta": {"name": {"en": "β adrenergic receptors",
                      "fr": "Récepteurs β adrénergiques"},
             "type": "receptor_group", "system": "adrenergic",
             "wikipedia": "https://en.wikipedia.org/wiki/Adrenergic_receptor",
             "regions": ["frontal", "parietal", "cingulate", "accumbens",
                         "cerebellum"]},
    "glutamate": {"name": {"en": "Glutamate receptors",
                           "fr": "Récepteurs du glutamate"},
                  "type": "receptor_group", "system": "glutamatergic",
                  "wikipedia": "https://en.wikipedia.org/wiki/Glutamate_receptor",
                  "regions": ["frontal", "temporal", "hippocampus", "thalamus",
                              "cerebellum", "caudate", "putamen"]},
    "melatonin": {"name": {"en": "Melatonin receptors (MT1/MT2)",
                           "fr": "Récepteurs de la mélatonine (MT1/MT2)"},
                  "type": "receptor_group", "system": "melatonergic",
                  "wikipedia": "https://en.wikipedia.org/wiki/Melatonin_receptor",
                  "regions": ["hypothalamus", "thalamus"]},
    "orexin": {"name": {"en": "Orexin receptors (OX1R/OX2R)",
                        "fr": "Récepteurs de l'orexine (OX1R/OX2R)"},
               "type": "receptor_group", "system": None,
               "wikipedia": "https://en.wikipedia.org/wiki/Orexin_receptor",
               "regions": ["hypothalamus", "locus_coeruleus", "raphe", "vta",
                           "thalamus"]},
    "melanocortin": {"name": {"en": "Melanocortin receptors",
                              "fr": "Récepteurs de la mélanocortine"},
                     "type": "receptor_group", "system": None,
                     "wikipedia":
                         "https://en.wikipedia.org/wiki/Melanocortin_receptor",
                     "regions": ["hypothalamus"]},
}

# Coarse kind of a non-receptor drug target -> {en,fr} legend tag. Receptors merged
# in by _build_drug_targets get the implicit "receptor" type (they keep their own
# sign swatch/classification, so they never need this tag). Object key order is the
# within-system row order's secondary sort (receptors first, then these in order).
TARGET_TYPE_LABELS: dict[str, str] = {
    "receptor": "Receptor",
    "transporter": "Transporter",
    "enzyme": "Enzyme",
    "ion_channel": "Ion channel",
    "vesicle_protein": "Vesicle protein",
    "receptor_group": "Receptor group",
}
# Swatch + expression-dot colour per non-receptor target type (a transporter/enzyme/
# channel has no excit/inhib sign, so it can't reuse SIGN_COLORS like a receptor;
# colour by kind instead). Receptor-linked targets use their sign colour, never
# these. Emitted into meta.json (language-neutral), so the viewer hardcodes nothing.
TARGET_TYPE_COLORS: dict[str, str] = {
    "transporter": "#3fb6a8",      # teal
    "enzyme": "#d8a23a",           # amber
    "ion_channel": "#7c83ff",      # periwinkle
    "vesicle_protein": "#5fb56a",  # green
    "receptor_group": "#9aa0a6",   # grey (coarse, like a stand-in)
}

# ---------------------------------------------------------------------------
# Source provenance grades. Every source / reference the viewer shows carries a
# ``provenance`` level saying *how trustworthy its attribution is*, rendered as a
# small coloured pill (the palette + tooltips live in the viewer; the grade here
# is the data). Weakest to strongest:
#   "llm"      grey   - produced by an LLM from memory, unchecked against any
#                       document, so it may be a hallucination.
#   "sourced"  yellow - written by an LLM that was given the source document
#                       (e.g. the Stahl dump), but the specific claim was not
#                       quote-verified.
#   "verified" green  - an LLM extracted a quote, the quote was programmatically
#                       confirmed to be present in the source, and a separate LLM
#                       agreed it supports the claim. (Still LLM-driven, so not
#                       infallible: see the viewer tooltip; going further would
#                       need substantial, error-prone human review, out of scope.)
# The *absence* of any source/reference is rendered as the orange "TODO" pill
# instead; it is not one of these stored grades. Everything currently grades as
# "llm" (the default) until individually upgraded.
PROVENANCE_LEVELS: tuple[str, ...] = ("llm", "sourced", "verified")
DEFAULT_PROVENANCE = "llm"

# Per-link provenance overrides for the *wikipedia* references (which are bare URL
# strings, not ``{citation, url}`` objects, so they have nowhere inline to carry a
# grade). Keyed by the owner's id: a structure *base* id, a receptor id, a
# DRUG_TARGETS key, or a drug id. Anything absent defaults to
# :data:`WIKIPEDIA_DEFAULT_PROVENANCE` below; upgrade an individual link to
# ``verified`` here once it is confirmed to be the canonical article, keeping the
# grading in the data rather than in code.
WIKIPEDIA_PROVENANCE: dict[str, str] = {}

# A *present* wikipedia link is itself a real reference: a CC BY-SA article the
# viewer can open (and live-fetches the lead from, grading that description
# "sourced"). So a reference link defaults to "sourced", NOT the bare "llm": an LLM
# chose which article, but the link points at a genuine source document, not a
# from-memory claim that could be a hallucination (the "llm"/"?" pill, whose tooltip
# says "may be a hallucination", was both wrong and confusing next to a working
# link). The absence of a link is still rendered as the orange NOSOURCE pill by the
# viewer, not as a grade here.
WIKIPEDIA_DEFAULT_PROVENANCE = "sourced"


def _provenance(level: str, what: str) -> str:
    """Validate a provenance grade against :data:`PROVENANCE_LEVELS` (typo guard)."""
    if level not in PROVENANCE_LEVELS:
        raise ValueError(
            f"{what} has unknown provenance {level!r}; "
            f"expected one of {PROVENANCE_LEVELS}")
    return level


def _lookup_provenance(table: dict[str, str], owner_id: str, what: str,
                       default: str = DEFAULT_PROVENANCE) -> str:
    """Grade for ``owner_id`` from an override ``table``, validated.

    The single core behind every per-id provenance map (wikipedia references,
    receptor / target / structure classifications): look the id up, fall back to
    ``default`` (``llm`` unless overridden, e.g. wikipedia links default
    ``sourced``), and validate so an upgraded grade can't be a typo.
    """
    return _provenance(table.get(owner_id, default), what)


def _wiki_provenance(owner_id: str) -> str:
    """Provenance grade for an owner's wikipedia reference (a structure base /
    receptor id / DRUG_TARGETS key / drug id); a present link defaults to
    ``sourced`` (see :data:`WIKIPEDIA_DEFAULT_PROVENANCE`)."""
    return _lookup_provenance(
        WIKIPEDIA_PROVENANCE, owner_id, f"wikipedia reference for {owner_id!r}",
        default=WIKIPEDIA_DEFAULT_PROVENANCE)


# Per-id provenance overrides for the *classification* claims of a receptor (its
# neurotransmitter / mechanism class / sign / synaptic site / locations), a
# non-receptor drug target (its type / system / region footprint) and a brain
# structure (its existence / group / position), all authored from general /
# Wikipedia / textbook knowledge, so they default to the honest ``"llm"`` grade
# (LLM-only, unchecked). Keyed by receptor id / DRUG_TARGETS key / structure *base*
# id; upgrade an entry here as its claim is checked against a document (raise to
# ``"sourced"`` / ``"verified"``), keeping the grading in the data, not in code.
# Empty for now (everything grades as ``"llm"``).
RECEPTOR_PROVENANCE: dict[str, str] = {}
TARGET_PROVENANCE: dict[str, str] = {}
STRUCTURE_PROVENANCE: dict[str, str] = {}


def _receptor_provenance(receptor_id: str) -> str:
    """Provenance grade for a receptor's classification claims (default ``llm``)."""
    return _lookup_provenance(
        RECEPTOR_PROVENANCE, receptor_id,
        f"receptor classification for {receptor_id!r}")


def _target_provenance(target_id: str) -> str:
    """Provenance grade for a non-receptor target's classification (default ``llm``)."""
    return _lookup_provenance(
        TARGET_PROVENANCE, target_id, f"target classification for {target_id!r}")


def _structure_provenance(base_id: str) -> str:
    """Provenance grade for a structure's anatomy claim (default ``llm``)."""
    return _lookup_provenance(
        STRUCTURE_PROVENANCE, base_id, f"structure anatomy for {base_id!r}")


# The constant source backing every drug record (the user-verified fair-use
# citation). Per-drug specifics (the binding profile) come from this single book;
# each drug additionally carries its own ``wikipedia`` link for quick reference.
# ``provenance`` grades the citation (see PROVENANCE_LEVELS): the drug bindings
# were extracted by an LLM given the Stahl dump but were not quote-verified, so
# they would warrant "sourced"; kept at the conservative "llm" default for now.
STAHL_SOURCE: dict[str, str] = {
    "citation": "Stahl SM. Prescriber's Guide: Stahl's Essential "
                "Psychopharmacology. 8th ed. Cambridge University Press; 2024.",
    "url": "TODO",
    "provenance": DEFAULT_PROVENANCE,
}


# Source corpora that the *per-claim* drug sources cite, keyed by a short id. A
# claim's source is ``{corpus, page, quote, provenance}``: ``quote`` is the
# verbatim snippet supporting the claim, ``page`` locates it inside the corpus,
# and ``tools/check_data.py`` confirms (when the corpus's pages are present) that
# the quote really appears on that page, which is what makes a ``"verified"``
# grade trustworthy. The design is source-agnostic: Stahl is the first corpus,
# more can be added here without touching the schema. ``pages_dir`` is an
# author-side path (relative to the repo root) holding one ``<page>.md`` per page
# (see ``sources/books/stahl/`` in CLAUDE.local.md); it is emitted into ``meta.json`` so the
# checker is data-driven, and is simply absent on a checkout without that
# (uncommitted, large) source material, in which case the quote-in-page check is
# skipped while the structural checks still run.
SOURCE_CORPORA: dict[str, dict[str, str]] = {
    "stahl": {
        # Label for the per-claim tooltip ref ("<ref>, p. N"). The full book title
        # + edition, not a bare "Stahl", so a page citation is unambiguous on its
        # own (which Stahl, which edition) without needing the full bibliographic
        # citation below.
        "ref": "Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed.",
        "citation": STAHL_SOURCE["citation"],
        "url": STAHL_SOURCE["url"],
        "pages_dir": "sources/books/stahl/pages",
    },
}


def _quote_sources(sources: Any, what: str) -> list[dict[str, Any]]:
    """Validate + normalize a list of quote-level ``sources`` for any sourced claim.

    Each authored source is ``{corpus, page, quote, provenance}``: ``corpus`` must
    be a :data:`SOURCE_CORPORA` key and ``provenance`` a :data:`PROVENANCE_LEVELS`
    grade. ``"verified"`` is the quote-checked grade, so a verified source *must*
    carry a ``page`` and a non-empty ``quote`` (``check_data.py`` then confirms the
    quote is on that page); weaker grades may omit them. The full citation/url is
    *not* denormalized onto every claim: the viewer resolves it from
    ``meta.source_corpora`` by ``corpus``, keeping ``drugs.jsonl`` lean. ``what`` is
    a human label used in error messages (e.g. ``"Drug 'x' binding 'sert'"``).

    Returns the emitted source dicts (empty list when none are authored). Used for
    a drug's per-binding ``sources`` and its ``nbn_sources`` alike.
    """
    out: list[dict[str, Any]] = []
    for s in sources or []:
        corpus = s.get("corpus")
        if corpus not in SOURCE_CORPORA:
            raise KeyError(
                f"{what} cites unknown source corpus {corpus!r} "
                f"(not a SOURCE_CORPORA key)")
        prov = _provenance(s.get("provenance", DEFAULT_PROVENANCE), f"{what} source")
        rec: dict[str, Any] = {"corpus": corpus, "provenance": prov}
        if s.get("page") is not None:
            rec["page"] = s["page"]
        if s.get("quote"):
            rec["quote"] = s["quote"]
        if prov == "verified" and not (rec.get("page") is not None and rec.get("quote")):
            raise ValueError(
                f"{what} has a 'verified' source without a page + quote (verified "
                f"is the quote-checked grade; use 'sourced'/'llm' for an unquoted "
                f"claim)")
        out.append(rec)
    return out


def _binding_sources(drug_id: str, binding: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-binding ``sources`` (thin wrapper over :func:`_quote_sources`)."""
    return _quote_sources(
        binding.get("sources"),
        f"Drug {drug_id!r} binding {binding.get('target')!r}")


# ---------------------------------------------------------------------------
# Internationalization (en / fr): the data file is bilingual. The anatomy below
# is authored in English; every translatable *display* string (region names,
# group headings, projection-kind labels, neurotransmitters, pathway labels +
# descriptions, circuit names) is wrapped with ``_t()`` when the records are
# built, turning "Foo" into {"en": "Foo", "fr": FR["Foo"]}. The viewer
# (js/data.js + window.__I18N__.pick) collapses that to the chosen language.
#
# FR is the single French translation source, keyed by the exact English string
# (so a string used in several places is translated once and stays consistent).
# A missing key is collected and raised at build time (see build_records), so the
# data can never silently ship a half-translated record. Source citations + URLs
# are intentionally NOT translated.
#
# Per-hemisphere names are composed, not stored: English prefixes "Right "/"Left "
# to the lowercased base name; French suffixes the gender/number-agreed
# "droit/droite/droits/droites" (right) or "gauche/gauches" (left). A paired
# entry may set ``fr_gender`` ("m" default, "f", "mp", "fp") for that agreement.
# ---------------------------------------------------------------------------

_FR_RIGHT = {"m": "droit", "f": "droite", "mp": "droits", "fp": "droites"}
_FR_LEFT = {"m": "gauche", "f": "gauche", "mp": "gauches", "fp": "gauches"}

# English -> French for every translatable data string.
FR: dict[str, str] = {
    # Group headings
    "Lobes": "Lobes",
    "Basal ganglia / deep nuclei": "Ganglions de la base / noyaux profonds",
    "Diencephalon": "Diencéphale",
    "Limbic": "Système limbique",
    "Hindbrain": "Rhombencéphale",
    # Projection-kind labels (the functional class shown next to the molecule)
    "excitatory": "excitateur",
    "inhibitory": "inhibiteur",
    "dopaminergic": "dopaminergique",
    "cholinergic": "cholinergique",
    "neuroendocrine": "neuroendocrine",
    "serotonergic": "sérotoninergique",
    "noradrenergic": "noradrénergique",
    # Sign-mode legend headings (capitalized; distinct from the lowercase kind
    # labels above, which read inline as "Glutamate (excitatory)").
    "Excitatory": "Excitateur",
    "Inhibitory": "Inhibiteur",
    "Modulatory": "Modulateur",
    # Neurotransmitters
    "Glutamate": "Glutamate",
    "GABA": "GABA",
    "Dopamine": "Dopamine",
    "Acetylcholine": "Acétylcholine",
    "Releasing hormones": "Hormones de libération",
    # Structure base names
    "Frontal lobe": "Lobe frontal",
    "Parietal lobe": "Lobe pariétal",
    "Temporal lobe": "Lobe temporal",
    "Occipital lobe": "Lobe occipital",
    "Insula": "Insula",
    "Caudate nucleus": "Noyau caudé",
    "Putamen": "Putamen",
    "Globus pallidus": "Globus pallidus",
    "Thalamus": "Thalamus",
    "Subthalamic nucleus": "Noyau subthalamique",
    "Substantia nigra": "Substance noire",
    "Nucleus accumbens": "Noyau accumbens",
    "Claustrum": "Claustrum",
    "Hippocampus": "Hippocampe",
    "Amygdala": "Amygdale",
    "Cingulate gyrus": "Gyrus cingulaire",
    "Fornix": "Fornix",
    "Olfactory bulb": "Bulbe olfactif",
    "Septal nuclei": "Noyaux septaux",
    "Hypothalamus": "Hypothalamus",
    "Mammillary bodies": "Corps mammillaires",
    "Pituitary gland": "Hypophyse",
    "Cerebellum": "Cervelet",
    "Midbrain": "Mésencéphale",
    "Pons": "Pont",
    "Medulla": "Bulbe rachidien",
    # Monoamine source nuclei + their group heading
    "Brainstem nuclei": "Noyaux du tronc cérébral",
    "Raphe nuclei": "Noyaux du raphé",
    "Locus coeruleus": "Locus cœruleus",
    "Ventral tegmental area": "Aire tegmentale ventrale",
    # Circuit names
    "Direct pathway (motor)": "Voie directe (motrice)",
    "Indirect pathway": "Voie indirecte",
    "Nigrostriatal (dopamine)": "Voie nigrostriée (dopamine)",
    "Cortico-cerebellar (motor)": "Cortico-cérébelleux (moteur)",
    "Hippocampal / limbic (Papez)": "Hippocampique / limbique (Papez)",
    "Commissures (interhemispheric)": "Commissures (interhémisphériques)",
    # Projection labels
    "Corticostriatal (motor)": "Corticostriée (motrice)",
    "Corticostriatal (associative)": "Corticostriée (associative)",
    "Corticostriatal (parietal)": "Corticostriée (pariétale)",
    "Corticostriatal (temporal)": "Corticostriée (temporale)",
    "Hyperdirect (corticosubthalamic)": "Hyperdirecte (cortico-subthalamique)",
    "Striatopallidal (direct)": "Striatopallidale (directe)",
    "Striatonigral (direct)": "Striatonigrale (directe)",
    "Pallidosubthalamic (indirect)": "Pallidosubthalamique (indirecte)",
    "Subthalamopallidal": "Subthalamopallidale",
    "Nigrostriatal": "Nigrostriée",
    "Pallidothalamic": "Pallidothalamique",
    "Nigrothalamic": "Nigrothalamique",
    "Thalamocortical": "Thalamocorticale",
    "Corticothalamic (visual)": "Corticothalamique (visuelle)",
    "Corticopontine": "Corticopontique",
    "Pontocerebellar (mossy fibers)": "Pontocérébelleuse (fibres moussues)",
    "Cerebellothalamic (dentatothalamic)": "Cérébellothalamique (dentatothalamique)",
    "Perforant path": "Voie perforante",
    "Fornix (hippocampal output)": "Fornix (sortie hippocampique)",
    "Postcommissural fornix": "Fornix postcommissural",
    "Mammillothalamic tract": "Faisceau mammillothalamique",
    "Anterior thalamocingulate": "Thalamo-cingulaire antérieure",
    "Cingulum (to hippocampus)": "Cingulum (vers l'hippocampe)",
    "Olfactory projection (to amygdala)": "Projection olfactive (vers l'amygdale)",
    "Olfactory projection (to olfactory cortex)":
        "Projection olfactive (vers le cortex olfactif)",
    "Stria terminalis": "Strie terminale",
    "Hippocamposeptal projection": "Projection hippocamposeptale",
    "Septohippocampal pathway": "Voie septohippocampique",
    "Mesolimbic dopamine pathway": "Voie dopaminergique mésolimbique",
    "Accumbens to ventral pallidum": "Accumbens vers pallidum ventral",
    "Hypothalamo-hypophyseal axis": "Axe hypothalamo-hypophysaire",
    "Corpus callosum (frontal)": "Corps calleux (frontal)",
    "Corpus callosum (parietal)": "Corps calleux (pariétal)",
    "Corpus callosum (splenium / occipital)": "Corps calleux (splénium / occipital)",
    "Anterior commissure": "Commissure antérieure",
    "Claustro-frontal projection": "Projection claustro-frontale",
    "Claustro-insular projection": "Projection claustro-insulaire",
    "Salience network link": "Lien du réseau de saillance",
    "Basolateral amygdala to accumbens": "Amygdale basolatérale vers accumbens",
    "Mammillary-hypothalamic link": "Lien mammillo-hypothalamique",
    "Septohypothalamic projection": "Projection septo-hypothalamique",
    # Ascending monoamine system labels (the brainstem source nuclei)
    "Ascending serotonergic (prefrontal)":
        "Sérotoninergique ascendante (préfrontale)",
    "Ascending serotonergic (hippocampal)":
        "Sérotoninergique ascendante (hippocampique)",
    "Ascending serotonergic (amygdala)":
        "Sérotoninergique ascendante (amygdale)",
    "Ascending serotonergic (hypothalamic)":
        "Sérotoninergique ascendante (hypothalamique)",
    "Ascending noradrenergic (prefrontal)":
        "Noradrénergique ascendante (préfrontale)",
    "Ascending noradrenergic (hippocampal)":
        "Noradrénergique ascendante (hippocampique)",
    "Ascending noradrenergic (amygdala)":
        "Noradrénergique ascendante (amygdale)",
    "Ascending noradrenergic (thalamic)":
        "Noradrénergique ascendante (thalamique)",
    "Mesolimbic (VTA)": "Mésolimbique (ATV)",
    "Mesocortical": "Mésocorticale",
    "Mesolimbic (amygdala)": "Mésolimbique (amygdale)",
    "Mesolimbic (hippocampal)": "Mésolimbique (hippocampique)",
    # Projection descriptions
    "Dorsal raphe serotonin neurons project diffusely to the prefrontal cortex, "
    "shaping mood and cognition.":
        "Les neurones sérotoninergiques du raphé dorsal projettent de façon "
        "diffuse vers le cortex préfrontal, modulant l'humeur et la cognition.",
    "Median raphe serotonin projects to the hippocampus.":
        "La sérotonine du raphé médian projette vers l'hippocampe.",
    "Raphe serotonin modulates the amygdala, tuning emotional reactivity.":
        "La sérotonine du raphé module l'amygdale, ajustant la réactivité "
        "émotionnelle.",
    "Raphe serotonin projects to the hypothalamus, influencing sleep, appetite "
    "and neuroendocrine rhythms.":
        "La sérotonine du raphé projette vers l'hypothalamus, influençant le "
        "sommeil, l'appétit et les rythmes neuroendocriniens.",
    "Locus coeruleus noradrenaline projects diffusely to the cortex, driving "
    "arousal and attention.":
        "La noradrénaline du locus cœruleus projette de façon diffuse vers le "
        "cortex, soutenant l'éveil et l'attention.",
    "Locus coeruleus noradrenaline projects to the hippocampus.":
        "La noradrénaline du locus cœruleus projette vers l'hippocampe.",
    "Locus coeruleus noradrenaline sharpens amygdala-dependent emotional "
    "memory.":
        "La noradrénaline du locus cœruleus renforce la mémoire émotionnelle "
        "dépendante de l'amygdale.",
    "Locus coeruleus noradrenaline projects to the thalamus.":
        "La noradrénaline du locus cœruleus projette vers le thalamus.",
    "VTA dopamine projects to the nucleus accumbens, the core of the reward "
    "pathway.":
        "La dopamine de l'ATV projette vers le noyau accumbens, cœur du circuit "
        "de la récompense.",
    "VTA dopamine projects to the prefrontal cortex, supporting motivation and "
    "executive control.":
        "La dopamine de l'ATV projette vers le cortex préfrontal, soutenant la "
        "motivation et le contrôle exécutif.",
    "VTA dopamine innervates the amygdala.":
        "La dopamine de l'ATV innerve l'amygdale.",
    "VTA dopamine projects to the hippocampus, gating reward-related memory.":
        "La dopamine de l'ATV projette vers l'hippocampe, contrôlant la mémoire "
        "liée à la récompense.",
    "Sensorimotor frontal cortex drives the putamen, the motor input nucleus "
    "of the basal ganglia.":
        "Le cortex frontal sensorimoteur active le putamen, le noyau d'entrée "
        "moteur des ganglions de la base.",
    "Prefrontal cortex drives the caudate (associative striatum).":
        "Le cortex préfrontal active le noyau caudé (striatum associatif).",
    "Posterior parietal association cortex projects to the caudate.":
        "Le cortex associatif pariétal postérieur projette vers le noyau caudé.",
    "Temporal association cortex projects to the striatum.":
        "Le cortex associatif temporal projette vers le striatum.",
    "Cortex excites the subthalamic nucleus directly, the fast 'hyperdirect' "
    "brake on movement.":
        "Le cortex excite directement le noyau subthalamique, le frein "
        "« hyperdirect » rapide du mouvement.",
    "Direct-pathway striatal neurons inhibit the internal pallidum, releasing "
    "(disinhibiting) the thalamus.":
        "Les neurones striataux de la voie directe inhibent le pallidum "
        "interne, libérant (désinhibant) le thalamus.",
    "Caudate direct-pathway output to the internal pallidum.":
        "Sortie de la voie directe du noyau caudé vers le pallidum interne.",
    "Direct-pathway striatal output to the substantia nigra pars reticulata.":
        "Sortie striatale de la voie directe vers la substance noire pars "
        "reticulata.",
    "Caudate direct-pathway output to the substantia nigra.":
        "Sortie de la voie directe du noyau caudé vers la substance noire.",
    "External pallidum inhibits the STN in the indirect pathway.":
        "Le pallidum externe inhibe le noyau subthalamique dans la voie "
        "indirecte.",
    "The STN excites the pallidum, amplifying basal-ganglia output "
    "(indirect/hyperdirect pathways).":
        "Le noyau subthalamique excite le pallidum, amplifiant la sortie des "
        "ganglions de la base (voies indirecte/hyperdirecte).",
    "Substantia nigra pars compacta dopamine sets the balance between the "
    "direct and indirect striatal pathways.":
        "La dopamine de la substance noire pars compacta règle l'équilibre "
        "entre les voies striatales directe et indirecte.",
    "Dopaminergic modulation of the caudate.":
        "Modulation dopaminergique du noyau caudé.",
    "The internal pallidum tonically inhibits the motor thalamus, the output "
    "gate of the loop.":
        "Le pallidum interne inhibe de façon tonique le thalamus moteur, la "
        "porte de sortie de la boucle.",
    "Substantia nigra pars reticulata inhibitory output to the thalamus.":
        "Sortie inhibitrice de la substance noire pars reticulata vers le "
        "thalamus.",
    "Motor thalamus excites frontal cortex, closing the "
    "cortico-basal-ganglia-thalamo-cortical loop.":
        "Le thalamus moteur excite le cortex frontal, fermant la boucle "
        "cortico-ganglions de la base-thalamo-corticale.",
    "Occipital (visual) cortex reciprocally connects with the thalamus "
    "(pulvinar / lateral geniculate).":
        "Le cortex occipital (visuel) est réciproquement connecté au thalamus "
        "(pulvinar / corps genouillé latéral).",
    "Cortex projects to the pontine nuclei (pons), the first leg of the "
    "cortico-ponto-cerebellar route.":
        "Le cortex projette vers les noyaux du pont, première "
        "étape de la voie cortico-ponto-cérébelleuse.",
    "Pontine nuclei send mossy fibers to the cerebellar cortex.":
        "Les noyaux du pont envoient des fibres moussues au cortex cérébelleux.",
    "Deep cerebellar nuclei drive the motor thalamus, feeding the cerebellar "
    "loop back to cortex.":
        "Les noyaux cérébelleux profonds activent le thalamus moteur, renvoyant "
        "la boucle cérébelleuse vers le cortex.",
    "Entorhinal (medial temporal) cortex drives the hippocampus via the "
    "perforant path.":
        "Le cortex entorhinal (temporal médial) active l'hippocampe via la voie "
        "perforante.",
    "The major hippocampal output gathers into the fornix, the great arching "
    "tract of the Papez circuit.":
        "La principale sortie hippocampique se rassemble dans le fornix, le "
        "grand faisceau arqué du circuit de Papez.",
    "The fornix carries hippocampal output forward to the mammillary bodies "
    "(Papez circuit).":
        "Le fornix transporte la sortie hippocampique vers les corps "
        "mammillaires (circuit de Papez).",
    "Mammillary bodies project to the anterior thalamic nuclei, continuing the "
    "Papez circuit.":
        "Les corps mammillaires projettent vers les noyaux thalamiques "
        "antérieurs, poursuivant le circuit de Papez.",
    "The anterior thalamic nuclei project to the cingulate gyrus, the next leg "
    "of the Papez circuit.":
        "Les noyaux thalamiques antérieurs projettent vers le gyrus cingulaire, "
        "étape suivante du circuit de Papez.",
    "The cingulate gyrus projects back to the hippocampus via the cingulum, "
    "closing the Papez loop.":
        "Le gyrus cingulaire reprojette vers l'hippocampe via le cingulum, "
        "fermant la boucle de Papez.",
    "Mitral cells of the olfactory bulb project to the corticomedial amygdala.":
        "Les cellules mitrales du bulbe olfactif projettent vers l'amygdale "
        "corticomédiale.",
    "Bulbar output reaches the piriform / insular olfactory cortex.":
        "La sortie bulbaire atteint le cortex olfactif piriforme / insulaire.",
    "The amygdala projects to the hypothalamus via the stria terminalis, "
    "driving autonomic / endocrine responses.":
        "L'amygdale projette vers l'hypothalamus via la strie terminale, "
        "déclenchant des réponses autonomes / endocrines.",
    "Hippocampal fibers run in the precommissural fornix to the septal nuclei.":
        "Les fibres hippocampiques cheminent dans le fornix précommissural vers "
        "les noyaux septaux.",
    "Medial septal cholinergic neurons project to the hippocampus, pacing the "
    "hippocampal theta rhythm.":
        "Les neurones cholinergiques du septum médial projettent vers "
        "l'hippocampe, cadençant le rythme thêta hippocampique.",
    "Midbrain dopaminergic neurons (VTA / substantia nigra) project to the "
    "nucleus accumbens, the reward hub.":
        "Les neurones dopaminergiques du mésencéphale (ATV / substance noire) "
        "projettent vers le noyau accumbens, le centre de la récompense.",
    "Nucleus accumbens medium spiny neurons project to the (ventral) pallidum, "
    "the ventral-striatal output.":
        "Les neurones épineux moyens du noyau accumbens projettent vers le "
        "pallidum (ventral), la sortie du striatum ventral.",
    "Hypothalamic neurons drive the pituitary via the median eminence / portal "
    "system and the posterior hypophyseal tract.":
        "Les neurones hypothalamiques commandent l'hypophyse via l'éminence "
        "médiane / le système porte et le tractus hypophysaire postérieur.",
    "Homotopic callosal fibers linking the two frontal lobes.":
        "Fibres calleuses homotopiques reliant les deux lobes frontaux.",
    "Homotopic callosal fibers linking the two parietal lobes.":
        "Fibres calleuses homotopiques reliant les deux lobes pariétaux.",
    "Splenial callosal fibers linking the two occipital lobes.":
        "Fibres calleuses spléniales reliant les deux lobes occipitaux.",
    "Older commissure linking the temporal lobes (and olfactory structures).":
        "Commissure plus ancienne reliant les lobes temporaux (et les "
        "structures olfactives).",
    "Reciprocal claustro-cortical link with prefrontal cortex (implicated in "
    "salience / attention).":
        "Lien claustro-cortical réciproque avec le cortex préfrontal (impliqué "
        "dans la saillance / l'attention).",
    "The claustrum tightly interconnects with the adjacent insular cortex.":
        "Le claustrum est étroitement interconnecté avec le cortex insulaire "
        "adjacent.",
    "The anterior insula and the cingulate co-activate as the salience network.":
        "L'insula antérieure et le cortex cingulaire s'activent ensemble comme "
        "réseau de saillance.",
    "Basolateral amygdala glutamatergic input to the ventral striatum "
    "(motivational salience).":
        "Entrée glutamatergique de l'amygdale basolatérale vers le striatum "
        "ventral (saillance motivationnelle).",
    "The mammillary bodies sit within and connect to the posterior "
    "hypothalamus.":
        "Les corps mammillaires se situent dans l'hypothalamus postérieur et "
        "s'y connectent.",
    "The septal nuclei project to the hypothalamus, a limbic-autonomic relay.":
        "Les noyaux septaux projettent vers l'hypothalamus, un relais "
        "limbique-autonome.",
    # --- Receptor family / class / synaptic labels + receptor neurotransmitters.
    # (Receptor descriptions are authored inline as {en, fr} pairs in RECEPTORS,
    #  not via this table, since each is unique.)
    "Adrenergic": "Adrénergique",
    "Cholinergic": "Cholinergique",
    "Dopaminergic": "Dopaminergique",
    "GABAergic": "GABAergique",
    "Glutamatergic": "Glutamatergique",
    "Glycinergic": "Glycinergique",
    "Histaminergic": "Histaminergique",
    "Opioidergic": "Opioïdergique",
    "Serotonergic": "Sérotoninergique",
    "Cannabinoid": "Cannabinoïde",
    "Purinergic": "Purinergique",
    "Sigma": "Sigma",
    "Melatonergic": "Mélatoninergique",
    "Ionotropic (ligand-gated ion channel)":
        "Ionotrope (canal ionique ligand-dépendant)",
    "Metabotropic (GPCR)": "Métabotrope (RCPG)",
    "Intracellular chaperone": "Chaperon intracellulaire",
    "Presynaptic": "Présynaptique",
    "Postsynaptic": "Postsynaptique",
    "Pre- and postsynaptic": "Pré- et postsynaptique",
    # Drug-target type tags (the merged "Receptors & targets" legend).
    "Receptor": "Récepteur",
    "Transporter": "Transporteur",
    "Enzyme": "Enzyme",
    "Ion channel": "Canal ionique",
    "Vesicle protein": "Protéine vésiculaire",
    "Receptor group": "Groupe de récepteurs",
    "Noradrenaline": "Noradrénaline",
    "Serotonin": "Sérotonine",
    "Histamine": "Histamine",
    "Opioid peptides": "Peptides opioïdes",
    "Glycine": "Glycine",
    "Endocannabinoids": "Endocannabinoïdes",
    "Adenosine": "Adénosine",
    "Sigma ligands": "Ligands sigma",
    "Melatonin": "Mélatonine",
}

# English strings reached by _t() that had no FR entry; build_records raises with
# the full list so a missing translation fails the build instead of shipping.
_MISSING_TRANSLATIONS: set[str] = set()


def _t(text: str) -> dict[str, str]:
    """Wrap an English display string as a bilingual ``{"en", "fr"}`` object.

    The French comes from :data:`FR` (the single translation source). A string
    with no FR entry is recorded in :data:`_MISSING_TRANSLATIONS` (and falls back
    to English) so :func:`build_records` can fail loudly listing every
    untranslated string at once.
    """
    fr = FR.get(text)
    if fr is None:
        _MISSING_TRANSLATIONS.add(text)
        fr = text
    return {"en": text, "fr": fr}


def _side_name(base: dict[str, str], gender: str, side: str) -> dict[str, str]:
    """Compose a per-hemisphere display name in both languages from a base name.

    English prefixes ``Right``/``Left`` to the lowercased base; French suffixes
    the agreed ``droit``/``gauche`` form (see :data:`_FR_RIGHT` / :data:`_FR_LEFT`).
    """
    word = "Right" if side == "R" else "Left"
    fr_word = (_FR_RIGHT if side == "R" else _FR_LEFT)[gender]
    return {
        "en": f"{word} {base['en'].lower()}",
        "fr": f"{base['fr']} {fr_word}",
    }


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

# name, group, right-side position, color, radii, seed, detail, noise
PAIRED: list[dict[str, Any]] = [
    # --- Cortical lobes (large, outer shell) ---
    dict(base="frontal", name="Frontal lobe", group="lobe",
         # Cortical lobes share a muted pink palette (low saturation so they read
         # as one cortex, not "pop" colors), each a slightly different hue so the
         # four stay tellable apart: frontal=rose, parietal=pink, temporal=salmon,
         # occipital=mauve-pink.
         pos=(0.85, 1.0, 2.2), color="#c58c9a",
         # Largest lobe; a smooth gyrified dome whose surface "curls" are a
         # shading normal-map (GYRUS_BUMP in shapes.js), not geometry, so the mesh
         # stays smooth (no faceting) and the curls are lighting only.
         # Anterior-superior quadrant of the hemisphere; `medial` gives it a flat
         # wall at the midline so left+right meet at the longitudinal fissure.
         # Lobes are sized to overlap their neighbors so the union reads as one
         # continuous cortical surface (no gaps) when assembled at explode 0.
         radii=(1.95, 1.8, 2.1), seed=11, detail=6, noise=0.10,
         octaves=2, medial=True),
    dict(base="parietal", name="Parietal lobe", group="lobe",
         pos=(0.85, 1.8, -0.2), color="#c69597",
         # Superior-posterior quadrant, behind the frontal and above the
         # occipital; smooth dome with a flat medial wall at the fissure (the
         # surface "curls" are a shading normal-map, see GYRUS_BUMP in shapes.js).
         radii=(1.9, 1.7, 1.8), seed=12, detail=6, noise=0.10,
         octaves=2, medial=True),
    dict(base="temporal", name="Temporal lobe", group="lobe",
         pos=(1.95, -0.75, 0.6), color="#c79a8e",
         # Inferior-lateral, elongated antero-posteriorly (a finger-shaped lobe).
         # It sits below the Sylvian fissure so it is NOT medial (stays lateral,
         # not at the midline); its top is clipped flat (ymax) to seat under the
         # fronto-parietal mass.
         radii=(1.25, 1.1, 2.15), seed=13, detail=6, noise=0.10,
         octaves=2, clip=dict(ymax=0.95)),
    dict(base="occipital", name="Occipital lobe", group="lobe",
         pos=(0.72, 0.75, -2.9), color="#bf8da6",
         # Smallest lobe, the posterior pole; compact, behind the parietal and
         # above the cerebellum, with a flat medial wall.
         radii=(1.7, 1.5, 1.6), seed=14, detail=6, noise=0.10,
         octaves=2, medial=True),
    dict(base="insula", name="Insula", group="lobe", fr_gender="f",
         pos=(2.2, 0.3, 0.55), color="#ae7aa3",
         # The hidden 5th lobe: cortex buried deep to the lateral (Sylvian)
         # sulcus, overlying the putamen, walled off by the fronto-parietal +
         # temporal opercula. Small lateral patch (flattened mediolaterally), NOT
         # medial. Gyrified like the other lobes (so it gets the gyrus bump). It
         # is mostly tucked inside at explode 0 and revealed by blowing out.
         # It sits IN the lateral (Sylvian) gap between the opercula, plugging it
         # so the deep nuclei (putamen) don't show through, but its lateral surface
         # MUST stay just medial to (inside) those opercula or it pokes out of the
         # brain: with x-radius 0.46 the lateral edge sits at x=2.66, inside the
         # frontal (~2.8) and temporal (~2.81 at this y,z) surfaces. It earlier sat
         # at x=2.5 (radius 0.5, surface reaching x=3.0), so it bulged out in front
         # of the lobes; pulled too far in (x=2.0) it instead exposed the putamen
         # through the gap, so it is parked flush in between.
         # NOTE: as a `lobe` blob it takes part in the same-group jigsaw clip
         # against the big lobes; its small size means the seams cut a fair bit
         # off it. Position/size are an anatomical guess: tune in a browser.
         radii=(0.46, 1.05, 1.2), seed=15, detail=6, noise=0.10,
         octaves=2),
    # --- Basal ganglia & deep nuclei (small, inner) ---
    dict(base="caudate", name="Caudate nucleus", group="basal_ganglia",
         # Retracted (y was 1.9, an earlier "emerge through the fronto-parietal
         # seam" experiment) so the bulbous head now sits below the cortical
         # surface and stays hidden inside the assembled brain at explode 0,
         # surfacing only as the lobes blow apart. The lobe-carve that used to
         # notch a channel around the exposed head is dropped with it (it would
         # otherwise cut a visible trench in the dome once the caudate sinks);
         # anatomically deeper and no longer poking out between the lobes.
         pos=(1.2, 1.1, 0.8), color="#ff9da7",
         # Genuinely C-shaped: a bulbous head (anterior-superior) arching over
         # and back, then a thin tail curling down and forward. Modeled as a
         # tapered tube along a parasagittal (x~0) spline so it reads as the
         # comma it is rather than a convex blob. Spine runs head -> tail; z is
         # anterior(+), y is superior(+).
         shape=dict(
             type="curve",
             points=[
                 (0.0, 0.55, 1.05),   # head: anterior + superior, bulbous
                 (0.0, 0.90, 0.45),   # rising
                 (0.0, 0.92, -0.35),  # top of the arch, heading posterior
                 (0.0, 0.55, -1.00),  # descending at the back
                 (0.0, -0.20, -1.00), # down the posterior wall
                 (0.0, -0.80, -0.50), # bottom, curling forward
                 (0.0, -0.98, 0.25),  # tail moving anteriorly
                 (0.0, -0.85, 0.90),  # tail tip (toward the temporal lobe)
             ],
             profile=[0.48, 0.40, 0.33, 0.29, 0.25, 0.20, 0.13, 0.06],
             seed=21, noise=0.1, radial_segments=14, tubular_segments=110,
         )),
    dict(base="putamen", name="Putamen", group="basal_ganglia",
         pos=(2.0, 0.2, 0.6), color="#f28e2b",
         # Rounded shell, the most lateral nucleus: flattened mediolaterally
         # (thin x), taller/deeper. Smooth surface (higher detail, low noise so
         # it reads as a clean lens, not a faceted potato).
         radii=(0.45, 1.05, 1.2), seed=22, detail=5, noise=0.06),
    dict(base="globus_pallidus", name="Globus pallidus", group="basal_ganglia",
         pos=(1.5, 0.0, 0.2), color="#76b7b2",
         # Smaller wedge sitting medial to the putamen; smooth. Together with the
         # putamen it forms the lens-shaped lentiform nucleus.
         radii=(0.4, 0.72, 0.82), seed=23, detail=5, noise=0.06),
    dict(base="thalamus", name="Thalamus", group="basal_ganglia",
         pos=(0.9, 0.4, -0.6), color="#bab0ac",
         # Large ovoid "egg", the biggest deep nucleus; smooth, slightly
         # elongated antero-posteriorly.
         radii=(0.82, 0.78, 1.1), seed=24, detail=5, noise=0.05),
    dict(base="subthalamic_nucleus", name="Subthalamic nucleus",
         group="basal_ganglia",
         pos=(1.3, -0.9, -0.6), color="#d37295",
         # Tiny biconvex lens; flattened in y, smooth.
         radii=(0.34, 0.26, 0.52), seed=25, detail=5, noise=0.05),
    dict(base="substantia_nigra", name="Substantia nigra",
         group="basal_ganglia", fr_gender="f",
         pos=(1.0, -1.4, -1.2), color="#3d3d3d",
         # A thin lamina/band in the midbrain: flat in y, elongated in z.
         radii=(0.5, 0.18, 0.68), seed=26, detail=5, noise=0.05),
    dict(base="accumbens", name="Nucleus accumbens", group="basal_ganglia",
         pos=(0.95, -0.5, 1.0), color="#e0997e",
         # Ventral striatum, where the head of the caudate meets the putamen
         # ventrally and anteriorly (the reward hub, target of the mesolimbic
         # dopamine pathway). Small smooth nucleus, anterior + low + fairly
         # medial. Position is an anatomical guess: tune in a browser.
         radii=(0.4, 0.34, 0.44), seed=27, detail=5, noise=0.06),
    dict(base="claustrum", name="Claustrum", group="basal_ganglia",
         pos=(2.5, 0.1, 0.5), color="#8d97ab",
         # Thin vertical sheet of grey matter between the insula (lateral) and the
         # putamen (medial), separated from each by a white-matter capsule. Modeled
         # as an ellipsoid squashed mediolaterally (very thin x) so it reads as a
         # lamina, not a lump. NOTE: thin + same-group as the putamen, so the
         # jigsaw clip may pare it; tune position/size in a browser.
         radii=(0.07, 0.7, 0.95), seed=28, detail=5, noise=0.05),
    # --- Limbic / diencephalon ---
    dict(base="hippocampus", name="Hippocampus", group="limbic",
         pos=(1.3, -0.7, -0.2), color="#b3823e",
         # Curved allocortical structure in the floor of the temporal lobe; runs
         # antero-posteriorly with the tail curling up toward the splenium, so a
         # tapered tube (curve) reads as the seahorse it is, not a blob. Spine is
         # parasagittal (local x~0) so the _L member mirrors correctly. Sits
         # medially inside the temporal lobe at explode 0.
         shape=dict(
             type="curve",
             points=[
                 (0.0, -0.15, 1.10),   # head: anterior + inferior (pes)
                 (0.0, -0.05, 0.50),
                 (0.0, 0.05, -0.10),   # body
                 (0.0, 0.20, -0.70),
                 (0.0, 0.45, -1.15),   # tail: posterior, curling up
             ],
             profile=[0.34, 0.32, 0.28, 0.22, 0.13],
             seed=51, noise=0.08, radial_segments=12, tubular_segments=80,
         )),
    dict(base="amygdala", name="Amygdala", group="limbic", fr_gender="f",
         pos=(1.45, -0.35, 0.95), color="#9b7bb0",
         # Almond-shaped nucleus in the medial temporal lobe, just anterior and
         # superior to the head of the hippocampus (emotion/fear hub). Small
         # smooth blob. Sits inside the temporal lobe at explode 0. Position is an
         # anatomical guess: tune in a browser.
         radii=(0.42, 0.4, 0.42), seed=54, detail=5, noise=0.06),
    dict(base="cingulate", name="Cingulate gyrus", group="limbic",
         pos=(0.5, 0.6, 0.0), color="#6fa39c",
         # The limbic-lobe arch: a C-shaped band of cortex on the medial wall,
         # curving over the corpus callosum from the subgenual front, up and over,
         # to the splenial back. Modeled as a tapered tube along a parasagittal
         # (local x~0) arch so it reads as the gyrus it is; the _L member mirrors
         # it. Hugs the midline (small pos.x). Position is a guess: tune in a
         # browser, especially against the (commissural) corpus-callosum arrow.
         shape=dict(
             type="curve",
             points=[
                 (0.0, -0.5, 1.3),    # subgenual, anterior + low
                 (0.0, 0.4, 1.5),     # rising in front of the genu
                 (0.0, 1.0, 0.95),    # anterior arch
                 (0.0, 1.2, 0.0),     # top of the arch
                 (0.0, 1.0, -0.95),   # posterior arch
                 (0.0, 0.3, -1.5),    # descending toward the splenium
                 (0.0, -0.45, -1.25), # isthmus, posterior + low
             ],
             profile=[0.18, 0.3, 0.34, 0.34, 0.32, 0.28, 0.18],
             seed=55, noise=0.07, radial_segments=12, tubular_segments=96,
         )),
    dict(base="fornix", name="Fornix", group="limbic",
         pos=(0.4, 0.2, -0.3), color="#d9d2c4",
         # The hippocampal output tract: a thin white-matter arch sweeping from
         # the hippocampus (posterior) up under the corpus callosum and forward,
         # then down as the columns toward the mammillary bodies. A slender
         # parasagittal curve (mirrored for the _L side). Position is a guess:
         # tune in a browser.
         shape=dict(
             type="curve",
             points=[
                 (0.0, -0.1, -1.0),   # crus, by the hippocampal tail (posterior)
                 (0.0, 0.6, -0.55),   # arching up
                 (0.0, 0.8, 0.2),     # body, under the callosum
                 (0.0, 0.15, 0.6),    # the descending column (anterior)
                 (0.0, -0.65, 0.5),   # toward the mammillary body
             ],
             profile=[0.1, 0.12, 0.12, 0.1, 0.08],
             seed=56, noise=0.05, radial_segments=10, tubular_segments=80,
         )),
    dict(base="olfactory_bulb", name="Olfactory bulb", group="limbic",
         pos=(0.45, -1.05, 2.7), color="#9aa86f",
         # Small elongated bulb on the orbital underside of the frontal lobe,
         # running antero-posteriorly along the cribriform plate (the front end of
         # the olfactory tract). Stretched in z, near the midline. Position is a
         # guess: tune in a browser.
         radii=(0.18, 0.16, 0.45), seed=57, detail=5, noise=0.05),
    dict(base="septal_nuclei", name="Septal nuclei", group="limbic", fr_gender="mp",
         pos=(0.3, 0.1, 0.85), color="#7f9cc0",
         # Small paramedian grey matter below the rostrum of the corpus callosum,
         # anterior to the thalamus and above the hypothalamus (a Papez/limbic
         # relay). Near the midline. Position is a guess: tune in a browser.
         radii=(0.2, 0.32, 0.22), seed=58, detail=5, noise=0.05),
    dict(base="hypothalamus", name="Hypothalamus", group="diencephalon",
         pos=(0.45, -0.45, 0.3), color="#c98ac9",
         # Small nucleus cluster below and anterior to the thalamus, hugging the
         # third ventricle (small x). Smooth (high detail, low noise).
         radii=(0.4, 0.4, 0.55), seed=52, detail=5, noise=0.05),
    dict(base="mammillary", name="Mammillary bodies", group="diencephalon", fr_gender="mp",
         pos=(0.35, -0.8, -0.2), color="#c6b06a",
         # Tiny paired bumps at the posterior base of the hypothalamus (the
         # Papez node between the fornix and the anterior thalamus). Small smooth
         # blob, kept just clear of the hypothalamus so they don't fuse. Position
         # is a guess: tune in a browser.
         radii=(0.18, 0.17, 0.2), seed=71, detail=4, noise=0.04),
    # --- Monoamine source nuclei (added for receptor expression) ---
    # The noradrenaline + dopamine source nuclei (raphe, the serotonin source, is
    # midline below). Small paired midbrain/pons nuclei tucked near the brainstem;
    # in their own `brainstem_nuclei` group so they don't take part in the
    # cortex/deep-nuclei jigsaw clipping. Positions are anatomical guesses: tune
    # in a browser.
    dict(base="locus_coeruleus", name="Locus coeruleus", group="brainstem_nuclei",
         pos=(0.3, -2.05, -1.15), color="#4a7fae",
         # "The blue spot": the brain's main noradrenaline source, in the dorsal
         # rostral pons. Tiny; coloured blue as a nod to its name. Carries the
         # alpha-2 autoreceptors. Sits inside/behind the brainstem at explode 0.
         radii=(0.12, 0.22, 0.14), seed=82, detail=4, noise=0.04),
    dict(base="vta", name="Ventral tegmental area", group="brainstem_nuclei",
         fr_gender="f",
         pos=(0.45, -1.35, -1.25), color="#6cab5d",
         # The midbrain dopamine source medial to the substantia nigra; origin of
         # the mesolimbic / mesocortical pathways (reward, D2 autoreceptors).
         # Small smooth blob, dopamine-green to echo the dopaminergic arrows.
         radii=(0.26, 0.2, 0.3), seed=83, detail=5, noise=0.05),
]

# Midline structures (emitted once, no hemisphere suffix)
MIDLINE: list[dict[str, Any]] = [
    dict(base="pituitary", name="Pituitary gland", group="diencephalon",
         pos=(0.0, -1.0, 0.35), color="#d2a06e",
         # Midline gland hanging below the hypothalamus on the infundibular stalk,
         # seated in the sella turcica. Tiny smooth blob; hides centrally at
         # explode 0 and is revealed by blowing out. Position is a guess: tune in
         # a browser.
         radii=(0.2, 0.22, 0.2), seed=72, detail=4, noise=0.04),
    dict(base="cerebellum", name="Cerebellum", group="hindbrain",
         pos=(0.0, -1.95, -3.3), color="#b07aa1",
         # Composite: two foliated hemispheres flanking a narrower central
         # vermis, the cerebellum's real "butterfly" form, instead of a single
         # wide ellipsoid. Each part stacks fine near-horizontal folia via a
         # strong y-frequency skew (aniso). Sits below/behind the occipital
         # lobes (under the tentorium) with the brainstem in front of it.
         shape=dict(
             type="composite",
             parts=[
                 # Left hemisphere.
                 dict(radii=[1.4, 1.05, 1.55], seed=31, detail=6, noise=0.13,
                      octaves=3, ridged=True, frequency=4.6,
                      aniso=[0.3, 4.4, 0.6], offset=[-1.05, 0.0, 0.0]),
                 # Right hemisphere.
                 dict(radii=[1.4, 1.05, 1.55], seed=41, detail=6, noise=0.13,
                      octaves=3, ridged=True, frequency=4.6,
                      aniso=[0.3, 4.4, 0.6], offset=[1.05, 0.0, 0.0]),
                 # Vermis: narrow, slightly taller central ridge joining them.
                 dict(radii=[0.55, 1.12, 1.5], seed=37, detail=5, noise=0.1,
                      octaves=3, ridged=True, frequency=5.4,
                      aniso=[0.25, 5.0, 0.5], offset=[0.0, 0.0, 0.05]),
             ],
         )),
    # The brainstem, cut into its three anatomical levels (midbrain -> pons ->
    # medulla) as separate midline structures instead of one swept tube, so each
    # is selectable and they come apart on explode. The three curve segments share
    # their boundary spine points (round-capped tubes that overlap a hair at the
    # joints), so at explode 0 they still read as one continuous tapering column
    # where the old single brainstem sat. Each carries its own pos at its centre so
    # it explodes radially on its own. Midline structures, never mirrored. (The pons
    # is the level the modeled corticopontine + pontocerebellar pathways actually
    # name, which is what justified splitting the column out, see "Drugs"/CLAUDE.md
    # granularity note.)
    dict(base="midbrain", name="Midbrain", group="hindbrain",
         pos=(0.0, -0.95, -0.66), color="#9c755f",
         # Top segment, continuous with the diencephalon/thalamus above it.
         shape=dict(
             type="curve",
             points=[
                 (0.0, 0.85, -0.09),  # top, under the thalamus
                 (0.0, 0.0, 0.0),     # mid
                 (0.0, -0.75, 0.11),  # tail, meeting the pons
             ],
             profile=[0.46, 0.55, 0.62],
             seed=32, noise=0.05, radial_segments=16, tubular_segments=44,
         )),
    dict(base="pons", name="Pons", group="hindbrain",
         pos=(0.0, -2.35, -0.45), color="#8c6a58",
         # Middle segment: the fullest, bulging anteriorly (+z); the pontine nuclei
         # relay cortex -> cerebellum (the corticopontine / pontocerebellar legs).
         shape=dict(
             type="curve",
             points=[
                 (0.0, 0.65, -0.10),  # head, meeting the midbrain
                 (0.0, 0.0, 0.0),     # belly, fullest + most anterior
                 (0.0, -0.65, -0.15), # tail, meeting the medulla
             ],
             profile=[0.62, 0.8, 0.55],
             seed=33, noise=0.05, radial_segments=16, tubular_segments=44,
         )),
    dict(base="medulla", name="Medulla", group="hindbrain",
         pos=(0.0, -3.8, -0.75), color="#7d5f4e",
         # Bottom segment, narrowing toward the spinal cord and drawing back (-z).
         shape=dict(
             type="curve",
             points=[
                 (0.0, 0.8, 0.15),    # head, meeting the pons
                 (0.0, 0.0, 0.0),     # mid
                 (0.0, -0.75, -0.10), # tail, toward the cord
             ],
             profile=[0.55, 0.44, 0.34],
             seed=34, noise=0.05, radial_segments=16, tubular_segments=44,
         )),
    dict(base="raphe", name="Raphe nuclei", group="brainstem_nuclei", fr_gender="mp",
         pos=(0.0, -1.9, -0.95), color="#b98ac9",
         # The brain's serotonin source: a midline column of nuclei running the
         # length of the brainstem. Modeled as a slim vertical blob hugging the
         # midline (emitted once, never mirrored). Carries the 5-HT1A
         # somatodendritic autoreceptors. Position/size are a guess: tune in a
         # browser.
         radii=(0.12, 0.55, 0.2), seed=81, detail=5, noise=0.05),
]

# Wikipedia article per structure, keyed by ``base`` id (so both hemispheres of a
# paired region share the one article, written once here). A small registry like
# SOURCES below: the generator attaches the URL to each structure record
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
SOURCES: dict[str, dict[str, str]] = {
    "kemp_powell1971": {
        "citation": "Kemp JM, Powell TPS (1971). The cortico-striate projection "
                    "in the monkey. Brain 94(3):525-546.",
        "url": "TODO",
    },
    "alexander1986": {
        "citation": "Alexander GE, DeLong MR, Strick PL (1986). Parallel "
                    "organization of functionally segregated circuits linking "
                    "basal ganglia and cortex. Annu Rev Neurosci 9:357-381.",
        "url": "TODO",
    },
    "albin1989": {
        "citation": "Albin RL, Young AB, Penney JB (1989). The functional anatomy "
                    "of basal ganglia disorders. Trends Neurosci 12(10):366-375.",
        "url": "TODO",
    },
    "delong1990": {
        "citation": "DeLong MR (1990). Primate models of movement disorders of "
                    "basal ganglia origin. Trends Neurosci 13(7):281-285.",
        "url": "TODO",
    },
    "parent1995": {
        "citation": "Parent A, Hazrati LN (1995). Functional anatomy of the basal "
                    "ganglia. Brain Res Rev 20(1):91-154.",
        "url": "TODO",
    },
    "smith1998": {
        "citation": "Smith Y, Bevan MD, Shink E, Bolam JP (1998). Microcircuitry "
                    "of the direct and indirect pathways of the basal ganglia. "
                    "Neuroscience 86(2):353-387.",
        "url": "TODO",
    },
    "nambu2002": {
        "citation": "Nambu A, Tokuno H, Takada M (2002). Functional significance "
                    "of the cortico-subthalamo-pallidal 'hyperdirect' pathway. "
                    "Neurosci Res 43(2):111-117.",
        "url": "TODO",
    },
    "middleton2000": {
        "citation": "Middleton FA, Strick PL (2000). Basal ganglia and cerebellar "
                    "loops: motor and cognitive circuits. Brain Res Rev "
                    "31(2-3):236-250.",
        "url": "TODO",
    },
    "aboitiz1992": {
        "citation": "Aboitiz F, Scheibel AB, Fisher RS, Zaidel E (1992). Fiber "
                    "composition of the human corpus callosum. Brain Res "
                    "598(1-2):143-153.",
        "url": "TODO",
    },
    "schmahmann2006": {
        "citation": "Schmahmann JD, Pandya DN (2006). Fiber Pathways of the "
                    "Brain. Oxford University Press.",
        "url": "TODO",
    },
    "papez1937": {
        "citation": "Papez JW (1937). A proposed mechanism of emotion. Arch "
                    "Neurol Psychiatry 38(4):725-743.",
        "url": "TODO",
    },
    "price1990": {
        "citation": "Price JL (1990). Olfactory system. In: Paxinos G (ed), The "
                    "Human Nervous System. Academic Press, pp. 979-1001.",
        "url": "TODO",
    },
    "dutar1995": {
        "citation": "Dutar P, Bassant MH, Senut MC, Lamour Y (1995). The "
                    "septohippocampal pathway: structure and function. Physiol "
                    "Rev 75(2):393-427.",
        "url": "TODO",
    },
    "swanson_sawchenko1983": {
        "citation": "Swanson LW, Sawchenko PE (1983). Hypothalamic integration: "
                    "organization of the paraventricular and supraoptic nuclei. "
                    "Annu Rev Neurosci 6:269-324.",
        "url": "TODO",
    },
    "haber2010": {
        "citation": "Haber SN, Knutson B (2010). The reward circuit: linking "
                    "primate anatomy and human imaging. Neuropsychopharmacology "
                    "35(1):4-26.",
        "url": "TODO",
    },
    "crick_koch2005": {
        "citation": "Crick FC, Koch C (2005). What is the function of the "
                    "claustrum? Philos Trans R Soc Lond B Biol Sci "
                    "360(1458):1271-1279.",
        "url": "TODO",
    },
    "menon_uddin2010": {
        "citation": "Menon V, Uddin LQ (2010). Saliency, switching, attention "
                    "and control: a network model of insula function. Brain "
                    "Struct Funct 214(5-6):655-667.",
        "url": "TODO",
    },
    "azmitia_segal1978": {
        "citation": "Azmitia EC, Segal M (1978). An autoradiographic analysis of "
                    "the differential ascending projections of the dorsal and "
                    "median raphe nuclei in the rat. J Comp Neurol 179(3):641-668.",
        "url": "TODO",
    },
    "foote1983": {
        "citation": "Foote SL, Bloom FE, Aston-Jones G (1983). Nucleus locus "
                    "coeruleus: new evidence of anatomical and physiological "
                    "specificity. Physiol Rev 63(3):844-914.",
        "url": "TODO",
    },
    "bjorklund_dunnett2007": {
        "citation": "Bjorklund A, Dunnett SB (2007). Dopamine neuron systems in "
                    "the brain: an update. Trends Neurosci 30(5):194-202.",
        "url": "TODO",
    },
    "kandel_principles": {
        "citation": "Kandel ER, Koester JD, Mack SH, Siegelbaum SA (eds) (2021). "
                    "Principles of Neural Science, 6th ed. McGraw-Hill.",
        "url": "TODO",
    },
}

# Directed neuron projections drawn as arrows. Each entry is a connection with
# metadata so the viewer can show what the pathway is and what supports it:
#   from, to        : structure ids (e.g. "putamen_R"); the arrow points from->to
#   kind            : functional/transmitter class, selects the arrow color
#                     (key of PROJECTION_COLORS in js/arrows.js + the legend)
#   neurotransmitter: the specific transmitter molecule (Glutamate/GABA/Dopamine)
#   label           : short pathway name
#   description     : one-line plain-language summary (shown in the info panel)
#   sources         : list of SOURCES keys backing the connection (expanded to
#                     full citations in the emitted data)
#   bidirectional   : optional; True draws a cone at BOTH ends (reciprocal /
#                     commissural pathways like the corpus callosum)
#   symmetric       : optional generator hint (default True); see below
#
# Bilateral by default: each entry is auto-mirrored to the left hemisphere (``_R``
# <-> ``_L`` on both endpoints, midline endpoints kept), so a symmetric pathway is
# defined once on the right. Set ``"symmetric": False`` for a pathway that already
# spans both sides (e.g. a commissure with explicit _L and _R endpoints) so it is
# not mirrored into a duplicate. ``symmetric`` is stripped from the emitted data.
PROJECTIONS: list[dict[str, Any]] = [
    # --- Corticostriatal input (glutamate): cortex drives the striatum ---
    dict(**{"from": "frontal_R", "to": "putamen_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (motor)",
         description="Sensorimotor frontal cortex drives the putamen, the motor "
                     "input nucleus of the basal ganglia.",
         sources=["alexander1986", "kemp_powell1971"]),
    dict(**{"from": "frontal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (associative)",
         description="Prefrontal cortex drives the caudate (associative striatum).",
         sources=["alexander1986", "kemp_powell1971"]),
    dict(**{"from": "parietal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (parietal)",
         description="Posterior parietal association cortex projects to the caudate.",
         sources=["kemp_powell1971"]),
    dict(**{"from": "temporal_R", "to": "caudate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticostriatal (temporal)",
         description="Temporal association cortex projects to the striatum.",
         sources=["kemp_powell1971"]),
    # --- Hyperdirect (glutamate): cortex excites the STN directly ---
    dict(**{"from": "frontal_R", "to": "subthalamic_nucleus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Hyperdirect (corticosubthalamic)",
         description="Cortex excites the subthalamic nucleus directly, the fast "
                     "'hyperdirect' brake on movement.",
         sources=["nambu2002"]),
    # --- Direct pathway (GABA): striatum inhibits the output nuclei ---
    dict(**{"from": "putamen_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatopallidal (direct)",
         description="Direct-pathway striatal neurons inhibit the internal "
                     "pallidum, releasing (disinhibiting) the thalamus.",
         sources=["albin1989", "smith1998"]),
    dict(**{"from": "caudate_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatopallidal (direct)",
         description="Caudate direct-pathway output to the internal pallidum.",
         sources=["albin1989", "smith1998"]),
    dict(**{"from": "putamen_R", "to": "substantia_nigra_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatonigral (direct)",
         description="Direct-pathway striatal output to the substantia nigra "
                     "pars reticulata.",
         sources=["albin1989", "parent1995"]),
    dict(**{"from": "caudate_R", "to": "substantia_nigra_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Striatonigral (direct)",
         description="Caudate direct-pathway output to the substantia nigra.",
         sources=["albin1989", "parent1995"]),
    # --- Indirect pathway (GABA out, glutamate back via STN) ---
    dict(**{"from": "globus_pallidus_R", "to": "subthalamic_nucleus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Pallidosubthalamic (indirect)",
         description="External pallidum inhibits the STN in the indirect pathway.",
         sources=["albin1989", "parent1995"]),
    dict(**{"from": "subthalamic_nucleus_R", "to": "globus_pallidus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Subthalamopallidal",
         description="The STN excites the pallidum, amplifying basal-ganglia "
                     "output (indirect/hyperdirect pathways).",
         sources=["albin1989", "parent1995"]),
    # --- Dopaminergic modulation (nigrostriatal) ---
    dict(**{"from": "substantia_nigra_R", "to": "putamen_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Nigrostriatal",
         description="Substantia nigra pars compacta dopamine sets the balance "
                     "between the direct and indirect striatal pathways.",
         sources=["delong1990", "parent1995"]),
    dict(**{"from": "substantia_nigra_R", "to": "caudate_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Nigrostriatal",
         description="Dopaminergic modulation of the caudate.",
         sources=["delong1990", "parent1995"]),
    # --- Basal-ganglia output to the thalamus (GABA) ---
    dict(**{"from": "globus_pallidus_R", "to": "thalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Pallidothalamic",
         description="The internal pallidum tonically inhibits the motor "
                     "thalamus, the output gate of the loop.",
         sources=["alexander1986", "parent1995"]),
    dict(**{"from": "substantia_nigra_R", "to": "thalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Nigrothalamic",
         description="Substantia nigra pars reticulata inhibitory output to the "
                     "thalamus.",
         sources=["parent1995"]),
    # --- Thalamocortical closure + sensory corticothalamic (glutamate) ---
    dict(**{"from": "thalamus_R", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Thalamocortical",
         description="Motor thalamus excites frontal cortex, closing the "
                     "cortico-basal-ganglia-thalamo-cortical loop.",
         sources=["alexander1986"]),
    dict(**{"from": "occipital_R", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticothalamic (visual)",
         description="Occipital (visual) cortex reciprocally connects with the "
                     "thalamus (pulvinar / lateral geniculate).",
         sources=["schmahmann2006"]),
    # --- Cortico-ponto-cerebellar and cerebellar output ---
    dict(**{"from": "frontal_R", "to": "pons"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corticopontine",
         description="Cortex projects to the pontine nuclei (pons), the "
                     "first leg of the cortico-ponto-cerebellar route.",
         sources=["middleton2000", "schmahmann2006"]),
    dict(**{"from": "pons", "to": "cerebellum"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Pontocerebellar (mossy fibers)",
         description="Pontine nuclei send mossy fibers to the cerebellar cortex.",
         sources=["middleton2000"]),
    dict(**{"from": "cerebellum", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Cerebellothalamic (dentatothalamic)",
         description="Deep cerebellar nuclei drive the motor thalamus, feeding "
                     "the cerebellar loop back to cortex.",
         sources=["middleton2000", "schmahmann2006"]),
    # --- Limbic (Papez) circuit ---
    dict(**{"from": "temporal_R", "to": "hippocampus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Perforant path",
         description="Entorhinal (medial temporal) cortex drives the hippocampus "
                     "via the perforant path.",
         sources=["schmahmann2006"]),
    dict(**{"from": "hippocampus_R", "to": "fornix_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Fornix (hippocampal output)",
         description="The major hippocampal output gathers into the fornix, the "
                     "great arching tract of the Papez circuit.",
         sources=["papez1937", "schmahmann2006"]),
    dict(**{"from": "fornix_R", "to": "mammillary_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Postcommissural fornix",
         description="The fornix carries hippocampal output forward to the "
                     "mammillary bodies (Papez circuit).",
         sources=["papez1937", "schmahmann2006"]),
    dict(**{"from": "mammillary_R", "to": "thalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Mammillothalamic tract",
         description="Mammillary bodies project to the anterior thalamic nuclei, "
                     "continuing the Papez circuit.",
         sources=["papez1937"]),
    dict(**{"from": "thalamus_R", "to": "cingulate_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Anterior thalamocingulate",
         description="The anterior thalamic nuclei project to the cingulate "
                     "gyrus, the next leg of the Papez circuit.",
         sources=["papez1937"]),
    dict(**{"from": "cingulate_R", "to": "hippocampus_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Cingulum (to hippocampus)",
         description="The cingulate gyrus projects back to the hippocampus via "
                     "the cingulum, closing the Papez loop.",
         sources=["papez1937", "schmahmann2006"]),
    # --- Olfactory, amygdalar and septal limbic links ---
    dict(**{"from": "olfactory_bulb_R", "to": "amygdala_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Olfactory projection (to amygdala)",
         description="Mitral cells of the olfactory bulb project to the "
                     "corticomedial amygdala.",
         sources=["price1990"]),
    dict(**{"from": "olfactory_bulb_R", "to": "insula_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Olfactory projection (to olfactory cortex)",
         description="Bulbar output reaches the piriform / insular olfactory "
                     "cortex.",
         sources=["price1990"]),
    dict(**{"from": "amygdala_R", "to": "hypothalamus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Stria terminalis",
         description="The amygdala projects to the hypothalamus via the stria "
                     "terminalis, driving autonomic / endocrine responses.",
         sources=["schmahmann2006"]),
    dict(**{"from": "hippocampus_R", "to": "septal_nuclei_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Hippocamposeptal projection",
         description="Hippocampal fibers run in the precommissural fornix to the "
                     "septal nuclei.",
         sources=["dutar1995"]),
    dict(**{"from": "septal_nuclei_R", "to": "hippocampus_R"},
         kind="cholinergic", neurotransmitter="Acetylcholine",
         label="Septohippocampal pathway",
         description="Medial septal cholinergic neurons project to the "
                     "hippocampus, pacing the hippocampal theta rhythm.",
         sources=["dutar1995"]),
    # --- Ventral striatum (reward) and the neuroendocrine outflow ---
    dict(**{"from": "substantia_nigra_R", "to": "accumbens_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic dopamine pathway",
         description="Midbrain dopaminergic neurons (VTA / substantia nigra) "
                     "project to the nucleus accumbens, the reward hub.",
         sources=["haber2010"]),
    dict(**{"from": "accumbens_R", "to": "globus_pallidus_R"},
         kind="inhibitory", neurotransmitter="GABA",
         label="Accumbens to ventral pallidum",
         description="Nucleus accumbens medium spiny neurons project to the "
                     "(ventral) pallidum, the ventral-striatal output.",
         sources=["haber2010"]),
    dict(**{"from": "hypothalamus_R", "to": "pituitary"},
         kind="neuroendocrine", neurotransmitter="Releasing hormones",
         label="Hypothalamo-hypophyseal axis",
         description="Hypothalamic neurons drive the pituitary via the median "
                     "eminence / portal system and the posterior hypophyseal "
                     "tract.",
         sources=["swanson_sawchenko1983"]),
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
                     "prefrontal cortex, shaping mood and cognition.",
         sources=["azmitia_segal1978"]),
    dict(**{"from": "raphe", "to": "hippocampus_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (hippocampal)",
         description="Median raphe serotonin projects to the hippocampus.",
         sources=["azmitia_segal1978"]),
    dict(**{"from": "raphe", "to": "amygdala_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (amygdala)",
         description="Raphe serotonin modulates the amygdala, tuning emotional "
                     "reactivity.",
         sources=["azmitia_segal1978"]),
    dict(**{"from": "raphe", "to": "hypothalamus_R"},
         kind="serotonergic", neurotransmitter="Serotonin",
         label="Ascending serotonergic (hypothalamic)",
         description="Raphe serotonin projects to the hypothalamus, influencing "
                     "sleep, appetite and neuroendocrine rhythms.",
         sources=["azmitia_segal1978"]),
    dict(**{"from": "locus_coeruleus_R", "to": "frontal_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (prefrontal)",
         description="Locus coeruleus noradrenaline projects diffusely to the "
                     "cortex, driving arousal and attention.",
         sources=["foote1983"]),
    dict(**{"from": "locus_coeruleus_R", "to": "hippocampus_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (hippocampal)",
         description="Locus coeruleus noradrenaline projects to the hippocampus.",
         sources=["foote1983"]),
    dict(**{"from": "locus_coeruleus_R", "to": "amygdala_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (amygdala)",
         description="Locus coeruleus noradrenaline sharpens amygdala-dependent "
                     "emotional memory.",
         sources=["foote1983"]),
    dict(**{"from": "locus_coeruleus_R", "to": "thalamus_R"},
         kind="noradrenergic", neurotransmitter="Noradrenaline",
         label="Ascending noradrenergic (thalamic)",
         description="Locus coeruleus noradrenaline projects to the thalamus.",
         sources=["foote1983"]),
    dict(**{"from": "vta_R", "to": "accumbens_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic (VTA)",
         description="VTA dopamine projects to the nucleus accumbens, the core "
                     "of the reward pathway.",
         sources=["bjorklund_dunnett2007", "haber2010"]),
    dict(**{"from": "vta_R", "to": "frontal_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesocortical",
         description="VTA dopamine projects to the prefrontal cortex, supporting "
                     "motivation and executive control.",
         sources=["bjorklund_dunnett2007"]),
    dict(**{"from": "vta_R", "to": "amygdala_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic (amygdala)",
         description="VTA dopamine innervates the amygdala.",
         sources=["bjorklund_dunnett2007"]),
    dict(**{"from": "vta_R", "to": "hippocampus_R"},
         kind="dopaminergic", neurotransmitter="Dopamine",
         label="Mesolimbic (hippocampal)",
         description="VTA dopamine projects to the hippocampus, gating "
                     "reward-related memory.",
         sources=["bjorklund_dunnett2007"]),
    # --- Interhemispheric commissures (bidirectional, defined once across the
    #     midline so symmetric=False keeps them from mirroring into duplicates) ---
    dict(**{"from": "frontal_L", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (frontal)", bidirectional=True, symmetric=False,
         description="Homotopic callosal fibers linking the two frontal lobes.",
         sources=["aboitiz1992", "schmahmann2006"]),
    dict(**{"from": "parietal_L", "to": "parietal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (parietal)", bidirectional=True, symmetric=False,
         description="Homotopic callosal fibers linking the two parietal lobes.",
         sources=["aboitiz1992", "schmahmann2006"]),
    dict(**{"from": "occipital_L", "to": "occipital_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Corpus callosum (splenium / occipital)", bidirectional=True,
         symmetric=False,
         description="Splenial callosal fibers linking the two occipital lobes.",
         sources=["aboitiz1992", "schmahmann2006"]),
    dict(**{"from": "temporal_L", "to": "temporal_R"},
         kind="excitatory", neurotransmitter="Glutamate",
         label="Anterior commissure", bidirectional=True, symmetric=False,
         description="Older commissure linking the temporal lobes (and olfactory "
                     "structures).",
         sources=["schmahmann2006"]),
    # --- Plausible / speculative pathways (tentative=True) -------------------
    # Anatomically reasonable but less certain or more diffuse than the pathways
    # above. The viewer lists these in a separate, off-by-default legend section
    # and draws them as dotted arrows, so they read as "maybe" rather than fact.
    # ``tentative`` is carried through to the emitted projection record.
    dict(**{"from": "claustrum_R", "to": "frontal_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Claustro-frontal projection", bidirectional=True,
         description="Reciprocal claustro-cortical link with prefrontal cortex "
                     "(implicated in salience / attention).",
         sources=["crick_koch2005"]),
    dict(**{"from": "claustrum_R", "to": "insula_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Claustro-insular projection", bidirectional=True,
         description="The claustrum tightly interconnects with the adjacent "
                     "insular cortex.",
         sources=["crick_koch2005"]),
    dict(**{"from": "insula_R", "to": "cingulate_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Salience network link", bidirectional=True,
         description="The anterior insula and the cingulate co-activate as the "
                     "salience network.",
         sources=["menon_uddin2010"]),
    dict(**{"from": "amygdala_R", "to": "accumbens_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Basolateral amygdala to accumbens",
         description="Basolateral amygdala glutamatergic input to the ventral "
                     "striatum (motivational salience).",
         sources=["haber2010"]),
    dict(**{"from": "mammillary_R", "to": "hypothalamus_R"},
         kind="excitatory", neurotransmitter="Glutamate", tentative=True,
         label="Mammillary-hypothalamic link",
         description="The mammillary bodies sit within and connect to the "
                     "posterior hypothalamus.",
         sources=["schmahmann2006"]),
    dict(**{"from": "septal_nuclei_R", "to": "hypothalamus_R"},
         kind="inhibitory", neurotransmitter="GABA", tentative=True,
         label="Septohypothalamic projection",
         description="The septal nuclei project to the hypothalamus, a limbic-"
                     "autonomic relay.",
         sources=["swanson_sawchenko1983"]),
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
         description="The movement-promoting basal-ganglia loop: cortex excites "
                     "the striatum, which inhibits the GPi/SNr output, releasing "
                     "the thalamus to drive cortex.",
         description_fr="La boucle des noyaux gris centraux favorisant le "
                        "mouvement : le cortex active le striatum, qui inhibe la "
                        "sortie GPi/SNr, libérant le thalamus pour activer le "
                        "cortex.",
         sources=["alexander1986", "smith1998", "delong1990"],
         # Cortex -> striatum -> GPi/SNr -> thalamus -> cortex: the movement-
         # promoting basal-ganglia loop (plus the nigrostriatal dopamine input).
         structures=["frontal", "putamen", "globus_pallidus",
                     "substantia_nigra", "thalamus"]),
    dict(id="bg_indirect", name="Indirect pathway",
         description="The movement-suppressing loop, routed through the subthalamic "
                     "nucleus, which drives the GPi/SNr to clamp the thalamus.",
         description_fr="La boucle supprimant le mouvement, passant par le noyau "
                        "sous-thalamique, qui active le GPi/SNr pour brider le "
                        "thalamus.",
         sources=["albin1989", "smith1998", "nambu2002"],
         # The movement-suppressing loop, routing through the subthalamic nucleus
         # (and the cortico-subthalamic "hyperdirect" shortcut).
         structures=["frontal", "putamen", "globus_pallidus",
                     "subthalamic_nucleus", "thalamus"]),
    dict(id="nigrostriatal", name="Nigrostriatal (dopamine)",
         description="The dopaminergic projection from the substantia nigra to the "
                     "striatum whose loss causes Parkinson's disease.",
         description_fr="La projection dopaminergique de la substance noire vers le "
                        "striatum dont la perte cause la maladie de Parkinson.",
         sources=["bjorklund_dunnett2007", "alexander1986"],
         # The dopaminergic projection whose loss causes Parkinson's, with the
         # reciprocal striatonigral return.
         structures=["substantia_nigra", "putamen", "caudate"]),
    dict(id="cerebellar_motor", name="Cortico-cerebellar (motor)",
         description="The coordination loop: cortex to pons to cerebellum to "
                     "thalamus and back, tuning the timing of movement.",
         description_fr="La boucle de coordination : cortex vers pont vers cervelet "
                        "vers thalamus et retour, ajustant le timing du mouvement.",
         sources=["middleton2000"],
         # Cortex -> pons -> cerebellum -> thalamus -> cortex: the coordination
         # loop running through the pons and cerebellum.
         structures=["frontal", "pons", "cerebellum", "thalamus"]),
    dict(id="limbic_memory", name="Hippocampal / limbic (Papez)",
         description="The Papez circuit: the medial-temporal memory loop through "
                     "hippocampus, fornix, mammillary bodies, anterior thalamus "
                     "and cingulate.",
         description_fr="Le circuit de Papez : la boucle mnésique médio-temporale "
                        "par l'hippocampe, le fornix, les corps mammillaires, le "
                        "thalamus antérieur et le cingulum.",
         sources=["papez1937"],
         # The medial-temporal memory loop, now wired through the real fornix,
         # mammillary and cingulate nodes: temporal -> hippocampus -> fornix ->
         # mammillary -> (anterior) thalamus -> cingulate -> hippocampus.
         structures=["temporal", "hippocampus", "fornix", "mammillary",
                     "thalamus", "cingulate"]),
    dict(id="commissures", name="Commissures (interhemispheric)",
         description="The interhemispheric bridges (corpus callosum + anterior "
                     "commissure) linking matching cortical areas across the "
                     "midline.",
         description_fr="Les ponts interhémisphériques (corps calleux + commissure "
                        "antérieure) reliant les aires corticales homologues à "
                        "travers la ligne médiane.",
         sources=["aboitiz1992", "schmahmann2006"],
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
# and ``sources`` (SOURCES keys). The member pathways are NOT listed here: the
# viewer derives them (the projections whose kind / sign matches ``key``), exactly
# as a circuit derives its arrows, so a group never duplicates the projection list.
# ``classification_provenance`` grades the grouping/description (LLM-authored).
PROJECTION_GROUPS: list[dict[str, Any]] = [
    # --- per-neurotransmitter (mode="kind"); name = the transmitter molecule -----
    dict(mode="kind", key="excitatory", name="Glutamate",
         description="The brain's main excitatory transmitter: glutamatergic "
                     "projections drive their targets, including the "
                     "corticostriatal and thalamocortical pathways.",
         description_fr="Le principal neurotransmetteur excitateur du cerveau : les "
                        "projections glutamatergiques activent leurs cibles, dont "
                        "les voies cortico-striées et thalamo-corticales.",
         wikipedia="https://en.wikipedia.org/wiki/Glutamate_(neurotransmitter)",
         sources=["kandel_principles"]),
    dict(mode="kind", key="inhibitory", name="GABA",
         description="The brain's main inhibitory transmitter: GABAergic "
                     "projections suppress their targets, including the striatal "
                     "output of the basal ganglia.",
         description_fr="Le principal neurotransmetteur inhibiteur du cerveau : les "
                        "projections GABAergiques freinent leurs cibles, dont la "
                        "sortie striatale des noyaux gris centraux.",
         wikipedia="https://en.wikipedia.org/wiki/Gamma-Aminobutyric_acid",
         sources=["kandel_principles"]),
    dict(mode="kind", key="dopaminergic", name="Dopamine",
         description="Dopaminergic projections from the midbrain (substantia "
                     "nigra, VTA) modulate movement, motivation and reward.",
         description_fr="Les projections dopaminergiques du mésencéphale (substance "
                        "noire, ATV) modulent le mouvement, la motivation et la "
                        "récompense.",
         wikipedia="https://en.wikipedia.org/wiki/Dopaminergic_pathways",
         sources=["bjorklund_dunnett2007", "kandel_principles"]),
    dict(mode="kind", key="cholinergic", name="Acetylcholine",
         description="Cholinergic projections modulate arousal, attention and "
                     "memory across the cortex and hippocampus.",
         description_fr="Les projections cholinergiques modulent l'éveil, "
                        "l'attention et la mémoire dans le cortex et l'hippocampe.",
         wikipedia="https://en.wikipedia.org/wiki/Cholinergic",
         sources=["dutar1995", "kandel_principles"]),
    dict(mode="kind", key="neuroendocrine", name="Releasing hormones",
         description="Hypothalamic neuroendocrine projections release hormones "
                     "that control the pituitary and the body's endocrine axes.",
         description_fr="Les projections neuroendocrines de l'hypothalamus libèrent "
                        "des hormones qui contrôlent l'hypophyse et les axes "
                        "endocriniens.",
         wikipedia="https://en.wikipedia.org/wiki/Releasing_hormone",
         sources=["swanson_sawchenko1983", "kandel_principles"]),
    dict(mode="kind", key="serotonergic", name="Serotonin",
         description="Serotonergic projections from the raphe nuclei diffusely "
                     "modulate mood, sleep and appetite throughout the brain.",
         description_fr="Les projections sérotoninergiques des noyaux du raphé "
                        "modulent diffusément l'humeur, le sommeil et l'appétit "
                        "dans tout le cerveau.",
         wikipedia="https://en.wikipedia.org/wiki/Serotonergic",
         sources=["azmitia_segal1978", "kandel_principles"]),
    dict(mode="kind", key="noradrenergic", name="Noradrenaline",
         description="Noradrenergic projections from the locus coeruleus modulate "
                     "arousal, vigilance and the stress response.",
         description_fr="Les projections noradrénergiques du locus coeruleus "
                        "modulent l'éveil, la vigilance et la réponse au stress.",
         wikipedia="https://en.wikipedia.org/wiki/Norepinephrine",
         sources=["foote1983", "kandel_principles"]),
    # --- per-sign (mode="sign"); name = the SIGN_LABELS heading ------------------
    dict(mode="sign", key="excitatory", name="Excitatory",
         description="Excitatory pathways depolarize their target, making it more "
                     "likely to fire (mainly glutamatergic).",
         description_fr="Les voies excitatrices dépolarisent leur cible, la rendant "
                        "plus susceptible de décharger (surtout glutamatergiques).",
         wikipedia="https://en.wikipedia.org/wiki/Excitatory_postsynaptic_potential",
         sources=["kandel_principles"]),
    dict(mode="sign", key="inhibitory", name="Inhibitory",
         description="Inhibitory pathways hyperpolarize their target, making it "
                     "less likely to fire (mainly GABAergic).",
         description_fr="Les voies inhibitrices hyperpolarisent leur cible, la "
                        "rendant moins susceptible de décharger (surtout "
                        "GABAergiques).",
         wikipedia="https://en.wikipedia.org/wiki/Inhibitory_postsynaptic_potential",
         sources=["kandel_principles"]),
    dict(mode="sign", key="modulatory", name="Modulatory",
         description="Modulatory pathways (the monoamines and acetylcholine) tune "
                     "the gain and excitability of their targets rather than "
                     "directly exciting or inhibiting them.",
         description_fr="Les voies modulatrices (monoamines et acétylcholine) "
                        "ajustent le gain et l'excitabilité de leurs cibles plutôt "
                        "que de les exciter ou inhiber directement.",
         wikipedia="https://en.wikipedia.org/wiki/Neuromodulation",
         sources=["kandel_principles"]),
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
RECEPTORS: list[dict[str, Any]] = [
    # --- Adrenergic (noradrenaline); all GPCRs ---------------------------------
    dict(id="alpha1a", name="α1A", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "cerebellum", "midbrain", "pons", "medulla", "thalamus", "hypothalamus"],
         description="Gq-coupled excitatory NA receptor; modulates cortical, "
                     "hippocampal and brainstem excitability.",
         description_fr="Récepteur excitateur de la noradrénaline couplé à Gq ; "
                        "module l'excitabilité corticale, hippocampique et du "
                        "tronc cérébral.",
         wikipedia="https://en.wikipedia.org/wiki/Alpha-1_adrenergic_receptor"),
    dict(id="alpha1b", name="α1B", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "cerebellum", "midbrain", "pons", "medulla", "thalamus"],
         description="Gq-coupled excitatory NA receptor; postsynaptic, widely "
                     "expressed across cortex and subcortex.",
         description_fr="Récepteur excitateur de la noradrénaline couplé à Gq ; "
                        "postsynaptique, largement exprimé dans le cortex et les "
                        "régions sous-corticales.",
         wikipedia="https://en.wikipedia.org/wiki/Alpha-1_adrenergic_receptor"),
    # Stub: α1C is obsolete (found identical to α1A; no distinct human subtype).
    dict(id="alpha1c", name="α1C", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Alpha-1_adrenergic_receptor"),
    dict(id="alpha1d", name="α1D", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "cerebellum", "midbrain", "pons", "medulla", "thalamus"],
         description="Gq-coupled excitatory NA receptor; postsynaptic, in cortex, "
                     "hippocampus and brainstem.",
         description_fr="Récepteur excitateur de la noradrénaline couplé à Gq ; "
                        "postsynaptique, dans le cortex, l'hippocampe et le tronc "
                        "cérébral.",
         wikipedia="https://en.wikipedia.org/wiki/Alpha-1_adrenergic_receptor"),
    dict(id="alpha2a", name="α2A", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["locus_coeruleus", "midbrain", "pons", "medulla", "hypothalamus", "hippocampus",
                    "frontal", "parietal", "temporal", "occipital", "cerebellum"],
         description="Gi-coupled inhibitory NA receptor; presynaptic autoreceptor "
                     "in locus coeruleus, postsynaptic in prefrontal cortex.",
         description_fr="Récepteur inhibiteur de la noradrénaline couplé à Gi ; "
                        "autorécepteur présynaptique du locus cœruleus, "
                        "postsynaptique dans le cortex préfrontal.",
         wikipedia="https://en.wikipedia.org/wiki/Alpha-2_adrenergic_receptor"),
    dict(id="alpha2b", name="α2B", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic",
         locations=["thalamus", "hippocampus", "cerebellum"],
         description="Gi-coupled inhibitory NA receptor; limited CNS expression in "
                     "thalamus, hippocampus and cerebellar Purkinje cells.",
         description_fr="Récepteur inhibiteur de la noradrénaline couplé à Gi ; "
                        "expression limitée au thalamus, à l'hippocampe et aux "
                        "cellules de Purkinje cérébelleuses.",
         wikipedia="https://en.wikipedia.org/wiki/Alpha-2_adrenergic_receptor"),
    dict(id="alpha2c", name="α2C", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["thalamus", "amygdala", "hippocampus", "frontal", "parietal",
                    "temporal", "occipital", "caudate", "putamen",
                    "globus_pallidus", "substantia_nigra", "vta", "midbrain", "pons", "medulla"],
         description="Gi-coupled inhibitory NA receptor; widespread in basal "
                     "ganglia, amygdala, hippocampus, cortex and midbrain.",
         description_fr="Récepteur inhibiteur de la noradrénaline couplé à Gi ; "
                        "répandu dans les noyaux gris centraux, l'amygdale, "
                        "l'hippocampe, le cortex et le mésencéphale.",
         wikipedia="https://en.wikipedia.org/wiki/Alpha-2_adrenergic_receptor"),
    # Stub: α2D is a rodent/non-human ortholog of human α2A (no human α2D).
    dict(id="alpha2d", name="α2D", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Alpha-2_adrenergic_receptor"),
    dict(id="beta1", name="β1", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "cingulate", "accumbens"],
         description="Gs-coupled excitatory NA receptor; in cortex, cingulate and "
                     "accumbens; modulates fear and circadian timing.",
         description_fr="Récepteur excitateur de la noradrénaline couplé à Gs ; "
                        "dans le cortex, le cingulaire et l'accumbens ; module la "
                        "peur et le rythme circadien.",
         wikipedia="https://en.wikipedia.org/wiki/Beta-1_adrenergic_receptor"),
    dict(id="beta2", name="β2", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["cerebellum", "frontal", "parietal", "temporal", "occipital",
                    "hippocampus"],
         description="Gs-coupled excitatory NA receptor; in cerebellum, cortex and "
                     "hippocampus.",
         description_fr="Récepteur excitateur de la noradrénaline couplé à Gs ; "
                        "dans le cervelet, le cortex et l'hippocampe.",
         wikipedia="https://en.wikipedia.org/wiki/Beta-2_adrenergic_receptor"),
    # Stub: β3 is predominantly peripheral (adipose/bladder); no brain role.
    dict(id="beta3", name="β3", family="adrenergic",
         neurotransmitter="Noradrenaline", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Beta-3_adrenergic_receptor"),

    # --- Cholinergic (acetylcholine) -------------------------------------------
    dict(id="m1", name="M1", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "cingulate",
                    "hippocampus", "accumbens"],
         description="Gq postsynaptic muscarinic receptor; slow EPSP, drives "
                     "cortical/hippocampal cognition and memory.",
         description_fr="Récepteur muscarinique Gq postsynaptique ; PPSE lent, "
                        "soutient la cognition et la mémoire corticale et "
                        "hippocampique.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M1"),
    dict(id="m2", name="M2", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["olfactory_bulb", "midbrain", "pons", "medulla", "frontal", "parietal",
                    "temporal", "occipital", "hippocampus"],
         description="Gi-coupled presynaptic autoreceptor; restrains acetylcholine "
                     "release (also slows the heart).",
         description_fr="Autorécepteur présynaptique couplé à Gi ; freine la "
                        "libération d'acétylcholine (ralentit aussi le cœur).",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M2"),
    dict(id="m3", name="M3", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["hypothalamus", "midbrain", "pons", "medulla", "thalamus", "frontal", "temporal",
                    "occipital"],
         description="Gq postsynaptic muscarinic receptor; acts in hypothalamus "
                     "and brainstem autonomic centres.",
         description_fr="Récepteur muscarinique Gq postsynaptique ; agit dans "
                        "l'hypothalamus et les centres autonomes du tronc "
                        "cérébral.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M3"),
    dict(id="m4", name="M4", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["caudate", "putamen", "accumbens", "frontal", "cingulate"],
         description="Gi-coupled receptor enriched in striatum; presynaptic "
                     "autoreceptor that brakes D1 dopamine drive.",
         description_fr="Récepteur couplé à Gi enrichi dans le striatum ; "
                        "autorécepteur présynaptique freinant l'activité "
                        "dopaminergique D1.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M4"),
    dict(id="m5", name="M5", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["substantia_nigra", "vta", "hypothalamus", "frontal",
                    "amygdala", "hippocampus", "mammillary"],
         description="Gq receptor on substantia nigra/VTA dopamine neurons; "
                     "facilitates dopamine release.",
         description_fr="Récepteur Gq sur les neurones dopaminergiques de la "
                        "substance noire et de l'ATV ; facilite la libération de "
                        "dopamine.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M5"),
    # Stub: muscle-type nAChR sits at the neuromuscular junction (peripheral).
    dict(id="nachr_muscle", name="Muscle nAChR", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor"),
    dict(id="nachr_a4b2", name="Neuronal α4β2 nAChR", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="ionotropic",
         sign="excitatory", synaptic="both",
         locations=["frontal", "parietal", "temporal", "occipital", "thalamus",
                    "vta", "substantia_nigra", "accumbens", "caudate", "putamen"],
         description="High-affinity nicotine receptor; cation channel on dopamine "
                     "terminals, drives nicotine addiction.",
         description_fr="Récepteur nicotinique à haute affinité ; canal cationique "
                        "sur les terminaisons dopaminergiques, moteur de "
                        "l'addiction à la nicotine.",
         wikipedia="https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor"),
    dict(id="nachr_a7", name="Neuronal α7 nAChR", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="ionotropic",
         sign="excitatory", synaptic="both",
         locations=["hippocampus", "frontal", "parietal", "temporal", "occipital",
                    "thalamus", "amygdala"],
         description="Homomeric Ca2+-permeable cation channel; "
                     "α-bungarotoxin-sensitive, implicated in schizophrenia.",
         description_fr="Canal cationique homomérique perméable au Ca2+ ; sensible "
                        "à l'α-bungarotoxine, impliqué dans la schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor"),

    # --- Dopaminergic ----------------------------------------------------------
    dict(id="d1", name="D1", family="dopaminergic",
         neurotransmitter="Dopamine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["caudate", "putamen", "accumbens", "olfactory_bulb", "frontal",
                    "parietal", "temporal", "occipital", "amygdala",
                    "septal_nuclei", "thalamus", "hypothalamus", "cingulate"],
         description="Most abundant dopamine receptor; Gs-coupled, excitatory; "
                     "drives the striatal direct pathway.",
         description_fr="Récepteur dopaminergique le plus abondant ; couplé à Gs, "
                        "excitateur ; active la voie directe striatale.",
         wikipedia="https://en.wikipedia.org/wiki/Dopamine_receptor_D1"),
    dict(id="d2", name="D2", family="dopaminergic",
         neurotransmitter="Dopamine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["putamen", "caudate", "accumbens", "olfactory_bulb",
                    "substantia_nigra", "vta", "pituitary", "frontal"],
         description="Gi-coupled, inhibitory; drives the indirect pathway and acts "
                     "as a presynaptic autoreceptor; antipsychotic target.",
         description_fr="Couplé à Gi, inhibiteur ; active la voie indirecte et "
                        "agit comme autorécepteur présynaptique ; cible des "
                        "antipsychotiques.",
         wikipedia="https://en.wikipedia.org/wiki/Dopamine_receptor_D2"),
    dict(id="d3", name="D3", family="dopaminergic",
         neurotransmitter="Dopamine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["accumbens", "olfactory_bulb", "putamen", "caudate", "frontal",
                    "hypothalamus", "hippocampus"],
         description="D2-like, Gi-coupled, inhibitory; concentrated in limbic "
                     "ventral striatum, highest dopamine affinity.",
         description_fr="De type D2, couplé à Gi, inhibiteur ; concentré dans le "
                        "striatum ventral limbique, plus forte affinité pour la "
                        "dopamine.",
         wikipedia="https://en.wikipedia.org/wiki/Dopamine_receptor_D3"),
    dict(id="d4", name="D4", family="dopaminergic",
         neurotransmitter="Dopamine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic",
         locations=["frontal", "amygdala", "hypothalamus", "hippocampus",
                    "occipital", "cerebellum"],
         description="D2-like, Gi-coupled, inhibitory; enriched in frontal cortex; "
                     "linked to attention and ADHD.",
         description_fr="De type D2, couplé à Gi, inhibiteur ; enrichi dans le "
                        "cortex frontal ; lié à l'attention et au TDAH.",
         wikipedia="https://en.wikipedia.org/wiki/Dopamine_receptor_D4"),
    dict(id="d5", name="D5", family="dopaminergic",
         neurotransmitter="Dopamine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["amygdala", "frontal", "parietal", "temporal", "occipital",
                    "hippocampus", "caudate", "putamen", "thalamus", "hypothalamus",
                    "septal_nuclei", "cerebellum", "midbrain", "pons", "medulla"],
         description="D1-like, Gs-coupled, excitatory; low-abundance but "
                     "widespread; high constitutive activity, prominent in "
                     "hippocampus.",
         description_fr="De type D1, couplé à Gs, excitateur ; peu abondant mais "
                        "répandu ; forte activité constitutive, marqué dans "
                        "l'hippocampe.",
         wikipedia="https://en.wikipedia.org/wiki/Dopamine_receptor_D5"),

    # --- GABAergic -------------------------------------------------------------
    dict(id="gaba_a", name="GABA-A", family="gabaergic",
         neurotransmitter="GABA", receptor_class="ionotropic",
         sign="inhibitory", synaptic="postsynaptic", locations="ALL",
         description="Ubiquitous Cl- channel; target of benzodiazepines, alcohol, "
                     "anaesthetics, neurosteroids; anxiety/epilepsy/insomnia.",
         description_fr="Canal Cl- ubiquitaire ; cible des benzodiazépines, de "
                        "l'alcool, des anesthésiques, des neurostéroïdes ; "
                        "anxiété/épilepsie/insomnie.",
         wikipedia="https://en.wikipedia.org/wiki/GABAA_receptor"),
    dict(id="gaba_b", name="GABA-B", family="gabaergic",
         neurotransmitter="GABA", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both", locations="ALL",
         description="Widespread Gi/o GPCR; opens K+ channels, curbs Ca2+ and "
                     "transmitter release; baclofen target.",
         description_fr="RCPG Gi/o répandu ; ouvre les canaux K+, réduit le Ca2+ "
                        "et la libération de neurotransmetteur ; cible du "
                        "baclofène.",
         wikipedia="https://en.wikipedia.org/wiki/GABAB_receptor"),
    # Stub: GABA-A-rho (formerly "GABA-C") is predominantly retinal.
    dict(id="gaba_a_rho", name="GABA-A-ρ", family="gabaergic",
         neurotransmitter="GABA", receptor_class="ionotropic",
         sign="inhibitory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/GABAA-rho_receptor"),

    # --- Glutamatergic ---------------------------------------------------------
    dict(id="nmda", name="NMDA", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic", locations="ALL",
         description="Coincidence-detecting Ca2+ channel driving LTP/memory; "
                     "ketamine/memantine target, schizophrenia hypofunction.",
         description_fr="Canal Ca2+ détecteur de coïncidence pilotant la "
                        "LTP/mémoire ; cible kétamine/mémantine, hypofonction dans "
                        "la schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/NMDA_receptor"),
    dict(id="ampa", name="AMPA", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic", locations="ALL",
         description="Fast cation channel mediating most fast excitatory "
                     "transmission; its trafficking underlies synaptic plasticity.",
         description_fr="Canal cationique rapide assurant l'essentiel de la "
                        "transmission excitatrice rapide ; son trafic sous-tend la "
                        "plasticité.",
         wikipedia="https://en.wikipedia.org/wiki/AMPA_receptor"),
    dict(id="kainate", name="Kainate", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="ionotropic",
         sign="excitatory", synaptic="both",
         locations=["hippocampus", "frontal", "parietal", "temporal", "occipital",
                    "amygdala", "cerebellum"],
         description="Cation channel with more limited distribution; postsynaptic "
                     "excitation plus presynaptic modulation of release.",
         description_fr="Canal cationique à distribution plus limitée ; excitation "
                        "postsynaptique et modulation présynaptique de la "
                        "libération.",
         wikipedia="https://en.wikipedia.org/wiki/Kainate_receptor"),
    dict(id="mglur1", name="mGluR1", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["cerebellum", "hippocampus", "thalamus", "frontal", "parietal",
                    "temporal", "occipital"],
         description="Group I Gq receptor; postsynaptic excitation, potentiates "
                     "NMDA currents; strong in cerebellar Purkinje cells.",
         description_fr="Récepteur Gq du groupe I ; excitation postsynaptique, "
                        "potentialise les courants NMDA ; abondant dans les "
                        "cellules de Purkinje.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur2", name="mGluR2", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "amygdala"],
         description="Group II Gi presynaptic autoreceptor lowering glutamate "
                     "release; agonists target anxiety and schizophrenia.",
         description_fr="Autorécepteur présynaptique Gi du groupe II réduisant la "
                        "libération de glutamate ; agonistes visés pour l'anxiété "
                        "et la schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur3", name="mGluR3", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "thalamus"],
         description="Group II Gi receptor on terminals and glia reducing "
                     "glutamate release; neuroprotective, schizophrenia interest.",
         description_fr="Récepteur Gi du groupe II sur terminaisons et glie "
                        "réduisant la libération de glutamate ; neuroprotecteur, "
                        "intérêt schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur4", name="mGluR4", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["cerebellum", "thalamus", "hypothalamus", "caudate", "putamen"],
         description="Group III Gi presynaptic receptor suppressing release; "
                     "basal-ganglia activation proposed for Parkinson's.",
         description_fr="Récepteur présynaptique Gi du groupe III réduisant la "
                        "libération ; activation des noyaux gris visée pour la "
                        "maladie de Parkinson.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur5", name="mGluR5", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["caudate", "putamen", "accumbens", "hippocampus", "frontal",
                    "parietal", "temporal", "occipital", "amygdala"],
         description="Group I Gq receptor potentiating NMDA; fragile-X and "
                     "psychiatric drug target, dense in striatum/cortex.",
         description_fr="Récepteur Gq du groupe I potentialisant le NMDA ; cible X "
                        "fragile/psychiatrie, dense dans le striatum et le cortex.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    # Stub: mGluR6 is restricted to retinal ON-bipolar cells.
    dict(id="mglur6", name="mGluR6", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur7", name="mGluR7", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic", locations="ALL",
         description="Group III Gi presynaptic autoreceptor, the most widespread "
                     "mGluR, gating release at active zones; lowest affinity.",
         description_fr="Autorécepteur présynaptique Gi du groupe III, le mGluR le "
                        "plus répandu, contrôle la libération aux zones actives ; "
                        "plus faible affinité.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),

    # --- Glycinergic -----------------------------------------------------------
    dict(id="glycine", name="Glycine", family="glycinergic",
         neurotransmitter="Glycine", receptor_class="ionotropic",
         sign="inhibitory", synaptic="postsynaptic",
         locations=["midbrain", "pons", "medulla", "cerebellum", "hippocampus"],
         description="Ionotropic Cl- channel; major inhibitory receptor of the "
                     "brainstem (its dominant spinal-cord site is out of frame).",
         description_fr="Canal Cl- ionotrope ; principal récepteur inhibiteur du "
                        "tronc cérébral (son site médullaire dominant est hors "
                        "champ).",
         wikipedia="https://en.wikipedia.org/wiki/Glycine_receptor"),

    # --- Histaminergic ---------------------------------------------------------
    dict(id="h1", name="H1", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "cingulate",
                    "amygdala", "hippocampus", "thalamus", "hypothalamus",
                    "midbrain", "pons", "medulla"],
         description="Gq excitatory; drives wakefulness and arousal; its blockade "
                     "by antihistamines causes sedation.",
         description_fr="Gq excitateur ; favorise l'éveil et la vigilance ; son "
                        "blocage par les antihistaminiques cause la sédation.",
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H1_receptor"),
    dict(id="h2", name="H2", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "caudate",
                    "putamen", "hippocampus", "cerebellum"],
         description="Gs cAMP receptor; mainly gastric, with a lighter CNS role in "
                     "basal ganglia and cortex.",
         description_fr="Récepteur Gs/AMPc ; surtout gastrique, avec un rôle "
                        "central plus léger dans les noyaux gris et le cortex.",
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H2_receptor"),
    dict(id="h3", name="H3", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "cingulate",
                    "caudate", "putamen", "accumbens", "hippocampus", "hypothalamus",
                    "olfactory_bulb"],
         description="Gi presynaptic auto/heteroreceptor; CNS-wide; curbs "
                     "transmitter release; cognition and wakefulness target.",
         description_fr="Auto/hétérorécepteur présynaptique Gi ; pan-cérébral ; "
                        "freine la libération de neurotransmetteurs ; cible "
                        "cognition/éveil.",
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H3_receptor"),
    # Stub: H4 is an immune/haematopoietic receptor (no neuronal CNS role).
    dict(id="h4", name="H4", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="modulatory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H4_receptor"),

    # --- Opioidergic -----------------------------------------------------------
    dict(id="mu", name="μ (MOR)", family="opioidergic",
         neurotransmitter="Opioid peptides", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["midbrain", "pons", "medulla", "thalamus", "caudate", "putamen", "accumbens",
                    "amygdala", "frontal", "parietal", "temporal", "occipital",
                    "vta", "hypothalamus", "hippocampus"],
         description="Main analgesia/euphoria/dependence opioid receptor; dense in "
                     "PAG, thalamus, striatum, amygdala.",
         description_fr="Récepteur opioïde principal de l'analgésie/euphorie/"
                        "dépendance ; dense dans la SGPA, le thalamus, le "
                        "striatum, l'amygdale.",
         wikipedia="https://en.wikipedia.org/wiki/%CE%9C-opioid_receptor"),
    dict(id="delta", name="δ (DOR)", family="opioidergic",
         neurotransmitter="Opioid peptides", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["frontal", "parietal", "temporal", "occipital", "caudate",
                    "putamen", "accumbens", "amygdala", "olfactory_bulb",
                    "hippocampus"],
         description="Opioid receptor modulating mood and anxiety; cortex, "
                     "striatum, amygdala, olfactory bulb.",
         description_fr="Récepteur opioïde modulant l'humeur et l'anxiété ; "
                        "cortex, striatum, amygdale, bulbe olfactif.",
         wikipedia="https://en.wikipedia.org/wiki/%CE%B4-opioid_receptor"),
    dict(id="kappa", name="κ (KOR)", family="opioidergic",
         neurotransmitter="Opioid peptides", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["caudate", "putamen", "accumbens", "claustrum", "hypothalamus",
                    "midbrain", "pons", "medulla", "amygdala"],
         description="Opioid receptor driving dysphoria and stress; striatum, "
                     "claustrum, hypothalamus, PAG.",
         description_fr="Récepteur opioïde induisant dysphorie et réponses au "
                        "stress ; striatum, claustrum, hypothalamus, SGPA.",
         wikipedia="https://en.wikipedia.org/wiki/%CE%BA-opioid_receptor"),

    # --- Serotonergic ----------------------------------------------------------
    dict(id="5ht1a", name="5-HT1A", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["raphe", "hippocampus", "frontal", "parietal", "temporal",
                    "occipital", "amygdala", "septal_nuclei"],
         description="Gi-coupled; raphe somatodendritic autoreceptor and "
                     "postsynaptic; anxiety/depression target (buspirone, SSRIs).",
         description_fr="Couplé à Gi ; autorécepteur somatodendritique du raphé et "
                        "postsynaptique ; cible anxiété/dépression (buspirone, "
                        "ISRS).",
         wikipedia="https://en.wikipedia.org/wiki/5-HT1A_receptor"),
    dict(id="5ht1b", name="5-HT1B", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["caudate", "putamen", "globus_pallidus", "substantia_nigra",
                    "frontal", "hippocampus"],
         description="Gi-coupled; presynaptic terminal autoreceptor in basal "
                     "ganglia; triptan target for migraine.",
         description_fr="Couplé à Gi ; autorécepteur terminal présynaptique des "
                        "noyaux gris centraux ; cible des triptans (migraine).",
         wikipedia="https://en.wikipedia.org/wiki/5-HT1B_receptor"),
    dict(id="5ht1d", name="5-HT1D", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both",
         locations=["globus_pallidus", "substantia_nigra", "caudate", "putamen",
                    "hippocampus", "frontal", "accumbens"],
         description="Gi-coupled; low-level basal ganglia/cortex; presynaptic "
                     "terminal autoreceptor; triptan migraine target.",
         description_fr="Couplé à Gi ; faible niveau noyaux gris/cortex ; "
                        "autorécepteur terminal présynaptique ; cible triptan "
                        "(migraine).",
         wikipedia="https://en.wikipedia.org/wiki/5-HT1D_receptor"),
    dict(id="5ht1e", name="5-HT1E", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic",
         locations=["frontal", "hippocampus", "olfactory_bulb", "cingulate",
                    "accumbens"],
         description="Gi-coupled; frontal cortex, hippocampus and olfactory bulb; "
                     "implicated in human memory; poorly characterized.",
         description_fr="Couplé à Gi ; cortex frontal, hippocampe et bulbe "
                        "olfactif ; impliqué dans la mémoire humaine ; mal "
                        "caractérisé.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT1E_receptor"),
    dict(id="5ht1f", name="5-HT1F", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic",
         locations=["frontal", "occipital", "thalamus", "subthalamic_nucleus"],
         description="Gi-coupled; cortex, thalamus, subthalamus; target of "
                     "lasmiditan for migraine without vasoconstriction.",
         description_fr="Couplé à Gi ; cortex, thalamus, subthalamus ; cible du "
                        "lasmiditan contre la migraine sans vasoconstriction.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT1F_receptor"),
    dict(id="5ht2a", name="5-HT2A", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "claustrum"],
         description="Gq-coupled; dense on cortical pyramidal cells; mediates "
                     "psychedelics; atypical antipsychotic target.",
         description_fr="Couplé à Gq ; dense sur les cellules pyramidales "
                        "corticales ; médiateur des psychédéliques ; cible "
                        "antipsychotique atypique.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT2A_receptor"),
    dict(id="5ht2b", name="5-HT2B", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["hypothalamus", "frontal", "amygdala"],
         description="Gq-coupled; mostly peripheral (cardiac valves); sparse CNS "
                     "in hypothalamus, cortex, amygdala; valvulopathy risk.",
         description_fr="Couplé à Gq ; surtout périphérique (valves cardiaques) ; "
                        "rare dans le SNC : hypothalamus, cortex, amygdale ; "
                        "risque de valvulopathie.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT2B_receptor"),
    dict(id="5ht2c", name="5-HT2C", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "hippocampus", "amygdala", "hypothalamus",
                    "substantia_nigra", "accumbens"],
         description="Gq-coupled; choroid plexus, cortex, limbic and hypothalamus; "
                     "regulates appetite and mood (lorcaserin).",
         description_fr="Couplé à Gq ; plexus choroïde, cortex, limbique et "
                        "hypothalamus ; régule l'appétit et l'humeur "
                        "(lorcasérine).",
         wikipedia="https://en.wikipedia.org/wiki/5-HT2C_receptor"),
    dict(id="5ht3", name="5-HT3", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["midbrain", "pons", "medulla", "hippocampus", "amygdala"],
         description="Ionotropic cation channel; area postrema drives "
                     "nausea/vomiting; antiemetic target (ondansetron).",
         description_fr="Canal cationique ionotrope ; l'area postrema déclenche "
                        "nausées/vomissements ; cible antiémétique (ondansétron).",
         wikipedia="https://en.wikipedia.org/wiki/5-HT3_receptor"),
    dict(id="5ht4", name="5-HT4", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["hippocampus", "caudate", "putamen", "frontal", "accumbens"],
         description="Gs-coupled; hippocampus, striatum, cortex; cognition and gut "
                     "motility.",
         description_fr="Couplé à Gs ; hippocampe, striatum, cortex ; cognition et "
                        "motilité intestinale.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT4_receptor"),
    dict(id="5ht5a", name="5-HT5A", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic",
         locations=["frontal", "cingulate", "cerebellum", "hippocampus",
                    "hypothalamus", "accumbens"],
         description="Gi-coupled; cortex, cerebellum, hippocampus, hypothalamus; "
                     "least understood subtype, possible circadian role.",
         description_fr="Couplé à Gi ; cortex, cervelet, hippocampe, hypothalamus ; "
                        "sous-type le moins compris, rôle circadien possible.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT5A_receptor"),
    dict(id="5ht6", name="5-HT6", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["caudate", "putamen", "frontal", "hippocampus", "accumbens"],
         description="Gs-coupled; striatum, cortex, hippocampus; almost entirely "
                     "CNS; cognition target.",
         description_fr="Couplé à Gs ; striatum, cortex, hippocampe ; presque "
                        "exclusivement SNC ; cible cognition.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT6_receptor"),
    dict(id="5ht7", name="5-HT7", family="serotonergic",
         neurotransmitter="Serotonin", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["thalamus", "hypothalamus", "hippocampus", "frontal",
                    "amygdala"],
         description="Gs-coupled; thalamus, hypothalamus, hippocampus; circadian "
                     "rhythm, mood and thermoregulation.",
         description_fr="Couplé à Gs ; thalamus, hypothalamus, hippocampe ; rythme "
                        "circadien, humeur et thermorégulation.",
         wikipedia="https://en.wikipedia.org/wiki/5-HT7_receptor"),

    # --- Cannabinoid (added; not in the source table) --------------------------
    dict(id="cb1", name="CB1", family="cannabinoid",
         neurotransmitter="Endocannabinoids", receptor_class="metabotropic",
         sign="modulatory", synaptic="presynaptic",
         locations=["substantia_nigra", "globus_pallidus", "caudate", "putamen",
                    "hippocampus", "frontal", "parietal", "temporal", "occipital",
                    "cerebellum", "amygdala"],
         description="Gi GPCR; presynaptic retrograde signaling, THC target; one "
                     "of the most abundant brain GPCRs.",
         description_fr="RCPG Gi ; signalisation rétrograde présynaptique, cible du "
                        "THC ; parmi les RCPG les plus abondants du cerveau.",
         wikipedia="https://en.wikipedia.org/wiki/Cannabinoid_receptor_type_1"),

    # --- Purinergic (added) ----------------------------------------------------
    dict(id="a2a", name="A2A", family="purinergic",
         neurotransmitter="Adenosine", receptor_class="metabotropic",
         sign="modulatory", synaptic="both",
         locations=["caudate", "putamen", "accumbens"],
         description="Gs GPCR concentrated in striatum on D2 indirect-pathway "
                     "neurons; caffeine antagonist target.",
         description_fr="RCPG Gs concentré dans le striatum sur les neurones D2 de "
                        "la voie indirecte ; cible antagoniste de la caféine.",
         wikipedia="https://en.wikipedia.org/wiki/Adenosine_A2A_receptor"),

    # --- Sigma (added; sigma-1 is an intracellular ER chaperone, not a channel
    #     or GPCR, hence receptor_class="chaperone") ---------------------------
    dict(id="sigma1", name="σ1", family="sigma",
         neurotransmitter="Sigma ligands", receptor_class="chaperone",
         sign="modulatory", synaptic="both",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "midbrain", "pons", "medulla", "cerebellum"],
         description="Intracellular ER chaperone (not a classic channel/GPCR); "
                     "fluvoxamine acts partly via it.",
         description_fr="Chaperon intracellulaire du RE (ni canal ni RCPG "
                        "classique) ; la fluvoxamine agit en partie via lui.",
         wikipedia="https://en.wikipedia.org/wiki/Sigma-1_receptor"),

    # --- Melatonergic (added) --------------------------------------------------
    dict(id="mt1", name="MT1", family="melatonergic",
         neurotransmitter="Melatonin", receptor_class="metabotropic",
         sign="modulatory", synaptic="postsynaptic",
         locations=["hypothalamus", "pituitary"],
         description="Gi GPCR in hypothalamic SCN + pituitary pars tuberalis; "
                     "sleep/circadian, ramelteon target.",
         description_fr="RCPG Gi dans le NSC hypothalamique et la pars tuberalis "
                        "hypophysaire ; sommeil/circadien, cible du ramelteon.",
         wikipedia="https://en.wikipedia.org/wiki/Melatonin_receptor_1A"),
    dict(id="mt2", name="MT2", family="melatonergic",
         neurotransmitter="Melatonin", receptor_class="metabotropic",
         sign="modulatory", synaptic="postsynaptic",
         locations=["hypothalamus"],
         description="Gi GPCR in hypothalamic SCN; drives circadian "
                     "phase-shifting.",
         description_fr="RCPG Gi dans le NSC hypothalamique ; gère le décalage de "
                        "phase circadien.",
         wikipedia="https://en.wikipedia.org/wiki/Melatonin_receptor_1B"),
]


def _structure_record(entry: dict[str, Any], structure_id: str,
                      name: dict[str, str], base_name: dict[str, str],
                      position: tuple[float, float, float], shape_id: str,
                      mirror: bool = False,
                      image_urls: dict[str, str] | None = None) -> dict[str, Any]:
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
    image_urls
        Map of base id -> Wikimedia GIF url (see
        :func:`_load_structure_image_urls` / ``tools/fetch_structure_images.py``); a
        match adds a ``structure_image`` url the viewer hot-links in the structure
        panel, a non-match omits it.

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
    # External reference link (same article for both hemispheres of a pair),
    # tagged with its provenance grade for the source pill (see _wiki_provenance).
    wiki = WIKIPEDIA.get(entry["base"])
    if wiki:
        record["wikipedia"] = wiki
        record["wikipedia_provenance"] = _wiki_provenance(entry["base"])
    if image_urls and entry["base"] in image_urls:
        # Wikimedia url (not a local path): the GIFs are too large to vendor, so
        # the viewer hot-links them at runtime (spinner / silent-fail, see
        # showStructure). Keyed by base so both hemispheres share the one URL, and
        # only set when its base was resolved (so a structure without one renders no
        # image, no broken placeholder).
        record["structure_image"] = image_urls[entry["base"]]
    if mirror:
        record["mirror"] = True
    return record


# Half-width of the longitudinal fissure: each cortical lobe's medial face is
# cut flat at world x = +/- this, so the left and right hemispheres meet along a
# thin midline gap instead of overlapping into one ball. Small = tight fissure.
MIDLINE_GAP = 0.06

# Clearance between a carved lobe channel and the carver's surface (see
# _tube_carve): the channel radius is the carver's profile inflated by its noise
# plus this gap, so the lobe never z-fights the carver and the carver shows
# cleanly through the notch.
LOBE_CARVE_GAP = 0.12


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
        return dict(entry["shape"])
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


def _tube_carve(carver: dict[str, Any],
                blob: dict[str, Any]) -> dict[str, Any] | None:
    """Channel a swept-tube ``carver`` subtracts from ``blob`` if it threads it.

    A ``carves=True`` curve (the C-shaped caudate) hollows a groove in the lobes
    it passes through so it seats into a clean notch ("partly exposed", a jigsaw
    piece set into the seam) rather than the cortex poking through it. This returns
    the carver's spine points + per-station channel radius expressed in ``blob``'s
    *local* frame (its geometry is centred at the origin and positioned later),
    which ``buildBlobGeometry`` consumes (see ``CARVE_TUBES`` in js/shapes.js):
    any lobe vertex inside the tube is pushed out onto the tube surface.

    The channel radius pads the carver's ``profile`` by its noise inflation plus
    :data:`LOBE_CARVE_GAP`, so the lobe clears the carver's wobbling surface and
    the carver shows through the notch instead of z-fighting it.

    Like the medial wall and the jigsaw planes this is computed once on the right
    side; the left lobe reuses the same shape file mirrored across x, which flips
    the notch to align with the mirrored (left) carver for free.

    Adjacency is geometry-derived (a spine control point reaching inside the
    blob's noise-inflated surface), not hand-listed, exactly like the jigsaw
    clipping; returns ``None`` when the tube never enters ``blob`` so non-threaded
    lobes emit no carve field and stay untouched.

    Parameters
    ----------
    carver
        A ``carves=True`` entry whose ``shape`` is a ``type="curve"`` payload.
    blob
        A default-blob entry (``radii``/``noise``/``pos``) to test and carve.
    """
    shape = carver["shape"]
    if shape.get("type") != "curve":
        return None
    cx, cy, cz = carver["pos"]
    bx, by, bz = blob["pos"]
    noise = shape.get("noise", 0.0)
    radii = tuple(blob["radii"])
    points: list[list[float]] = []
    radius: list[float] = []
    penetrates = False
    for (lx, ly, lz), pr in zip(shape["points"], shape["profile"]):
        # Spine control point in the blob's local frame (blob is centred at pos).
        px, py, pz = (cx + lx) - bx, (cy + ly) - by, (cz + lz) - bz
        points.append([round(px, 3), round(py, 3), round(pz, 3)])
        r = pr * (1 + noise) + LOBE_CARVE_GAP
        radius.append(round(r, 3))
        d = math.sqrt(px * px + py * py + pz * pz)
        if d < 1e-6:
            penetrates = True
            continue
        reach = _directional_extent(radii, blob["noise"], (px / d, py / d, pz / d))
        # Tube near-edge (d - r) reaching inside the blob surface => it threads it.
        if d - r < reach:
            penetrates = True
    if not penetrates:
        return None
    return {"points": points, "radius": radius}


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


def _expand_sources(keys: list[str]) -> list[dict[str, str]]:
    """Resolve a list of :data:`SOURCES` keys to full citation objects.

    Pathways cite shared references by short key so a citation lives once in
    :data:`SOURCES`; this expands each key into the ``{citation, url}`` object the
    viewer renders, keeping ``data/projections.jsonl`` self-contained (the client never
    resolves keys). Raising on an unknown key makes a typo fail the build instead
    of silently dropping a reference.

    Parameters
    ----------
    keys
        Source keys listed on a projection's ``sources`` field.

    Returns
    -------
    list of dict
        One ``{citation, url, provenance}`` dict per key, in order. ``provenance``
        is the entry's own grade if it set one, else :data:`DEFAULT_PROVENANCE`
        (see :data:`PROVENANCE_LEVELS`), validated so a typo fails the build.
    """
    expanded: list[dict[str, str]] = []
    for key in keys:
        if key not in SOURCES:
            raise KeyError(f"projection references unknown source '{key}'")
        src = dict(SOURCES[key])
        src["provenance"] = _provenance(
            src.get("provenance", DEFAULT_PROVENANCE), f"source {key!r}")
        expanded.append(src)
    return expanded


def _projection_records(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one projection definition into its JSONL record(s).

    Projections are bilateral by default: each is emitted as given and, unless
    it sets ``"symmetric": False``, also as a hemisphere-flipped twin (``_R`` <->
    ``_L`` on both endpoints). The twin is skipped when flipping changes nothing
    (e.g. a purely midline pathway) so no duplicate is produced. ``symmetric`` is
    a generator hint and is stripped from the emitted records.

    The ``sources`` key (a list of :data:`SOURCES` keys) is expanded in place to
    full citation objects, and the expanded metadata (``neurotransmitter``,
    ``label``, ``description``, ``bidirectional``, ...) is carried onto the
    mirrored twin unchanged so both hemispheres show the same details. The
    translatable display fields (``label``, ``description``, ``neurotransmitter``)
    are wrapped bilingually with :func:`_t` so the data file is self-describing in
    both languages.
    """
    symmetric = proj.get("symmetric", True)
    fields = {k: v for k, v in proj.items() if k != "symmetric"}
    if "sources" in fields:
        fields["sources"] = _expand_sources(fields["sources"])
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
        # Source grade of this receptor's classification claims (its
        # neurotransmitter / mechanism class / sign / synaptic site / locations), so
        # the panel can show a provenance pill for "why is it excitatory" and the
        # coverage tally can count it. Authored from general/Wikipedia knowledge, so
        # "llm" by default; upgrade per-receptor in RECEPTOR_PROVENANCE as checked.
        "classification_provenance": _receptor_provenance(rec["id"]),
    }
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
        if spec.get("wikipedia"):
            targets[tid]["wikipedia"] = spec["wikipedia"]
            targets[tid]["wikipedia_provenance"] = _wiki_provenance(tid)
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

    The authored drug (from ``tools/drugs_data.json``) is mostly passed through;
    this validates it against the drug vocabularies (categories / targets /
    actions / effect overrides) and attaches the constant :data:`STAHL_SOURCE`.
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
        if b["action"] not in DRUG_ACTIONS:
            raise KeyError(f"Drug {drug['id']!r} binding action {b['action']!r} "
                           f"has no DRUG_ACTIONS entry")
        out_b: dict[str, Any] = {"target": b["target"], "action": b["action"]}
        if "effect" in b:
            if b["effect"] not in DRUG_EFFECT_COLORS:
                raise KeyError(f"Drug {drug['id']!r} binding effect {b['effect']!r} "
                               f"has no DRUG_EFFECT_COLORS entry")
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
        bindings.append(out_b)
    out: dict[str, Any] = {
        "id": drug["id"],
        "name": drug["name"],
        "categories": list(drug["categories"]),
        "bindings": bindings,
        "sources": [dict(STAHL_SOURCE)],
        "focusable": len(bindings) > 0,
    }
    if drug.get("nbn"):
        out["nbn"] = drug["nbn"]
        # The NbN is quote-sourced like a binding: Stahl prints a verbatim
        # "Neuroscience-based Nomenclature: ..." line on each drug's first page.
        nbn_sources = _quote_sources(drug.get("nbn_sources"), f"Drug {drug['id']!r} nbn")
        if nbn_sources:
            out["nbn_sources"] = nbn_sources
    if drug.get("description"):
        out["description"] = drug["description"]
        # Every description carries a provenance grade so the panel can show a pill.
        # Default "llm" (an LLM-synthesized mechanism line); set "sourced" when the
        # description was replaced by a drug's Wikipedia lead (see fetch_descriptions).
        out["description_provenance"] = _provenance(
            drug.get("description_provenance", DEFAULT_PROVENANCE),
            f"drug {drug['id']!r} description")
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


def _load_structure_image_urls() -> dict[str, str]:
    """Map ``base id -> Wikimedia GIF url`` from ``tools/structure_images_sources.json``.

    Unlike the drug molecule SVGs (vendored same-origin), the structure
    illustration GIFs are too large to commit, so the viewer **hot-links** them
    from Wikimedia at runtime (with a spinner / silent-fail, see ``showStructure``):
    only the URL is stored in the data, not the binary. The URLs are resolved
    author-side by ``tools/fetch_structure_images.py`` (which hits the network) and
    recorded in that small JSON; this offline generator just reads it, so a structure
    gets a ``structure_image`` iff its base has an entry. A missing file is fine (no
    images). Keyed by base id, so both hemispheres of a pair share the one URL.
    """
    src = Path(__file__).resolve().parent / "structure_images_sources.json"
    if not src.exists():
        return {}
    data = json.loads(src.read_text(encoding="utf-8"))
    return {base: rec["url"] for base, rec in data.items() if rec.get("url")}


def _load_drugs() -> list[dict[str, Any]]:
    """Read the authored drug list from ``tools/drugs_data.json`` (if present).

    The drug data is kept in a sibling JSON rather than inline in this module
    because it is large and comes from extraction (Stahl's Prescriber's Guide);
    keeping it separate keeps this generator readable. A missing file is not an
    error (the drugs feature is simply empty), so the generator still runs on a
    checkout without it.
    """
    path = Path(__file__).resolve().parent / "drugs_data.json"
    if not path.exists():
        log.warning("no %s; drugs.jsonl will be empty", path.name)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must be a JSON list of drug objects")
    return data


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


def _provenance_stats(structures: list[dict[str, Any]],
                      projections: list[dict[str, Any]],
                      receptors: list[dict[str, Any]],
                      drugs: list[dict[str, Any]],
                      drug_targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Programmatic sourcing tally emitted into ``meta.provenance_stats``.

    Every factual claim and every reference link in the dataset is bucketed by the
    strength of its source: ``verified`` (quote-checked), ``sourced`` (from a
    document, not quote-checked) or ``unverified`` (LLM-only, or no source yet). The
    viewer's About panel and the README headline read these numbers, so the
    "% sourced" figure is always a real count of the shipped data, never hand-typed
    (the whole point of the request: a programmatic count of source type vs all).

    "Assertions" are the factual claims (drug bindings, drug NbN labels, drug
    descriptions, neuron projections, receptor classifications, non-receptor target
    classifications, brain-region anatomy) and drive the headline ``pct_backed``;
    Wikipedia "references" are tallied separately (read-more links, not claims).
    """
    def bucket(rank_or_grade: Any) -> str:
        rank = (rank_or_grade if isinstance(rank_or_grade, int)
                else _GRADE_RANK.get(rank_or_grade, 0))
        return ("verified" if rank == 3 else
                "sourced" if rank == 2 else "unverified")

    def tally(grades: list[Any]) -> dict[str, int]:
        counts = {"total": 0, "verified": 0, "sourced": 0, "unverified": 0}
        for g in grades:
            counts["total"] += 1
            counts[bucket(g)] += 1
        return counts

    binding_grades = [_strongest_grade(b.get("sources"))
                      for d in drugs for b in d.get("bindings", [])]
    nbn_grades = [_strongest_grade(d.get("nbn_sources"))
                  for d in drugs if d.get("nbn")]
    desc_grades = [d.get("description_provenance", DEFAULT_PROVENANCE)
                   for d in drugs if d.get("description")]
    projection_grades = [_strongest_grade(p.get("sources")) for p in projections]
    # Receptor classification claims (neurotransmitter / mechanism class / sign /
    # synaptic site / locations), graded per receptor (classification_provenance). A
    # pure stub (no CNS role: no locations, not ubiquitous, no description) asserts
    # nothing real, so it is skipped.
    receptor_grades = [
        r.get("classification_provenance", DEFAULT_PROVENANCE)
        for r in receptors
        if r.get("ubiquitous") or r.get("locations") or r.get("description")]
    # Non-receptor drug target classifications (type / system / region footprint),
    # graded per target. Receptor-linked targets are skipped (already counted as
    # receptors, not twice).
    target_grades = [t.get("classification_provenance", DEFAULT_PROVENANCE)
                     for t in drug_targets.values() if t.get("type") != "receptor"]
    # Brain-region anatomy (existence / group / position), graded per emitted
    # structure record (both hemispheres of a pair count, one line each).
    structure_grades = [s.get("classification_provenance", DEFAULT_PROVENANCE)
                        for s in structures]
    # Wikipedia reference links across every owner kind. Non-receptor targets only
    # (a receptor is already counted via the receptor records, not twice); a missing
    # link is a rank-0 "unverified" so the gap shows in the coverage.
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
        "drug_descriptions": tally(desc_grades),
        "projections": tally(projection_grades),
        "receptors": tally(receptor_grades),
        "targets": tally(target_grades),
        "structures": tally(structure_grades),
        "references": tally(ref_grades),
    }
    assertion_kinds = ("drug_bindings", "drug_nbn", "drug_descriptions",
                       "projections", "receptors", "targets", "structures")
    assertions = {"total": 0, "verified": 0, "sourced": 0, "unverified": 0}
    for kind in assertion_kinds:
        for key in assertions:
            assertions[key] += by_kind[kind][key]
    backed = assertions["verified"] + assertions["sourced"]
    assertions["backed"] = backed
    assertions["pct_backed"] = (
        round(100 * backed / assertions["total"]) if assertions["total"] else 0)
    return {"by_kind": by_kind, "assertions": assertions}


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
    # group so the small deep nuclei still nest inside the cortex (a lobe is never
    # carved by a nucleus); within a group, overlap is detected per pair.
    blob_groups: dict[str, list[dict[str, Any]]] = {}
    for entry in PAIRED:
        if "shape" not in entry:
            blob_groups.setdefault(entry["group"], []).append(entry)

    # Swept-tube carvers (the caudate) that hollow a notch in the lobes they pass
    # through, so they read as "partly exposed" instead of buried/interpenetrating.
    # Geometry-derived like the jigsaw clipping: a carver only carves the lobes its
    # spine actually threads (see _tube_carve). Defined on the right side; the left
    # lobes mirror their shape file, flipping the notch to the mirrored carver.
    carvers = [e for e in PAIRED if e.get("carves")]

    # Wikimedia GIF urls resolved author-side (offline read of the sources JSON);
    # a structure whose base has one gets a hot-linked structure_image (the GIFs
    # are too large to vendor, unlike the drug molecule SVGs).
    structure_image_urls = _load_structure_image_urls()

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
            # Only the cortical lobes are carved (a nucleus never carves a lobe,
            # mirroring the same-group jigsaw rule that keeps nuclei nested).
            if entry["group"] == "lobe":
                carves = [c for c in (_tube_carve(cv, entry) for cv in carvers) if c]
                if carves:
                    shape["carve_tubes"] = carves
        shapes[base] = shape
        # Bilingual base name (e.g. {"en": "Putamen", "fr": "Putamen"}); the
        # per-hemisphere display names are composed from it (English prefix,
        # French gender/number-agreed suffix). ``fr_gender`` tunes the agreement.
        base_name = _t(entry["name"])
        gender = entry.get("fr_gender", "m")
        structures.append(
            _structure_record(entry, f"{base}_R", _side_name(base_name, gender, "R"),
                              base_name, (x, y, z), base,
                              image_urls=structure_image_urls))
        structures.append(
            _structure_record(entry, f"{base}_L", _side_name(base_name, gender, "L"),
                              base_name, (-x, y, z), base, mirror=True,
                              image_urls=structure_image_urls))

    for entry in MIDLINE:
        sid = entry["base"]
        # Midline structures have no hemisphere, so the full name is the base.
        name = _t(entry["name"])
        structures.append(
            _structure_record(entry, sid, name, name, entry["pos"], sid,
                              image_urls=structure_image_urls))
        shapes[sid] = _shape_record(entry, entry["pos"][0])

    for proj in PROJECTIONS:
        projections.extend(_projection_records(proj))

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
            record["sources"] = _expand_sources(circuit["sources"])
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
            record["sources"] = _expand_sources(group["sources"])
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

    # Drugs: authored in tools/drugs_data.json, validated against the drug
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
            structures, projections, receptors, drugs, drug_targets),
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

    # meta is a single object -> pretty-printed meta.json; the collections are one
    # JSON object per line -> one *.jsonl each.
    meta_path = data_dir / "meta.json"
    meta_path.write_text(
        json.dumps(data["meta"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    log.info("wrote %s", meta_path)

    for name in ("structures", "projections", "circuits", "projection_groups",
                 "receptors", "drugs"):
        path = data_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for record in data[name]:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        log.info("wrote %s (%d lines)", path, len(data[name]))

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
