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
    "recreational": {"en": "Recreational / psychoactive",
                     "fr": "Récréatif / psychoactif"},
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
    # A *vesicular* transporter inhibitor (VMAT2): unlike a plasma-membrane reuptake
    # pump, blocking vesicular loading DEPLETES the transmitter, so the net effect is
    # a block (tone down), not a boost. Kept distinct from reuptake_inhibitor so the
    # direction is never conflated. See toneSignOf in js/data.js.
    "vesicular_inhibitor": {"label": {"en": "Vesicular transport inhibitor",
                                      "fr": "Inhibiteur du transport vésiculaire"},
                            "effect": "block"},
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
              # A *vesicular* transporter: it loads monoamines into synaptic
              # vesicles, so inhibiting it DEPLETES releasable transmitter and
              # *lowers* the system's tone, the opposite of a plasma-membrane
              # reuptake transporter (SERT/DAT/NET). The viewer's flow overlay
              # reads this flag to sign the tone correctly (js/data.js toneSignOf).
              "vesicular": True,
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
                           "type": "enzyme", "system": None,
                           "wikipedia": "https://en.wikipedia.org/wiki/Carbonic_anhydrase",
                           "regions": []},
    "pde5": {"name": {"en": "Phosphodiesterase 5 (PDE5)",
                      "fr": "Phosphodiestérase 5 (PDE5)"},
             "type": "enzyme", "system": None,
             "wikipedia": "https://en.wikipedia.org/wiki/PDE5",
             "regions": []},
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
               # The α2 family's dominant pharmacology is the presynaptic
               # *inhibitory autoreceptor* on noradrenergic neurons: an agonist
               # (clonidine) damps NA tone, an antagonist (mirtazapine, yohimbine)
               # disinhibits and raises it. Marked so the flow overlay signs the
               # tone (the specific 5-HT1x / D2/D3 autoreceptors carry this on their
               # own receptor records; a receptor_group has none, so it is set here).
               "sign": "inhibitory", "synaptic": "presynaptic",
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
# neurotransmitter / mechanism class / sign / synaptic site), a non-receptor drug
# target (its type / system / region footprint) and a brain structure (its
# existence / group / position), all authored from general / Wikipedia / textbook
# knowledge, so they default to the honest ``"llm"`` grade (LLM-only, unchecked).
# Keyed by receptor id / DRUG_TARGETS key / structure *base* id; upgrade an entry
# here as its claim is checked against a document (raise to ``"sourced"`` /
# ``"verified"``), keeping the grading in the data, not in code. Empty for now
# (everything grades as ``"llm"``). A receptor's *expression regions* are graded
# separately, per region (see RECEPTOR_LOCATION_SOURCES); this override covers only
# the mechanism classification, not "which regions express it".
RECEPTOR_PROVENANCE: dict[str, str] = {}
TARGET_PROVENANCE: dict[str, str] = {}
STRUCTURE_PROVENANCE: dict[str, str] = {}
# The same, for a drug's *class* classification (its ``categories`` set, e.g. "SSRI"):
# the claim "this drug belongs to class X" is a node in its own right (kind
# ``drug_categories``), one per drug, graded like the receptor/target classification.
# Authored from general knowledge, so default ``"llm"``; keyed by drug id. A drug may
# additionally carry quote-level ``category_sources`` in tools/drugs_data.json, which
# upgrade the emitted grade (mirror of the target classification's optional quotes).
DRUG_CATEGORY_PROVENANCE: dict[str, str] = {}

# Per-region provenance for a receptor's *expression locations* ("Found in"): the
# claim "receptor R is expressed in region B" is distinct from R's mechanism
# classification and is authored from general knowledge, so every location defaults
# to ``"llm"`` (unsourced). This registry upgrades an individual (receptor, region)
# to a quote-source: ``{receptor_id: {base: [ {corpus, page, quote, provenance} ]}}``.
# ``_receptor_record`` validates each base is one of that receptor's own locations
# and emits the sources; the viewer shows a per-region pill and the coverage tally
# counts each region separately. Empty for now: no expression atlas is wired yet, so
# every "Found in" region is honestly ``"llm"``. Add entries as regions are sourced.
RECEPTOR_LOCATION_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {}

# The same, for a non-receptor drug target's *expression regions* ("Found in"): the
# claim "target T is found in region B" is a distinct node from T's type/system
# classification, so each region grades separately (default ``"llm"``). Keyed by
# DRUG_TARGETS id: ``{target_id: {base: [ {corpus, page, quote, provenance} ]}}``.
# ``_build_drug_targets`` validates each base is one of that target's own regions and
# emits ``location_sources``; the viewer shows a per-region pill and the coverage
# tally counts each region (kind ``target_locations``). Empty for now. Add entries as
# a target's regions are sourced.
TARGET_LOCATION_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {}


def _merge_external_location_sources() -> None:
    """Merge author-side sourced expression locations from ``tools/location_sources.json``
    into the two registries above.

    That file is machine-written by the expression-sourcing pipeline (fetch ->
    judge -> ``tools/apply_location_sources.py``, e.g. from GtoPdb tissue
    distributions), so the bulk of per-region sources lives in a sibling JSON rather
    than inline here (mirroring ``drugs_data.json`` / ``*_images_sources.json``); the
    in-code dicts above stay the place for any hand-authored override. Shape:
    ``{"receptors": {rid: {base: [source, ...]}}, "targets": {tid: {base: [...]}}}``.
    An external entry wins per (owner, base). A missing file is fine (nothing sourced),
    so the generator still runs on a checkout without it."""
    src = Path(__file__).resolve().parent / "location_sources.json"
    if not src.exists():
        return
    data = json.loads(src.read_text(encoding="utf-8"))
    for owner, per_base in (data.get("receptors") or {}).items():
        RECEPTOR_LOCATION_SOURCES.setdefault(owner, {}).update(per_base)
    for owner, per_base in (data.get("targets") or {}).items():
        TARGET_LOCATION_SOURCES.setdefault(owner, {}).update(per_base)


_merge_external_location_sources()


def _receptor_provenance(receptor_id: str) -> str:
    """Provenance grade for a receptor's classification claims (default ``llm``)."""
    return _lookup_provenance(
        RECEPTOR_PROVENANCE, receptor_id,
        f"receptor classification for {receptor_id!r}")


def _target_provenance(target_id: str) -> str:
    """Provenance grade for a non-receptor target's classification (default ``llm``)."""
    return _lookup_provenance(
        TARGET_PROVENANCE, target_id, f"target classification for {target_id!r}")


def _target_polarity_provenance(target_id: str) -> str:
    """Provenance grade for a target's tone-polarity claim (default ``llm``)."""
    return _lookup_provenance(
        TARGET_POLARITY_PROVENANCE, target_id,
        f"target polarity for {target_id!r}")


def _structure_provenance(base_id: str) -> str:
    """Provenance grade for a structure's anatomy claim (default ``llm``)."""
    return _lookup_provenance(
        STRUCTURE_PROVENANCE, base_id, f"structure anatomy for {base_id!r}")


def _location_sources(
        registry: dict[str, dict[str, list[dict[str, Any]]]], owner_id: str,
        regions: list[str], label: str) -> dict[str, list[dict[str, Any]]]:
    """Emitted per-region ``location_sources`` (``{base: [quote-source, ...]}``) for
    an owner whose "Found in" regions are each a separately-graded expression node: a
    receptor (:data:`RECEPTOR_LOCATION_SOURCES`) or a non-receptor drug target
    (:data:`TARGET_LOCATION_SOURCES`).

    Every cited base must be one of the owner's own ``regions`` (a stray base is a
    typo that would grade a region the owner does not claim), and each source is
    validated like any other quote-level source. Returns ``{}`` when nothing is
    sourced (the common case today), so the field is simply omitted and every region
    grades as ``llm``. ``label`` names the owner kind for error messages."""
    per_base = registry.get(owner_id)
    if not per_base:
        return {}
    known = set(regions)
    out: dict[str, list[dict[str, Any]]] = {}
    for base, sources in per_base.items():
        if base not in known:
            raise KeyError(
                f"{label} {owner_id!r} has location sources for {base!r}, "
                f"which is not one of its regions {sorted(known)}")
        out[base] = _quote_sources(
            sources, f"{label} {owner_id!r} location {base!r}")
    return out


