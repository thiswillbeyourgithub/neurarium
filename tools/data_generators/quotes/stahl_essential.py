"""Stahl's Essential Psychopharmacology quote registries: receptor + target
classification, per-attribute overrides, and target tone polarity.

Moved verbatim out of tools/generate_data.py. Imports the ``_stahl_ess`` quote
constructor from data_generators.provenance. Ordering matters: the ``_SE_*``
shared constants come first, then the registries that reference them, and
TARGET_POLARITY_QUOTES is defined AFTER STAHL_ESSENTIAL_TARGET_QUOTES because it
reads that dict at import time.
"""
from typing import Any

from data_generators.provenance import _stahl_ess

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
    "alpha1d": _SE_NE_GROUPS,
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
    "alpha1a": _F, "alpha1b": _F, "alpha1d": _F,
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
    # muscarinic / nicotinic / alpha1 / beta are `members` groups: expanded to their
    # individual receptors (which carry their own classification quotes via
    # STAHL_ESSENTIAL_RECEPTOR_QUOTES) and not emitted as browsable target nodes, so
    # they need no group-level target quote here. Only the un-expanded α2 group does.
    "alpha2": _SE_NE_GROUPS,
    "glutamate": _stahl_ess(92,
        "The other subclass of ligand-gated ion channels has a tetrameric "
        "structure, and includes many glutamate receptors, including the AMPA, "
        "kainate, and NMDA subtypes."),
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
    # α2's own quote, NOT its classification one: _SE_NE_GROUPS only classifies α2
    # as an NE receptor family and never speaks to direction. This sentence states
    # both halves of the polarity flag in one breath: *presynaptic* (the site) and
    # "turn off further release" (the inhibitory autoreceptor sign), which is exactly
    # what makes an α2 antagonist raise noradrenergic tone in the flow overlay.
    "alpha2": _stahl_ess(271,
        "That is, when presynaptic α2 receptors recognize NE, they turn off further "
        "release of NE"),
}
