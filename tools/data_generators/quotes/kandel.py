"""Kandel/Nieuwenhuys quote registries: projection + structure anatomy sources.

Owns every ``_KQ_*`` Kandel pathway sentence, including those
data_generators.connectivity cites for its CIRCUITS / PROJECTION_GROUPS, built
with the ``_kandel`` / ``_nieuwenhuys`` quote constructors from
data_generators.provenance. No import cycle: provenance <- quotes <- connectivity
<- generate_data.
"""
from typing import Any

from data_generators.provenance import _kandel, _nieuwenhuys, _nolte

# Pathway sentences reused across PROJECTION_QUOTES, STRUCTURE_QUOTES and the
# CIRCUITS / PROJECTION_GROUPS literals in data_generators.connectivity (which
# imports them from here). Defined once so one sentence is one quote object.
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
_KQ_CHOLINERGIC_BASAL = _kandel(1047,
    "Those in the basal forebrain are divided into the medial septum, the "
    "nuclei of the vertical and horizontal limbs of the diagonal band, and the "
    "nucleus basalis of Meynert. These neurons project throughout the cerebral "
    "cortex, hippocampus, and amygdala.")
# One sentence pair backing the whole melatonin story: that the pineal makes it,
# and that the suprachiasmatic nucleus is where its receptors are. Cited by the
# pineal structure, the pineal -> hypothalamus pathway and the melatonergic group.
_KQ_MELATONIN = _kandel(1137,
    "Melatonin is made by the pineal gland, and the suprachiasmatic neurons time "
    "its release through communication with neurons in the paraventricular "
    "nucleus of the hypothalamus that activate sympathetic innervation of the "
    "pineal gland. Neurons in the suprachiasmatic nucleus contain melatonin "
    "receptors, which reinforce circadian rhythms.")
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
    "In contrast, striatal neurons containing enkephalin and expressing mainly "
    "D2 dopamine receptors make excitatory contact with the output nuclei via relays in the "
    "globus pallidus and subthalamus: the indirect pathway.")

# Two sentences that each back a whole fan of ascending arrows, so they are
# written once here rather than per endpoint. They are cited only by
# PROJECTION_QUOTES (no CIRCUIT / PROJECTION_GROUP uses them).
_KQ_RAPHE_FOREBRAIN = _kandel(1048,
    "The B5–B7 neurons in the pons mainly provide serotonergic innervation of "
    "the thalamus, hypothalamus, and cerebral cortex.")
_KQ_HISTAMINE_CORTEX = _kandel(1048,
    "They are the sole source of histaminergic actions in the entire brain, from "
    "the cerebral cortex to the spinal cord, and are involved in a variety of "
    "arousal responses.")
_KQ_HISTAMINE_NEURAXIS = _kandel(1046,
    "All histaminergic neurons are located in the posterior lateral hypothalamus, "
    "mostly within the tuberomammillary nucleus. These neurons project to "
    "virtually every part of the neuraxis and play a major role in arousal.")
_NQ_RAPHE_STRIATUM = _nieuwenhuys(896,
    "The main projections of the dorsal raphe nucleus are to the lateral "
    "geniculate body, the striatum, the entorhinal cortex, the olfactory bulb "
    "and the amygdala, and from the median raphe nucleus to the septum, basal "
    "forebrain and hippocampus")