# The constant source backing every drug record (the user-verified fair-use
# citation). Per-drug specifics (the binding profile) come from this single book;
# each drug additionally carries its own ``wikipedia`` link for quick reference.
# ``provenance`` grades the citation (see PROVENANCE_LEVELS): the drug bindings
# were extracted by an LLM given the Stahl dump but were not quote-verified, so
# they would warrant "sourced"; kept at the conservative "llm" default for now.


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
        "citation": "Stahl SM. Prescriber's Guide: Stahl's Essential "
                    "Psychopharmacology. 8th ed. Cambridge University Press; 2024.",
        "url": "TODO",
        "pages_dir": "sources/books/stahl/pages",
    },
    "kandel": {
        # Anatomy/pathway corpus (the projection claims, currently LLM-only, are
        # quote-verified against this). Full title + edition so a page citation is
        # unambiguous on its own.
        "ref": "Kandel, Principles of Neural Science, 6th ed.",
        "citation": "Kandel ER, Koester JD, Mack SH, Siegelbaum SA, eds. "
                    "Principles of Neural Science. 6th ed. McGraw Hill; 2021.",
        "url": "TODO",
        "pages_dir": "sources/books/eric_kandel/pages",
    },
    "stahl_essential": {
        # Mechanism/receptor corpus: the receptor + non-receptor-target
        # classification claims are quote-verified against this.
        "ref": "Stahl's Essential Psychopharmacology: Neuroscientific Basis, "
               "5th ed.",
        "citation": "Stahl SM. Stahl's Essential Psychopharmacology: "
                    "Neuroscientific Basis and Practical Applications. 5th ed. "
                    "Cambridge University Press; 2021.",
        "url": "TODO",
        "pages_dir": "sources/books/stahl_essential_pharmacology/pages",
    },
    "carlat": {
        # Second drug corpus: cross-sources drug bindings Stahl did not state.
        "ref": "Carlat Medication Fact Book for Psychiatric Practice, 7th ed.",
        "citation": "Carlat DJ. The Carlat Medication Fact Book for Psychiatric "
                    "Practice. 7th ed. Carlat Publishing; 2024.",
        "url": "TODO",
        "pages_dir": "sources/books/carlat_medication/pages",
    },
    "nieuwenhuys": {
        # Systematic neuroanatomy/connectivity corpus: backs region-anatomy +
        # projection claims Kandel does not state in prose (the claustrum, the
        # fornix, commissures). Page numbers are the PDF's 1-based pages (the .md
        # file names), which run a few ahead of the printed page numbers.
        "ref": "Nieuwenhuys, Voogd & van Huijzen, The Human Central Nervous "
               "System, 4th ed.",
        "citation": "Nieuwenhuys R, Voogd J, van Huijzen C. The Human Central "
                    "Nervous System. 4th ed. Springer; 2008.",
        "url": "TODO",
        "pages_dir": "sources/books/nieuwenhuys_atlas/pages",
    },
    "gtopdb": {
        # Expression/localization corpus: the IUPHAR/BPS Guide to Pharmacology
        # per-target "Tissue Distribution" statements, backing a receptor/target
        # expression-region claim ("R is found in region B"). Fetched from the GtoPdb
        # web service (tools/fetch_gtopdb.py) and cached author-side as one page per
        # target id: each `location_sources` quote is a verbatim `tissue` string and
        # its `page` is the GtoPdb target id, so the normal verbatim-quote gate
        # applies unchanged. Many entries are rat/mouse, so each source carries a
        # `species` (the viewer flags a non-human claim; see _quote_sources).
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), tissue distribution",
        "citation": "Harding SD, Armstrong JF, Faccenda E, et al. The IUPHAR/BPS "
                    "Guide to Pharmacology. Nucleic Acids Res. "
                    "guidetopharmacology.org.",
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "sources/gtopdb/pages",
    },
    "pdsp_ki": {
        # Binding-affinity corpus: measured Ki (nM) values backing a drug binding's
        # `ki` annotation. Unlike the book corpora this is a single CSV of assay
        # rows, not paged text, so it has no `pages_dir`; check_data confirms a
        # cited Ki id/value against the `csv` file instead (author-side, skipped on
        # a clone without it, like the quote gate). See tools/fetch_ki.py +
        # sources/books/pdsp_ki/README.md.
        "ref": "PDSP Ki Database (NIMH PDSP)",
        "citation": "NIMH Psychoactive Drug Screening Program (PDSP) Ki Database, "
                    "directed by Bryan L. Roth, University of North Carolina at "
                    "Chapel Hill.",
        "url": "https://pdspdb.unc.edu/databases/kidb.php",
        "csv": "sources/books/pdsp_ki/KiDatabase.csv",
    },
    "allen_ahba": {
        # Expression corpus: the Allen Human Brain Atlas microarray, backing a
        # receptor/target expression-region claim ("X is found in region B") the
        # GtoPdb tissue comments could not reach (esp. the non-receptor targets +
        # the deep nuclei). tools/fetch_allen.py aggregates Allen's PACall
        # present/absent boolean per (gene, region) across the 6 donors and writes one
        # cached page per gene (`page` = the HGNC gene symbol): each `location_sources`
        # quote is a verbatim presence line, so the normal verbatim-quote gate applies
        # unchanged. All 6 donors are human, so every quote carries `species: Human`.
        # Licence: copyright-reserved, non-commercial research use with required
        # citation; we vendor only the cited slice, never the atlas.
        "ref": "Allen Human Brain Atlas, microarray (Hawrylycz et al. 2012)",
        "citation": "Hawrylycz MJ, Lein ES, Guillozet-Bongaarts AL, et al. An "
                    "anatomically comprehensive atlas of the adult human brain "
                    "transcriptome. Nature. 2012;489(7416):391-399. "
                    "human.brain-map.org.",
        "url": "https://human.brain-map.org/",
        "pages_dir": "sources/allen/pages",
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
        # An expression/localization source (e.g. GtoPdb tissue distribution) may name
        # the assay species: many are rat/mouse, not human. It is carried through so the
        # viewer can flag a non-human claim (amber, like the non-human Ki chip); "Human"
        # or absent = no flag. The grade is independent of species (a rat quote is still
        # quote-verified), but the reader should see what was actually measured.
        if s.get("species"):
            rec["species"] = s["species"]
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


def _ki_annotation(drug_id: str, binding: dict[str, Any]) -> dict[str, Any] | None:
    """Validate + normalize a binding's PDSP ``ki`` annotation (measured binding
    affinity), or ``None`` when absent.

    Shape: ``{median, min, max, n_human, n_nonhuman, source}`` where ``source`` is
    one specific PDSP CSV row: ``{corpus:"pdsp_ki", ki_id, value_nm, species,
    preparation, radioligand, reference, provenance}`` plus, for a match recovered
    through the alias map (:data:`tools.fetch_ki.ALIAS`), ``mapped``/``measured_as``/
    ``relation``/``pdsp_names`` so the viewer warns *which* compound the Ki was
    measured on. The Ki carries its **own** ``verified`` source (rendered as its own
    badge beside the binding), separate from the binding's quote ``sources``, because
    it is a distinct measurement (an affinity), not a source for the binding node.
    ``check_data.py`` confirms the ``ki_id`` row is really in the corpus CSV.
    """
    ki = binding.get("ki")
    if not ki:
        return None
    what = f"Drug {drug_id!r} binding {binding.get('target')!r} ki"
    for k in ("median", "min", "max"):
        if not isinstance(ki.get(k), (int, float)):
            raise ValueError(f"{what} missing numeric {k!r}")
    src = ki.get("source") or {}
    corpus = src.get("corpus")
    if corpus not in SOURCE_CORPORA:
        raise KeyError(f"{what} source cites unknown corpus {corpus!r}")
    prov = _provenance(src.get("provenance", DEFAULT_PROVENANCE), f"{what} source")
    if prov == "verified" and src.get("ki_id") is None:
        raise ValueError(f"{what} 'verified' source needs a ki_id (the PDSP row id)")
    out_src: dict[str, Any] = {"corpus": corpus, "provenance": prov}
    for f in ("ki_id", "value_nm", "species", "preparation", "radioligand",
              "reference", "note", "mapped", "measured_as", "relation", "pdsp_names"):
        if src.get(f) not in (None, ""):
            out_src[f] = src[f]
    out = {
        "median": ki["median"], "min": ki["min"], "max": ki["max"],
        "n_human": int(ki.get("n_human", 0)),
        "n_nonhuman": int(ki.get("n_nonhuman", 0)),
        "source": out_src,
    }
    # Count of assays excluded as "tested, essentially inactive" (>=10 uM ceiling),
    # so the panel can note the target was probed and found not to bind. Only present
    # when nonzero (fetch_ki writes it that way), so the field stays sparse.
    if ki.get("inactive"):
        out["inactive"] = int(ki["inactive"])
    return out


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

# Half-width of the longitudinal fissure: each cortical lobe's medial face is
# cut flat at world x = +/- this, so the left and right hemispheres meet along a
# thin midline gap instead of overlapping into one ball. Small = tight fissure.
MIDLINE_GAP = 0.06

# --- Cortical dome (SDF) -----------------------------------------------------
# The cerebral cortex is authored as ONE shared right-hemisphere ellipsoid (the
# "cortical mantle"); each lobe is a sector of it carved by shared cut planes, so
# at explode 0 the lobes reassemble into a single continuous dome instead of
# reading as a cluster of separate balls. The gyral relief is a gentle GEOMETRIC
# displace (lumpy silhouette) sampled from one shared WORLD-space fold field, so
# the folds line up across seams; the brainy sulcus ink is still the swirl
# shader on top. (See geometry_refinements/.)
CORTEX_DOME_CENTER = (1.15, 0.55, -0.15)  # world coords, right hemisphere
CORTEX_DOME_RADII = (1.55, 2.0, 3.4)      # M-L, S-I, A-P (anteroposterior longest)
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# Shared lobe-boundary planes (world coords; the listed normal points INTO the
# kept side). Reused across lobes so their cut faces are coincident and the lobes
# abut exactly. The fissures are tilted (oblique) so the seams read like the real
# central / Sylvian fissures, not axis-aligned slabs.
_CENTRAL_PT = (1.15, 0.55, 0.4)      # central sulcus: frontal (anterior) | parietal
_CENTRAL_N_FRONT = (0.0, 0.32, 1.0)  # -> into the frontal side; tilt = slopes forward going down
_SYLVIAN_PT = (1.15, -0.1, 0.2)      # lateral (Sylvian) fissure: fronto-parietal | temporal
_SYLVIAN_N_UP = (0.0, 1.0, 0.18)     # -> into the upper side; tilt = rises posteriorly
_PAR_OCC_Z = -1.9                    # parieto-occipital: occipital is the posterior cap
_TEMPORAL_MEDIAL_X = 0.95            # temporal stays lateral of this parasagittal plane


def _neg(v):
    return (-v[0], -v[1], -v[2])


# The temporal "bite": the region below the Sylvian fissure AND lateral of the
# temporal parasagittal plane. Subtracted from the frontal + parietal lobes so
# they keep their inferomedial / orbital surface (which reaches the base medially)
# while the temporal owns just this lateral inferior wedge (so it no longer slabs
# across the midline). The same plane definitions feed the temporal's own
# intersect, so the shared faces are coincident and the lobes abut.
_TEMPORAL_BITE = [("plane", _neg(_SYLVIAN_N_UP), _SYLVIAN_PT),
                  ("x", ">", _TEMPORAL_MEDIAL_X)]


def _cut_to_plane(cut, pos):
    """One territory cut -> an SDF half-space ``plane`` node (in local coords).

    Two forms (both in WORLD coords; ``local = world - pos``):
      * axis-aligned ``("z", ">", 0.4)`` keeps ``axis > value`` (or ``"<"``);
      * oblique ``("plane", inward_normal, point)`` keeps the half-space the
        inward normal points into.
    Returns ``(plane_node, axis_clamp)`` where ``axis_clamp`` is
    ``(index, side, value)`` for AABB tightening, or ``None`` (oblique: the dome
    AABB already bounds it).
    """
    if cut[0] in _AXIS_INDEX:
        axis, side, value = cut
        i = _AXIS_INDEX[axis]
        normal = [0.0, 0.0, 0.0]
        normal[i] = -1.0 if side == ">" else 1.0
        local_value = value - pos[i]
        offset = -local_value if side == ">" else local_value
        return dict(prim="plane", normal=normal, offset=round(offset, 4)), (i, side, value)
    _, n_in, p = cut
    normal = [-n_in[0], -n_in[1], -n_in[2]]  # sdPlane inside = dot(local, n) < offset
    offset = -sum(n_in[k] * (p[k] - pos[k]) for k in range(3))
    return dict(prim="plane", normal=[round(v, 4) for v in normal], offset=round(offset, 4)), None


def _region_node(region, pos):
    """A set of cuts -> one SDF node that is solid inside their intersection."""
    planes = [_cut_to_plane(c, pos)[0] for c in region]
    return planes[0] if len(planes) == 1 else dict(op="intersect", nodes=planes)


def _cortex_lobe(pos, cuts, *, seed, subtract_regions=None, resolution=92):
    """SDF spec for one cortical lobe: a sector of the shared cortical dome.

    ``cuts`` selects this lobe's territory as the intersection of the dome with a
    set of half-space cuts (see ``_cut_to_plane``). ``subtract_regions`` removes
    further regions (each a list of cuts intersected together) AFTER the
    intersection: this is how the temporal "bite" (below Sylvian AND lateral) is
    carved out of the frontal/parietal lobes so they keep their inferomedial /
    orbital surface while the temporal stays a lateral wedge. The dome ellipsoid,
    its gyral ``displace`` and every plane are translated into the lobe's local
    frame; the displace samples a shared WORLD-space fold field (``origin = pos``)
    so the gyri are continuous across seams. A flat medial wall (world
    ``x = MIDLINE_GAP``) is subtracted last. ``bounds`` is the wedge AABB tightened
    by the axis-aligned cuts (oblique cuts fall back to the dome extent).
    """
    c, r = CORTEX_DOME_CENTER, CORTEX_DOME_RADII
    lo = [c[i] - r[i] for i in range(3)]
    hi = [c[i] + r[i] for i in range(3)]
    lo[0] = max(lo[0], MIDLINE_GAP)  # the medial wall trims the AABB
    plane_nodes = []
    for cut in cuts:
        node, clamp = _cut_to_plane(cut, pos)
        plane_nodes.append(node)
        if clamp:
            i, side, value = clamp
            if side == ">":
                lo[i] = max(lo[i], value)
            else:
                hi[i] = min(hi[i], value)
    dome = dict(prim="ellipsoid",
                center=[round(c[i] - pos[i], 4) for i in range(3)], radii=list(r))
    folded = dict(op="displace", octaves=2, freq=2.2, amp=0.13, unit=1.9, seed=seed,
                  origin=[round(pos[i], 4) for i in range(3)], nodes=[dome])
    wedge = dict(op="intersect", nodes=[folded, *plane_nodes])
    medial = dict(prim="plane", normal=[1.0, 0.0, 0.0],
                  offset=round(MIDLINE_GAP - pos[0], 4))
    cut_nodes = [medial] + [_region_node(rg, pos) for rg in (subtract_regions or [])]
    margin = 0.2  # cover the gyral displace (amp 0.13) pushing past the AABB
    bounds = [[round(lo[i] - pos[i] - margin, 3) for i in range(3)],
              [round(hi[i] - pos[i] + margin, 3) for i in range(3)]]
    return dict(type="sdf", resolution=resolution, bounds=bounds,
                root=dict(op="subtract", nodes=[wedge, *cut_nodes]))


def _cortex_lobe_entry(base, name, color, pos, cuts, seed, subtract_regions=None):
    """A PAIRED cortical-lobe entry whose shape is a sector of the shared dome.

    ``pos`` is written once and threaded into both the entry and the SDF
    local-frame translation, so the two can never drift apart.
    """
    return dict(base=base, name=name, group="lobe", pos=pos, color=color,
                shape=_cortex_lobe(pos, cuts, seed=seed, subtract_regions=subtract_regions))


# name, group, right-side position, color, radii, seed, detail, noise
PAIRED: list[dict[str, Any]] = [
    # --- Cortical lobes (large, outer shell) ---
    # The four main lobes are sectors of ONE shared cortical dome (see
    # _cortex_lobe), carved by planes they share so they reassemble seamlessly at
    # explode 0. The fissures are OBLIQUE (tilted) so the seams read like the real
    # central / Sylvian fissures, not axis-aligned slabs (world coords):
    #   central  through (1.15,0.55,0.4), tilted forward going down -> frontal
    #            (anterior) | parietal (posterior)
    #   Sylvian  through (1.15,-0.1,0.2), rising posteriorly -> fronto-parietal
    #            (above) | temporal (below), but ONLY lateral of x=0.95: the
    #            temporal is a LATERAL inferior wedge (the _TEMPORAL_BITE), so the
    #            frontal+parietal keep their inferomedial / orbital surface and the
    #            temporal no longer slabs across the midline.
    #   par-occ  z = -1.90 -> occipital is the whole posterior cap.
    # Muted pink palette, low saturation so they read as one cortex; each a
    # slightly different hue (frontal=rose, parietal=pink, temporal=salmon,
    # occipital=mauve-pink) so the four stay tellable apart. Provenance: llm.
    _cortex_lobe_entry("frontal", "Frontal lobe", "#c58c9a", (0.85, 1.0, 2.2),
                       [("plane", _CENTRAL_N_FRONT, _CENTRAL_PT), ("z", ">", -0.7)], 11,
                       subtract_regions=[_TEMPORAL_BITE]),
    _cortex_lobe_entry("parietal", "Parietal lobe", "#c69597", (0.85, 1.8, -0.2),
                       [("plane", _neg(_CENTRAL_N_FRONT), _CENTRAL_PT),
                        ("z", ">", -1.9), ("z", "<", 1.3)], 12,
                       subtract_regions=[_TEMPORAL_BITE]),
    _cortex_lobe_entry("temporal", "Temporal lobe", "#c79a8e", (2.1, -0.75, 0.6),
                       [("plane", _neg(_SYLVIAN_N_UP), _SYLVIAN_PT),
                        ("z", ">", -1.9), ("x", ">", _TEMPORAL_MEDIAL_X),
                        ("y", "<", 0.5)], 13),
    _cortex_lobe_entry("occipital", "Occipital lobe", "#bf8da6", (0.72, 0.75, -2.9),
                       [("z", "<", -1.9)], 14),
    dict(base="insula", name="Insula", group="lobe", fr_gender="f",
         pos=(1.95, 0.3, 0.5), color="#ae7aa3",
         # The hidden 5th lobe: insular cortex buried deep to the lateral
         # (Sylvian) sulcus, overlying the putamen. Now that the four big lobes
         # are SOLID dome sectors abutting at the Sylvian plane (no lateral gap),
         # the deep nuclei are already covered, so the insula only has to (a) stay
         # buried INSIDE the cortical surface at explode 0 and (b) read as a small
         # gyrified patch when the lobes blow apart. A mediolaterally-thin SDF
         # ellipsoid with gentle gyri: its lateral edge sits at x ~ 2.35, inside
         # the cortex (whose gyral troughs here reach ~2.5), so it no longer pokes
         # out. It reveals laterally on explode (pos is the radial anchor).
         shape=dict(type="sdf", resolution=64,
                    bounds=[[-0.6, -1.2, -1.35], [0.6, 1.2, 1.35]],
                    root=dict(op="displace", octaves=2, freq=2.6, amp=0.1,
                              unit=1.1, seed=15,
                              nodes=[dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                                          radii=[0.4, 0.95, 1.1])]))),
    # --- Basal ganglia & deep nuclei (small, inner) ---
    dict(base="caudate", name="Caudate nucleus", group="basal_ganglia",
         # Retracted (y was 1.9, an earlier "emerge through the fronto-parietal
         # seam" experiment) so the bulbous head now sits below the cortical
         # surface and stays hidden inside the assembled brain at explode 0,
         # surfacing only as the lobes blow apart: anatomically deeper and no
         # longer poking out between the lobes.
         pos=(1.2, 1.1, 0.8), color="#ff9da7",
         scale=(0.95, 0.67, 0.66),  # anatomical: ~14x38x42mm (was too tall/long)
         # SDF (self-authored atlas, see geometry_refinements/). The caudate is
         # the comma/tadpole of the basal ganglia, wrapping over + behind the
         # thalamus along the lateral ventricle: a large BULBOUS HEAD (anterior +
         # superior, bulging into the frontal horn), the body arching up + back
         # over the thalamus, then a long WISPY TAIL descending at the back and
         # hooking down + forward into the temporal lobe (toward the amygdala).
         # Modeled as a slim tapered `tube` on a 3D comma spline (the tail swings
         # gently LATERAL as it dives into the temporal horn, so no orthogonal
         # view collapses to a flat C) smooth-unioned with a distinct head bulb,
         # under a light displace. Mirroring negates x, so the _L tail swings
         # lateral on the left too. Authored in local space (z anterior+, y
         # superior+); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=112,
             bounds=[[-0.42, -1.45, -1.35], [0.52, 1.2, 1.6]],
             root=dict(op="displace", amp=0.006, freq=5.0, seed=21, nodes=[
                 dict(op="smoothUnion", k=0.12, nodes=[
                     # Body + tail: slim tube tapering head -> wispy tail along the
                     # comma; the head end is modest (the bulb below adds the heft).
                     # The tail descends the posterior wall then HOOKS DOWNWARD into
                     # the temporal horn (it does NOT run forward under the head), so
                     # the comma's opening faces INFERIOR, not anterior.
                     dict(prim="tube",
                          points=[
                              [0.0, 0.45, 0.92],    # head/body junction (anterior)
                              [0.02, 0.72, 0.58],   # body rising
                              [0.05, 0.88, 0.15],
                              [0.07, 0.93, -0.30],  # arch peak (superior)
                              [0.10, 0.82, -0.70],  # starting to descend
                              [0.15, 0.45, -1.00],  # descending posterior, swinging lateral
                              [0.20, -0.12, -1.08], # down the posterior wall (most posterior)
                              [0.23, -0.66, -0.90], # rounding the back-bottom corner
                              [0.22, -1.00, -0.45], # into the temporal horn, well below the body
                              [0.18, -1.10, 0.08],  # tail running forward along the horn floor
                              [0.14, -1.28, 0.34],  # tail tip hooking DOWN (caudal extremity)
                          ],
                          profile=[0.18, 0.165, 0.155, 0.15, 0.14, 0.125,
                                   0.105, 0.085, 0.065, 0.05, 0.035]),
                     # Bulbous head: a tall ovoid (taller than wide, per the front
                     # view) bulging anterosuperiorly into the frontal horn.
                     dict(prim="ellipsoid", center=[0.0, 0.42, 1.06],
                          radii=[0.30, 0.44, 0.40]),
                 ]),
             ])),
         ),
    dict(base="putamen", name="Putamen", group="basal_ganglia",
         pos=(1.9, 0.2, 0.6), color="#f28e2b",
         scale=(0.69, 0.48, 0.55),  # anatomical: ~14x24x32mm (was ~2x too tall)
         # SDF (self-authored atlas, see geometry_refinements/). The putamen is
         # the most lateral basal nucleus: a rounded lens/shell flattened
         # mediolaterally (thin x), taller (y) and deep (z), gently scalloped on
         # its medial face where the globus pallidus nests. Authored in local
         # space (centered on origin); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             root=dict(op="displace", amp=0.018, freq=3.2, seed=22, nodes=[
                 dict(op="subtract", k=0.18, nodes=[
                     # Lens body, nudged a touch lateral so the medial scoop bites
                     # the inner face, not the centre.
                     dict(prim="ellipsoid", center=[0.06, 0, 0],
                          radii=[0.45, 1.05, 1.2]),
                     # Scoop the medial (-x) face concave, cradling the globus
                     # pallidus that nests against it.
                     dict(prim="sphere", center=[-1.18, 0.0, -0.1], radius=0.95),
                 ]),
             ]),
         )),
    dict(base="globus_pallidus", name="Globus pallidus", group="basal_ganglia",
         pos=(1.5, 0.0, 0.2), color="#76b7b2",
         scale=(0.5, 0.65, 0.8),  # anatomical: ~10x16x20mm
         # SDF (self-authored atlas, see geometry_refinements/). The inner, medial
         # part of the lentiform nucleus: a WEDGE/cone tapering to a medial apex
         # (pointing toward the internal capsule / thalamus) with a convex lateral
         # face nesting into the putamen's medial scoop. Modeled as a
         # medially-tapering roundcone (the wedge taper) intersected with a tall,
         # AP-extended ellipsoid (the envelope + convex lateral face), the join
         # rounded by smoothIntersect, under a light displace. Together with the
         # putamen it reads as the lens-shaped lentiform nucleus. Authored in local
         # space (x lateral+); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             root=dict(op="displace", amp=0.012, freq=3.4, seed=23, nodes=[
                 dict(op="smoothIntersect", k=0.1, nodes=[
                     # Mediolateral taper: fat lateral end -> pointed medial apex.
                     dict(prim="roundcone", a=[0.3, 0.0, 0.0], r1=0.55,
                          b=[-0.5, 0.0, 0.0], r2=0.1),
                     # Tall, AP-extended envelope (convex lateral face for the scoop).
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                          radii=[0.42, 0.72, 0.82]),
                 ]),
             ])),
         ),
    dict(base="thalamus", name="Thalamus", group="basal_ganglia",
         pos=(0.9, 0.4, -0.6), color="#bab0ac",
         scale=(0.87, 0.77, 0.62),  # anatomical: ~25x22x32mm (AP was too long)
         # SDF (self-authored atlas, see geometry_refinements/). The biggest deep
         # nucleus: an elongated EGG with a narrower anterior pole (the anterior
         # tubercle) and a bulbous posterior PULVINAR overhanging the geniculate
         # bodies, the long axis running anteromedial -> posterolateral. Modeled as
         # a main ovoid smooth-unioned with a posterolateral pulvinar sphere
         # (asymmetry = the egg taper + the tilt), under a light displace; the
         # anterior ellipsoid is nudged medial, the pulvinar lateral. Mirroring
         # negates x, so the _L tilt is correct on the left. Authored in local
         # space (z anterior+, x lateral+); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             # A single tapered roundcone = a clean teardrop egg (narrow rounded
             # anterior pole -> bulbous posterior pulvinar), no fused-balls waist.
             # The axis is tilted anteromedial(up) -> posterolateral(down).
             root=dict(op="displace", amp=0.012, freq=3.0, seed=24, nodes=[
                 dict(prim="roundcone",
                      a=[-0.07, 0.04, 0.66], r1=0.39,    # anterior pole (narrow)
                      b=[0.10, -0.04, -0.53], r2=0.60),  # posterior pulvinar (bulbous)
             ])),
         ),
    dict(base="subthalamic_nucleus", name="Subthalamic nucleus",
         group="basal_ganglia",
         pos=(0.75, -0.35, -0.55), color="#d37295",
         scale=0.3,  # anatomical: a tiny ~5-7mm lens (was ~4x too big)
         # SDF (self-authored atlas, see geometry_refinements/). The tiny biconvex
         # LENS (lentil) of the subthalamus: two large spheres offset along the
         # thin (DV) axis, intersected so their overlap is a lens with a crisp
         # equatorial edge (the lens character a rounded ellipsoid lacks), then
         # clipped by an AP-elongated ellipsoid so it is longer front-to-back than
         # wide, under a faint displace; res 60. Authored in local space (y thin);
         # `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=60,
             root=dict(op="displace", amp=0.008, freq=4.5, seed=25, nodes=[
                 dict(op="smoothIntersect", k=0.05, nodes=[
                     dict(prim="sphere", center=[0.0, 0.55, 0.0], radius=0.78),
                     dict(prim="sphere", center=[0.0, -0.55, 0.0], radius=0.78),
                     # AP-elongated, ML-narrow clip (the lens outline).
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                          radii=[0.34, 0.5, 0.54]),
                 ]),
             ])),
         ),
    dict(base="substantia_nigra", name="Substantia nigra",
         group="basal_ganglia", fr_gender="f",
         pos=(0.55, -0.6, -0.6), color="#3d3d3d",
         scale=(0.6, 0.45, 0.45),  # anatomical: a thin ~9x5x17mm band
         # SDF (self-authored atlas, see geometry_refinements/). A thin, gently
         # CURVED lamina in the midbrain hugging the back of the cerebral peduncle
         # (concave anteromedially), not a flat lens. Modeled as three flattened
         # (thin-DV) ellipsoids smooth-unioned along an antero-posterior arc whose
         # middle is bowed laterally, so the band is concave toward the midline,
         # under a light displace; res 64. Mirroring negates x, so the _L band is
         # concave-medial too. Authored in local space (z anterior+, x lateral+,
         # y thin); `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.01, freq=4.0, seed=26, nodes=[
                 dict(op="smoothUnion", k=0.30, nodes=[
                     dict(prim="ellipsoid", center=[0.06, 0.03, -0.44],
                          radii=[0.34, 0.16, 0.34]),   # posterior end
                     dict(prim="ellipsoid", center=[0.22, 0.0, 0.0],
                          radii=[0.36, 0.16, 0.34]),   # middle, bowed lateral
                     dict(prim="ellipsoid", center=[0.06, -0.03, 0.44],
                          radii=[0.32, 0.16, 0.32]),   # anterior end
                 ]),
             ])),
         ),
    dict(base="accumbens", name="Nucleus accumbens", group="basal_ganglia",
         pos=(0.95, -0.5, 1.0), color="#e0997e",
         scale=(0.5, 0.32, 0.42),  # anatomical: ~10x9x8mm (was ~3x too tall)
         # SDF (self-authored atlas, see geometry_refinements/). Ventral striatum,
         # where the head of the caudate meets the putamen ventrally and anteriorly
         # (the reward hub, target of the mesolimbic dopamine pathway). It has no
         # distinctive standalone silhouette: a rounded mass that is the inferior
         # corner of the striatum, so it is modeled as a gentle TEARDROP, a
         # roundcone fat at the free ventral pole tapering dorsally (and slightly
         # posterolateral) into the striatum, under a light displace; res 64.
         # Position is an anatomical guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.012, freq=3.6, seed=27, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, -0.28, 0.10], r1=0.42,   # fat ventral pole
                      b=[0.06, 0.40, -0.16], r2=0.16),  # taper up into the striatum
             ])),
         ),
    dict(base="claustrum", name="Claustrum", group="basal_ganglia",
         pos=(2.3, 0.1, 0.5), color="#8d97ab",
         scale=0.62,  # anatomical: a thin curved ~4x21x28mm sheet, seated medial
         # to the insula (was poking out lateral to it). Uniform on purpose: this is
         # a spherical-shell construction whose surface sits at (center + radius), so
         # anisotropic scaling (center per-axis, scalar radius by the mean) would
         # slide the shell off its bounds and mesh to nothing.
         # SDF (self-authored atlas, see geometry_refinements/). A thin, gently
         # curved vertical lamina of grey matter between the insula (lateral) and
         # the putamen (medial): a thin spherical SHELL (so it is curved, concave
         # toward the medial putamen it drapes over, not a flat slab) clipped by an
         # ellipsoid to the claustrum's tall, narrow y/z patch. Explicit tight
         # bounds keep the ~0.09-thick sheet well-resolved cheaply. Authored in
         # local space; `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=96,
             bounds=[[-0.25, -0.95, -1.2], [0.25, 0.95, 1.2]],
             # smoothIntersect rounds the thin shell-meets-clip rim (a hard
             # intersect leaves a shallow-angle edge that marching cubes steps).
             root=dict(op="smoothIntersect", k=0.06, nodes=[
                 # ~0.09-thick curved shell (outer ~x=0.06, inner ~x=-0.03).
                 dict(op="subtract", nodes=[
                     dict(prim="sphere", center=[-2.3, 0, 0], radius=2.36),
                     dict(prim="sphere", center=[-2.3, 0, 0], radius=2.27),
                 ]),
                 # Clip the shell to the claustrum's tall, narrow patch.
                 dict(prim="ellipsoid", center=[0, 0, 0], radii=[1.0, 0.72, 0.95]),
             ]),
         )),
    # --- Limbic / diencephalon ---
    dict(base="hippocampus", name="Hippocampus", group="limbic",
         pos=(1.3, -0.7, -0.2), color="#b3823e",
         scale=(0.95, 0.6, 0.8),  # anatomical: ~15x24x40mm (was too tall)
         # SDF (self-authored atlas, see geometry_refinements/). Curved
         # allocortical "seahorse" in the floor of the temporal lobe, swept on a
         # genuinely 3D spline so no orthogonal view collapses to a bulb-on-a-shaft:
         #   - sagittal (y-z): a strong comma. Head hooks down + under at the
         #     antero-inferior tip; body sweeps up + posterior; tail hooks up +
         #     forward toward the splenium.
         #   - transverse (x): head sits LATERAL, the body/tail curve MEDIALLY as
         #     they run back (the paired tails converge toward the splenium). This
         #     is what makes the front/top silhouettes read as a curved form, and it
         #     is anatomically right. Mirroring negates x, so the _L member curves
         #     the other way (correct: its head is lateral on the left).
         # Slender (length >> caliber, the head only modestly wider than the body).
         # Anatomical detail: a beaded dentate-gyrus ridge along the inferomedial
         # edge (the "teeth" the dentate is named for), three pes digitations, all
         # under a light displace so the detail survives. Authored in local space;
         # `pos` seats it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=112,
             root=dict(op="displace", amp=0.006, freq=5.5, seed=51, nodes=[
                 # Outer join: hang the dentate beads off the body as distinct teeth.
                 dict(op="smoothUnion", k=0.045, nodes=[
                     dict(op="smoothUnion", k=0.10, nodes=[
                         # Slim tapered body on the 3D comma spline.
                         dict(prim="tube",
                              points=[
                                  [0.20, -0.50, 1.02],   # head: lateral + anterior + inferior
                                  [0.16, -0.60, 0.64],   # head curls under (lowest)
                                  [0.08, -0.46, 0.24],   # body rising + going medial
                                  [-0.02, -0.16, -0.18],
                                  [-0.10, 0.20, -0.54],  # sweeping medial + up + posterior
                                  [-0.13, 0.52, -0.82],  # tail
                                  [-0.10, 0.82, -0.66],  # tail tip hooks up + forward
                              ],
                              profile=[0.13, 0.15, 0.16, 0.145, 0.125, 0.095, 0.055]),
                         # Pes hippocampi: small flattened base paw + three finger-like
                         # digitations fanned around the lateral head tip (tight k ->
                         # distinct bumps).
                         dict(op="smoothUnion", k=0.05, nodes=[
                             dict(prim="ellipsoid", center=[0.16, -0.52, 0.78],
                                  radii=[0.15, 0.12, 0.18]),
                             dict(prim="sphere", center=[0.06, -0.57, 0.97], radius=0.09),
                             dict(prim="sphere", center=[0.17, -0.61, 1.03], radius=0.095),
                             dict(prim="sphere", center=[0.28, -0.57, 0.96], radius=0.09),
                         ]),
                     ]),
                     # Dentate-gyrus beading: a row of small spheres along the
                     # inferomedial (-x, -y) edge of the body, from anterior body to
                     # tail; the tight outer k=0.045 keeps them as a scalloped ridge.
                     dict(prim="sphere", center=[0.02, -0.54, 0.30], radius=0.075),
                     dict(prim="sphere", center=[-0.06, -0.34, 0.06], radius=0.075),
                     dict(prim="sphere", center=[-0.14, -0.10, -0.22], radius=0.07),
                     dict(prim="sphere", center=[-0.19, 0.16, -0.48], radius=0.07),
                     dict(prim="sphere", center=[-0.22, 0.38, -0.68], radius=0.065),
                     dict(prim="sphere", center=[-0.20, 0.56, -0.82], radius=0.055),
                 ]),
             ]),
         )),
    dict(base="amygdala", name="Amygdala", group="limbic", fr_gender="f",
         pos=(1.45, -0.35, 0.95), color="#9b7bb0",
         scale=(0.75, 0.5, 0.6),  # anatomical: an ~14x12x18mm almond
         # SDF (self-authored atlas, see geometry_refinements/). The ALMOND
         # (amygdala = "almond"): an elongated nut, rounded and fat at its
         # antero-superior pole, tapering postero-inferiorly to a blunter point
         # where it caps the head of the hippocampus, in the medial temporal lobe
         # (emotion/fear hub). Modeled as a roundcone (tapered capsule) along that
         # AS -> PI axis, under a light displace; res 64. Sits inside the temporal
         # lobe at explode 0. Position is an anatomical guess: tune in a browser.
         # Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.012, freq=3.4, seed=54, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, 0.14, 0.30], r1=0.40,    # fat antero-superior pole
                      b=[0.06, -0.26, -0.34], r2=0.22),  # blunt postero-inferior tip
             ])),
         ),
    dict(base="cingulate", name="Cingulate gyrus", group="limbic",
         pos=(0.5, 0.6, 0.0), color="#6fa39c",
         # SDF (self-authored atlas, see geometry_refinements/). The limbic-lobe
         # arch: a C-shaped band of cortex on the medial wall, curving over the
         # corpus callosum from the subgenual front, up and over, to the splenial
         # back. A GYRUS is a ribbon, not a worm, so it is modeled as a swept tube
         # along the parasagittal (local x~0) arch INTERSECTED with a thin-x slab:
         # the result is a flattened band, thin mediolaterally (~0.22) and tall
         # radially (the tube diameter), reading as the gyrus it is. Under a gentle
         # displace; res 100 to resolve the thin ribbon over the long arch. Hugs the
         # midline (small pos.x); the _L member mirrors it. Position is a guess:
         # tune in a browser, especially against the (commissural) corpus-callosum
         # arrow. Provenance: llm.
         shape=dict(
             type="sdf", resolution=100,
             bounds=[[-0.26, -0.95, -1.72], [0.26, 1.62, 1.72]],
             root=dict(op="displace", amp=0.02, freq=2.6, seed=55, nodes=[
                 dict(op="intersect", nodes=[
                     dict(prim="tube",
                          points=[
                              [0.0, -0.5, 1.3],    # subgenual, anterior + low
                              [0.0, 0.4, 1.5],     # rising in front of the genu
                              [0.0, 1.0, 0.95],    # anterior arch
                              [0.0, 1.2, 0.0],     # top of the arch
                              [0.0, 1.0, -0.95],   # posterior arch
                              [0.0, 0.3, -1.5],    # descending toward the splenium
                              [0.0, -0.45, -1.25],  # isthmus, posterior + low
                          ],
                          profile=[0.18, 0.3, 0.34, 0.34, 0.32, 0.28, 0.18]),
                     # thin-x slab: flattens the round tube into a gyrus ribbon.
                     dict(prim="box", center=[0.0, 0.35, 0.0],
                          half=[0.11, 1.25, 1.65], round=0.02),
                 ]),
             ])),
         ),
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
         scale=(0.6, 0.6, 1.0),  # anatomical: thin bulb+tract, ~5mm wide (was too fat)
         # SDF (self-authored atlas, see geometry_refinements/). A match-stick on
         # the orbital underside of the frontal lobe: a swollen anterior BULB (on
         # the cribriform plate) tapering into a thin posterior olfactory TRACT that
         # rises gently as it runs back toward the brain. Modeled as an ovoid bulb
         # smooth-unioned with a slender tapered roundcone tract, under a faint
         # displace; res 80, tight bounds to resolve the thin tract. Near the
         # midline. Position is a guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             bounds=[[-0.26, -0.26, -0.62], [0.26, 0.30, 0.56]],
             root=dict(op="displace", amp=0.008, freq=5.0, seed=57, nodes=[
                 dict(op="smoothUnion", k=0.10, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.22],
                          radii=[0.19, 0.18, 0.24]),     # the bulb (anterior)
                     dict(prim="roundcone",
                          a=[0.0, 0.0, 0.10], r1=0.11,
                          b=[0.0, 0.06, -0.50], r2=0.05),  # the tract (posterior)
                 ]),
             ])),
         ),
    dict(base="septal_nuclei", name="Septal nuclei", group="limbic", fr_gender="mp",
         pos=(0.3, 0.1, 0.85), color="#7f9cc0",
         scale=(0.9, 0.6, 0.9),  # anatomical: small paramedian nuclei, ~10mm (was tall)
         # SDF (self-authored atlas, see geometry_refinements/). Small paramedian
         # grey matter below the rostrum of the corpus callosum, anterior to the
         # thalamus and above the hypothalamus (a Papez/limbic relay). It has no
         # distinctive silhouette: a small ovoid set in the thin septal wall, so it
         # is a vertical ellipsoid flattened mediolaterally (thin in x), under a
         # faint displace; res 56. Near the midline. Position is a guess: tune in a
         # browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=56,
             root=dict(op="displace", amp=0.01, freq=4.0, seed=58, nodes=[
                 dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                      radii=[0.20, 0.34, 0.22]),
             ])),
         ),
    dict(base="hypothalamus", name="Hypothalamus", group="diencephalon",
         pos=(0.45, -0.45, 0.3), color="#c98ac9",
         scale=(0.6, 0.45, 0.5),  # anatomical: a small ~11x10x12mm region
         # SDF (self-authored atlas, see geometry_refinements/). Small nucleus
         # cluster below and anterior to the thalamus, forming the floor + lower
         # walls of the third ventricle (hugs the midline, small pos.x). Its
         # characteristic feature is the INFUNDIBULAR FUNNEL: the floor (tuber
         # cinereum / median eminence) tapers downward and medially toward the
         # midline pituitary stalk. Modeled as a rounded mass smooth-unioned with a
         # short inferior funnel angled medially, under a light displace; res 72.
         # The mirrored _L funnel angles the other way, so the pair converges on the
         # midline. Position is a guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             root=dict(op="displace", amp=0.012, freq=3.2, seed=52, nodes=[
                 dict(op="smoothUnion", k=0.14, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.06, 0.0],
                          radii=[0.38, 0.34, 0.50]),       # the bulk
                     dict(prim="roundcone",
                          a=[0.0, -0.16, 0.04], r1=0.20,
                          b=[-0.22, -0.46, 0.04], r2=0.08),  # infundibular funnel
                 ]),
             ])),
         ),
    dict(base="mammillary", name="Mammillary bodies", group="diencephalon", fr_gender="mp",
         pos=(0.35, -0.8, -0.2), color="#c6b06a",
         scale=0.55,  # anatomical: pea-sized ~5mm bodies
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
         pos=(0.3, -1.0, -0.95), color="#4a7fae",
         scale=(0.4, 1.0, 0.4),  # anatomical: thin ~2mm column; moved into the upper pons
         # SDF (self-authored atlas, see geometry_refinements/). "The blue spot":
         # the brain's main noradrenaline source, a thin ROD of cells in the dorsal
         # rostral pons (floor of the 4th ventricle). Modeled as a slim vertical
         # capsule (a roundcone with equal end radii) so it reads as the pencil-line
         # column it is, faint displace; res 56. Coloured blue as a nod to its name.
         # Carries the alpha-2 autoreceptors. Sits inside/behind the brainstem at
         # explode 0. Provenance: llm.
         shape=dict(
             type="sdf", resolution=56,
             root=dict(op="displace", amp=0.006, freq=5.0, seed=82, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, -0.17, 0.0], r1=0.10,
                      b=[0.0, 0.17, 0.0], r2=0.085),  # slim near-vertical rod
             ])),
         ),
    dict(base="vta", name="Ventral tegmental area", group="brainstem_nuclei",
         fr_gender="f",
         pos=(0.3, -0.6, -0.5), color="#6cab5d",
         scale=0.4,  # anatomical: ~5mm midbrain nucleus; moved into the rescaled midbrain
         # The midbrain dopamine source medial to the substantia nigra; origin of
         # the mesolimbic / mesocortical pathways (reward, D2 autoreceptors).
         # Small smooth blob, dopamine-green to echo the dopaminergic arrows.
         radii=(0.26, 0.2, 0.3), seed=83, detail=5, noise=0.05),
]

