"""Drug presentation maps + binding vocabularies (emitted into meta.json).

The drug "schema": the coarse category labels, the action -> {label, net effect}
map, the effect colours/labels, the non-receptor DRUG_TARGETS registry and the
target type labels/colours. ``build_records`` validates every category / target /
action / effect a drug uses against these. All are authored bilingually inline
(the drug data comes from a separate extraction JSON, so its translations stay
self-contained rather than growing the shared FR table).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Drug presentation maps + binding vocabularies (emitted into meta.json).
#
# Drugs (the psychoactive medications authored in ``tools/data/drugs_data.jsonl``, see
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
    # --- Receptor groups -----------------------------------------------------
    # A `receptor_group` is a coarse target kept ONLY where its subtypes cannot be
    # split honestly: glutamate (expanding to all 10 iono/metabotropic subtypes would
    # over-claim), orexin/melanocortin (no subtype modeled), and α2 (its tone-setting
    # autoreceptor character lives on this group node, see alpha2 below). The
    # muscarinic / α1 / β / nicotinic families ARE split: their drug bindings are
    # authored directly against the individual subtype receptors (m1..m5, alpha1a..d,
    # beta1..3, nachr_a4b2/a7) in drugs_data.jsonl, so each subtype carries its own
    # measured per-subtype Ki (fetch_ki, CHRM1..5 / ADRA1A.. etc.) instead of an
    # aggregate, and the drug shows up when browsing that receptor.
    #
    # `subtypes` links a group to its modeled subtype receptor ids: a self-evident
    # taxonomy (α2 -> α2A/B/C/D), so it carries NO source (see CLAUDE.md "Nodes":
    # a group->subtype link is not a sourceable claim). The viewer uses it to list,
    # under the group panel's own interacting drugs, one collapsible dropdown per
    # subtype that has drugs of its own, so a subtype-specific binder (asenapine at
    # α2A) is reachable from the coarse α2 panel. Omit it for a group whose subtypes
    # are not modeled (orexin/melanocortin have no OX1R/OX2R/MC* receptor records).
    "alpha2": {"name": {"en": "α2 adrenergic receptors",
                        "fr": "Récepteurs α2 adrénergiques"},
               "type": "receptor_group", "system": "adrenergic",
               # The α2 family's dominant pharmacology is the presynaptic
               # *inhibitory autoreceptor* on noradrenergic neurons: an agonist
               # (clonidine) damps NA tone, an antagonist (mirtazapine, yohimbine)
               # disinhibits and raises it. Marked so the flow overlay signs the
               # tone (the specific 5-HT1x / D2/D3 autoreceptors carry this on their
               # own receptor records; a receptor_group has none, so it is set here).
               # Kept coarse (not split into alpha2a..d): the tone-setting autoreceptor
               # character lives on THIS group node's sign/synaptic flags, which the
               # individual alpha2a..d receptor records do not carry, so splitting
               # would silently drop the drug-flow overlay for clonidine / mirtazapine
               # / yohimbine.
               "sign": "inhibitory", "synaptic": "presynaptic",
               "subtypes": ["alpha2a", "alpha2b", "alpha2c", "alpha2d"],
               "wikipedia":
                   "https://en.wikipedia.org/wiki/Alpha-2_adrenergic_receptor",
               "regions": ["locus_coeruleus", "frontal", "hippocampus", "thalamus",
                           "hypothalamus", "midbrain", "pons", "medulla"]},
    "glutamate": {"name": {"en": "Glutamate receptors",
                           "fr": "Récepteurs du glutamate"},
                  "type": "receptor_group", "system": "glutamatergic",
                  "subtypes": ["nmda", "ampa", "kainate", "mglur1", "mglur2",
                               "mglur3", "mglur4", "mglur5", "mglur6", "mglur7"],
                  "wikipedia": "https://en.wikipedia.org/wiki/Glutamate_receptor",
                  "regions": ["frontal", "temporal", "hippocampus", "thalamus",
                              "cerebellum", "caudate", "putamen"]},
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