# Verified quote-sources for pathways, keyed by RIGHT-side ``(from, to)``
# endpoint pair (matching how PROJECTIONS defines each pathway once on the right).
# Most are Kandel (the ``_kandel`` helper); a few connectivity claims Kandel does
# not state in prose are backed by the Nieuwenhuys atlas (``_nieuwenhuys``). Each
# quote carries its own ``corpus``, so the table is corpus-agnostic.
# ``_projection_records`` merges the matching quote entry's ``sources``
# before mirroring, so both hemispheres inherit it; a single sentence backing many
# pathways (e.g. one naming the whole striatal output) is written once as a
# ``_KQ_*`` constant (defined above), not duplicated per entry.
# Every key must match a PROJECTIONS entry or
# ``build_records`` raises (typo guard). This is the projection analogue of the
# per-binding drug sources; ``check_data.py`` confirms each quote verbatim on the
# cited page (the verify gate).
# The sentence immediately before the one _KQ_CHOLINERGIC_BASAL quotes: same
# figure legend, the other half of the cholinergic map. It names both mesopontine
# nuclei, so it grades the two structures and their thalamic arrows.
_KQ_MESOPONTINE = _kandel(1047,
    "Those in the pons and midbrain (mesopontine groups) are divided into a "
    "ventrolateral cluster (pedunculopontine nucleus) and the dorsomedial "
    "cluster (laterodorsal tegmental nucleus). The mesopontine cholinergic "
    "neurons project to the brain stem reticular formation and the thalamus.")


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
        "For example, the sensorimotor territories of the dorsolateral striatum receive "
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
    # The septal area is named only in Kandel's branching-axon sentence.
    ("vta_R", "septal_nuclei_R"): _kandel(982,
        "Individual dopaminergic neurons have highly branching axons that project into "
        "extensive regions of not only the other basal ganglia nuclei but also external "
        "structures (eg, frontal cortex, septal area, amygdala, habenula)."),
    # Tectothalamic: the inferior colliculus (midbrain) to the medial geniculate.
    ("midbrain", "thalamus_R"): _kandel(701,
        "Neurons of the inferior colliculus project to the superior colliculus and to "
        "the medial geniculate nucleus of the thalamus."),
    ("vta_R", "accumbens_R"): _KQ_VTA_REWARD,
    ("vta_R", "amygdala_R"): _KQ_VTA_REWARD,
    ("vta_R", "frontal_R"): _KQ_VTA_REWARD,
    ("vta_R", "hippocampus_R"): _KQ_VTA_REWARD,
    # Ascending histaminergic: one Kandel sentence (p.1052) names the
    # tuberomammillary histamine neurons innervating cortex/thalamus/hypothalamus/
    # basal forebrain, backing all four TMN targets.
    ("tuberomammillary_R", "frontal_R"): _KQ_MONOAMINE_INNERV,
    ("tuberomammillary_R", "thalamus_R"): _KQ_MONOAMINE_INNERV,
    ("tuberomammillary_R", "hypothalamus_R"): _KQ_MONOAMINE_INNERV,
    ("tuberomammillary_R", "septal_nuclei_R"): _KQ_MONOAMINE_INNERV,
    # The rest of the histamine fan. Kandel never lists this system's targets one
    # by one; he twice states it in the broadest terms a book can, and those two
    # sentences are the only sources there are. Split by what each actually
    # covers: _KQ_HISTAMINE_CORTEX ("from the cerebral cortex to the spinal cord")
    # for the cortical + limbic targets, _KQ_HISTAMINE_NEURAXIS ("virtually every
    # part of the neuraxis") for the striatum, olfactory bulb, brainstem and
    # cerebellum, which "cerebral cortex to spinal cord" only reaches by implication.
    ("tuberomammillary_R", "parietal_R"): _KQ_HISTAMINE_CORTEX,
    ("tuberomammillary_R", "temporal_R"): _KQ_HISTAMINE_CORTEX,
    ("tuberomammillary_R", "occipital_R"): _KQ_HISTAMINE_CORTEX,
    ("tuberomammillary_R", "cingulate_R"): _KQ_HISTAMINE_CORTEX,
    ("tuberomammillary_R", "hippocampus_R"): _KQ_HISTAMINE_CORTEX,
    ("tuberomammillary_R", "amygdala_R"): _KQ_HISTAMINE_CORTEX,
    ("tuberomammillary_R", "accumbens_R"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "caudate_R"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "putamen_R"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "olfactory_bulb_R"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "midbrain"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "pons"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "medulla"): _KQ_HISTAMINE_NEURAXIS,
    ("tuberomammillary_R", "cerebellum"): _KQ_HISTAMINE_NEURAXIS,
    ("pineal", "suprachiasmatic_R"): _KQ_MELATONIN,
    # Ascending cholinergic: one Kandel sentence (p.1047) puts the nucleus basalis
    # of Meynert in the basal forebrain group and has it projecting "throughout the
    # cerebral cortex, hippocampus, and amygdala", backing all six NBM targets
    # (the four lobes + cingulate cortex + amygdala).
    # The sentence immediately before the one _KQ_CHOLINERGIC_BASAL quotes: same
    # figure legend, the other half of the cholinergic map.
    ("pedunculopontine_R", "thalamus_R"): _KQ_MESOPONTINE,
    ("laterodorsal_tegmental_R", "thalamus_R"): _KQ_MESOPONTINE,
    ("periaqueductal_gray", "raphe"): _kandel(536,
        "Both the serotonergic nucleus raphe magnus and noradrenergic nuclei "
        "receive input from neurons in the periaqueductal gray region."),
    ("nucleus_basalis_R", "frontal_R"): _KQ_CHOLINERGIC_BASAL,
    ("nucleus_basalis_R", "parietal_R"): _KQ_CHOLINERGIC_BASAL,
    ("nucleus_basalis_R", "temporal_R"): _KQ_CHOLINERGIC_BASAL,
    ("nucleus_basalis_R", "occipital_R"): _KQ_CHOLINERGIC_BASAL,
    ("nucleus_basalis_R", "cingulate_R"): _KQ_CHOLINERGIC_BASAL,
    ("nucleus_basalis_R", "amygdala_R"): _KQ_CHOLINERGIC_BASAL,
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
    ("locus_coeruleus_R", "parietal_R"): _KQ_MONOAMINE_INNERV,
    ("locus_coeruleus_R", "temporal_R"): _KQ_MONOAMINE_INNERV,
    ("locus_coeruleus_R", "occipital_R"): _KQ_MONOAMINE_INNERV,
    ("locus_coeruleus_R", "cingulate_R"): _KQ_MONOAMINE_INNERV,
    ("locus_coeruleus_R", "hypothalamus_R"): _KQ_MONOAMINE_INNERV,
    # The cerebellum is outside every "forebrain" sentence, so it needs the atlas.
    ("locus_coeruleus_R", "cerebellum"): _nieuwenhuys(900,
        "The cerebellar noradrenergic innervation of the cerebellum and the "
        "inferior olive stems from the locus coeruleus and the groups A5 and A7"),
    # Not _KQ_MONOAMINE_INNERV: an Opus judge rejected that sentence for this one arrow
    # (it names "the cerebral cortex", and raphe -> frontal was its only cortical use, so
    # no blanket_claim flag conceded it). This sentence sweeps every raphe -> lobe arrow,
    # so the derived blanket_claim flag says out loud that the lobe split is ours.
    ("raphe", "frontal_R"): _KQ_RAPHE_FOREBRAIN,
    ("raphe", "hypothalamus_R"): _KQ_MONOAMINE_INNERV,
    ("raphe", "amygdala_R"): _KQ_MONOAMINE_LIMBIC,
    ("raphe", "hippocampus_R"): _KQ_MONOAMINE_LIMBIC,
    ("raphe", "thalamus_R"): _KQ_RAPHE_FOREBRAIN,
    ("raphe", "parietal_R"): _KQ_RAPHE_FOREBRAIN,
    ("raphe", "temporal_R"): _KQ_RAPHE_FOREBRAIN,
    ("raphe", "occipital_R"): _KQ_RAPHE_FOREBRAIN,
    ("raphe", "cingulate_R"): _KQ_RAPHE_FOREBRAIN,
    ("raphe", "accumbens_R"): _NQ_RAPHE_STRIATUM,
    ("raphe", "caudate_R"): _NQ_RAPHE_STRIATUM,
    ("raphe", "putamen_R"): _NQ_RAPHE_STRIATUM,
    ("raphe", "substantia_nigra_R"): _nieuwenhuys(896,
        "The median raphe nucleus connects with the interpeduncular nucleus, the "
        "substantia nigra and the mamillary body."),
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
        "Finally, it may be mentioned that a considerable number of limbic "
        "cortical areas, including the "
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
# The one sentence that names the basal-forebrain cholinergic nuclei, so it grades
# both structures it names (the medial septum and the nucleus basalis of Meynert).
# The projections out of them cite the sentence that follows it instead
# (_KQ_CHOLINERGIC_BASAL), which is where the innervation is stated.
_KSQ_BASAL_FOREBRAIN = _kandel(1047,
    "Those in the basal forebrain are divided into the medial septum, the "
    "nuclei of the vertical and horizontal limbs of the diagonal band, and "
    "the nucleus basalis of Meynert.")
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
    "tuberomammillary": _KQ_MONOAMINE_INNERV,
    # Diencephalon.
    "hypothalamus": _kandel(1025,
        "Neurons controlling the internal environment are concentrated in the "
        "hypothalamus, a small area of the diencephalon that comprises less than "
        "1% of the total brain volume."),
    "mammillary": _kandel(1096,
        "The sensory cortex then projects to both the cingulate cortex and the "
        "hippocampus, which in turn makes connections with the mammillary bodies "
        "of the hypothalamus, thus completing the loop"),
    "pineal": _KQ_MELATONIN,
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
    "septal_nuclei": _KSQ_BASAL_FOREBRAIN,
    "nucleus_basalis": _KSQ_BASAL_FOREBRAIN,
    "pedunculopontine": _KQ_MESOPONTINE,
    "laterodorsal_tegmental": _KQ_MESOPONTINE,
    "suprachiasmatic": _kandel(1137,
        "The suprachiasmatic nucleus exerts control over all of the other body "
        "clocks by regulating body temperature as well as autonomic, endocrine, "
        "and behavioral functions."),
    "area_postrema": _kandel(1041,
        "Toxic substances in the blood stream can be detected by nerve cells in "
        "the area postrema, a small region adjacent to the nucleus of the "
        "solitary tract along the floor of the fourth ventricle."),
    # Kandel never places it anatomically, Nolte does.
    "periaqueductal_gray": _nolte(292,
        "Medial to it, encircling the aqueduct, is a particularly pale-staining "
        "region of gray matter called, appropriately enough, the periaqueductal "
        "gray."),
}