# Midline structures (emitted once, no hemisphere suffix)
MIDLINE: list[dict[str, Any]] = [
    dict(base="pituitary", name="Pituitary gland", group="diencephalon",
         pos=(0.0, -1.0, 0.35), color="#d2a06e",
         scale=(0.9, 0.5, 0.7),  # anatomical: ~10x9x6mm (bean-sized)
         # SDF (self-authored atlas, see geometry_refinements/). The defining shape
         # is GLAND-ON-A-STALK: a small bean-shaped gland (wider mediolaterally than
         # tall) seated in the sella turcica, with a thin INFUNDIBULAR STALK rising
         # from its top toward the hypothalamus above. Modeled as a bean ellipsoid
         # smooth-unioned with a slender tapered roundcone stalk, under a faint
         # displace; res 72, tight bounds for the thin stalk. Midline (no mirror).
         # Hides centrally at explode 0, revealed on blow-out. Position is a guess:
         # tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=72,
             bounds=[[-0.28, -0.28, -0.28], [0.28, 0.62, 0.30]],
             root=dict(op="displace", amp=0.008, freq=5.0, seed=72, nodes=[
                 dict(op="smoothUnion", k=0.08, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.0, 0.0],
                          radii=[0.22, 0.18, 0.20]),       # the bean gland
                     dict(prim="roundcone",
                          a=[0.0, 0.10, 0.04], r1=0.07,
                          b=[0.0, 0.50, 0.0], r2=0.05),     # infundibular stalk
                 ]),
             ])),
         ),
    dict(base="cerebellum", name="Cerebellum", group="hindbrain",
         pos=(0.0, -1.55, -3.3), color="#b07aa1",
         scale=(0.88, 0.85, 0.74),  # anatomical: ~103x48x55mm (was a bit large/deep)
         # SDF (self-authored atlas, see geometry_refinements/). The cerebellum's
         # "butterfly": two hemispheres flanking a narrower, slightly taller central
         # VERMIS, smooth-unioned into ONE continuous mass (soft paravermian valleys,
         # not three separate balls). The signature transverse FOLIA are PAINTED ON,
         # not carved: `pattern="folia"` tells the viewer to cel-shade it like the
         # cortex and ink stacked near-horizontal fold lines (CEREBELLUM_FOLIA in
         # shapes.js). So the geometry stays a cheap SMOOTH mass (only a faint
         # displace for an organic surface) at a modest ISOTROPIC resolution, instead
         # of the costly ridged displace + anisotropic [Nx,Ny,Nz] grid the carved
         # folia needed. Sits below/behind the occipital lobes (under the tentorium)
         # with the brainstem in front of it. Provenance: llm.
         shape=dict(
             type="sdf", resolution=56, pattern="folia",
             bounds=[[-2.65, -1.40, -1.78], [2.65, 1.40, 1.78]],
             root=dict(op="displace", amp=0.03, freq=2.6, octaves=1,
                       unit=1.0, seed=31, nodes=[
                 dict(op="smoothUnion", k=0.35, nodes=[
                     dict(prim="ellipsoid", center=[-1.12, 0.0, 0.0],
                          radii=[1.33, 1.0, 1.5]),     # left hemisphere
                     dict(prim="ellipsoid", center=[1.12, 0.0, 0.0],
                          radii=[1.33, 1.0, 1.5]),     # right hemisphere
                     dict(prim="ellipsoid", center=[0.0, 0.0, -0.08],
                          radii=[0.46, 1.2, 1.5]),     # vermis (narrow, taller ridge)
                 ]),
             ]))),
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
         pos=(0.0, -0.51, -0.66), color="#9c755f",
         scale=(0.74, 0.4, 0.7),  # anatomical: short ~18-20mm segment (was ~55mm tall)
         # SDF (self-authored atlas, see geometry_refinements/). Top brainstem
         # segment, continuous with the diencephalon/thalamus above. Its signature
         # is the dorsal TECTAL (quadrigeminal) PLATE: four colliculi, the superior +
         # inferior pair each side, bulging posteriorly (toward the cerebellum).
         # Modeled as a vertical roundcone body (narrower at the top, widening down
         # to meet the pons) smooth-unioned with four small colliculus spheres on the
         # posterior (-z) dorsal surface, under a light displace; res 80. Midline.
         # Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             root=dict(op="displace", amp=0.012, freq=3.2, seed=32, nodes=[
                 dict(op="smoothUnion", k=0.12, nodes=[
                     dict(prim="roundcone",
                          a=[0.0, 0.70, -0.08], r1=0.44,    # top, under the thalamus
                          b=[0.0, -0.60, 0.10], r2=0.56),   # tail, meeting the pons
                     # tectal plate: superior + inferior colliculi, both sides.
                     dict(prim="sphere", center=[0.20, 0.18, -0.40], radius=0.17),
                     dict(prim="sphere", center=[-0.20, 0.18, -0.40], radius=0.17),
                     dict(prim="sphere", center=[0.18, -0.16, -0.46], radius=0.15),
                     dict(prim="sphere", center=[-0.18, -0.16, -0.46], radius=0.15),
                 ]),
             ])),
         ),
    dict(base="pons", name="Pons", group="hindbrain",
         pos=(0.0, -1.43, -0.45), color="#8c6a58",
         scale=0.87,  # anatomical: ~27mm tall (already close); raised to meet midbrain
         # SDF (self-authored atlas, see geometry_refinements/). Middle brainstem
         # segment, the fullest. Its defining feature is the BASIS PONTIS: a rounded
         # belly bulging ANTERIORLY (+z) that a radially-symmetric curve tube cannot
         # make. Modeled as a body ellipsoid (wider mediolaterally, tapering up/down
         # to meet the midbrain + medulla) smooth-unioned with an anterior belly
         # ellipsoid, under a light displace; res 80. Midline. Provenance: llm.
         shape=dict(
             type="sdf", resolution=80,
             root=dict(op="displace", amp=0.014, freq=3.0, seed=33, nodes=[
                 dict(op="smoothUnion", k=0.30, nodes=[
                     dict(prim="ellipsoid", center=[0.0, 0.0, -0.05],
                          radii=[0.72, 0.64, 0.46]),       # body
                     dict(prim="ellipsoid", center=[0.0, -0.05, 0.30],
                          radii=[0.60, 0.50, 0.36]),       # anterior belly
                 ]),
             ])),
         ),
    dict(base="medulla", name="Medulla", group="hindbrain",
         pos=(0.0, -2.61, -0.75), color="#7d5f4e",
         scale=(0.74, 0.55, 0.8),  # anatomical: ~30mm tall (was ~55mm); raised to meet pons
         # SDF (self-authored atlas, see geometry_refinements/). Bottom brainstem
         # segment, narrowing toward the spinal cord. Its ventral surface carries the
         # two PYRAMIDS (longitudinal ridges flanking the anterior median fissure)
         # and, ventrolaterally on the upper medulla, the OLIVES (the inferior
         # olivary bumps). Modeled as a vertical roundcone body (tapering down to the
         # cord) smooth-unioned with two ventral pyramid ridges (slim roundcones) +
         # two olive ellipsoids, under a light displace; res 84. Midline.
         # Provenance: llm.
         shape=dict(
             type="sdf", resolution=84,
             root=dict(op="displace", amp=0.012, freq=3.4, seed=34, nodes=[
                 dict(op="smoothUnion", k=0.10, nodes=[
                     dict(prim="roundcone",
                          a=[0.0, 0.72, 0.14], r1=0.52,     # head, meeting the pons
                          b=[0.0, -0.72, -0.08], r2=0.32),  # tail, toward the cord
                     # ventral pyramids (paramedian longitudinal ridges).
                     dict(prim="roundcone", a=[0.16, 0.55, 0.36], r1=0.13,
                          b=[0.14, -0.60, 0.24], r2=0.10),
                     dict(prim="roundcone", a=[-0.16, 0.55, 0.36], r1=0.13,
                          b=[-0.14, -0.60, 0.24], r2=0.10),
                     # olives (ventrolateral, upper medulla).
                     dict(prim="ellipsoid", center=[0.40, 0.22, 0.14],
                          radii=[0.16, 0.26, 0.18]),
                     dict(prim="ellipsoid", center=[-0.40, 0.22, 0.14],
                          radii=[0.16, 0.26, 0.18]),
                 ]),
             ])),
         ),
    dict(base="raphe", name="Raphe nuclei", group="brainstem_nuclei", fr_gender="mp",
         pos=(0.0, -1.5, -0.6), color="#b98ac9",
         scale=(0.5, 1.2, 0.5),  # anatomical: thin midline column spanning the brainstem
         # SDF (self-authored atlas, see geometry_refinements/). The brain's
         # serotonin source: a midline COLUMN of nuclei running the length of the
         # brainstem (the seam, "raphe"). Modeled as a slim vertical capsule (a
         # roundcone with near-equal end radii) hugging the midline so it reads as
         # the continuous column it is, faint displace; res 64. Emitted once, never
         # mirrored. Carries the 5-HT1A somatodendritic autoreceptors. Position/size
         # are a guess: tune in a browser. Provenance: llm.
         shape=dict(
             type="sdf", resolution=64,
             root=dict(op="displace", amp=0.008, freq=4.5, seed=81, nodes=[
                 dict(prim="roundcone",
                      a=[0.0, -0.48, 0.0], r1=0.13,
                      b=[0.0, 0.48, 0.0], r2=0.11),  # tall slim midline column
             ])),
         ),
]

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
    "5ht2b": _stahl_ess(131,
        "Presynaptic serotonin (5HT) receptors include 5HT1A, 5HT1B/D, and 5HT2B, "
        "all of which act as autoreceptors"),
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
    # 5-HT1B/D: "inhibitory ... G-protein-coupled" (record synaptic="both", quote
    # says only postsynaptic, so `synaptic` is left unsourced).
    "5ht1b": _FCG, "5ht1d": _FCG,
    # Pure NE enumeration: only names the family, nothing mechanistic.
    "alpha1a": _F, "alpha1b": _F, "alpha1c": _F, "alpha1d": _F,
    "alpha2b": _F, "alpha2c": _F, "beta1": _F, "beta2": _F, "beta3": _F,
    # 5-HT sign sentence: family + the excitatory/inhibitory sign it lists.
    "5ht1a": _FG, "5ht2a": _FG, "5ht2c": _FG, "5ht4": _FG, "5ht5a": _FG, "5ht6": _FG,
    # 5-HT2B quote calls it a *presynaptic autoreceptor*, contradicting the record's
    # postsynaptic value, so only family is backed (see the note above).
    "5ht2b": _F,
    # "5HT7 receptors are postsynaptic, excitatory": family + sign + site.
    "5ht7": _FGY,
    # Opioid "synapse with postsynaptic sites": family + site.
    "mu": _FY, "delta": _FY, "kappa": _FY,
    # CB1 "presynaptic ... inhibition of release" but record sign="modulatory", so
    # only the presynaptic site is backed, not the sign.
    "cb1": _FY,
    # Existence-only / enumeration quotes: family alone.
    "a2a": _F, "sigma1": _F, "mt1": _F, "mt2": _F, "h4": _F,
    # H3 "presynaptic autoreceptors": family + site.
    "h3": _FY,
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
    "vmat2": _stahl_ess(269,
        "After synthesis, NE is packaged into synaptic vesicles via the vesicular "
        "monoamine transporter 2 (VMAT2) and stored there until its release into "
        "the synapse during neurotransmission."),
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
# Manual per-target polarity-grade overrides (mirror TARGET_PROVENANCE). Empty:
# grade defaults to `llm`, upgraded only by a TARGET_POLARITY_QUOTES quote.
TARGET_POLARITY_PROVENANCE: dict[str, str] = {}

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
    classification: dict[str, dict[str, Any]] = {}
    for attr in CLASSIFICATION_ATTRS:
        entry: dict[str, Any] = {"grade": base_grade}
        if rq is not None and attr in covered:
            entry["sources"] = [dict(rq)]
            if _GRADE_RANK[rq["provenance"]] > _GRADE_RANK[entry["grade"]]:
                entry["grade"] = rq["provenance"]
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

    The authored drug (from ``tools/drugs_data.json``) is mostly passed through;
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
