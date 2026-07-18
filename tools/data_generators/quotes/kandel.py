"""Kandel/Nieuwenhuys quote registries: projection + structure anatomy sources.

Moved verbatim out of tools/generate_data.py. Cites the ``_KQ_*`` shared quote
constants defined in data_generators.connectivity and the ``_kandel`` /
``_nieuwenhuys`` quote constructors from data_generators.provenance. No import
cycle: provenance <- connectivity <- quotes <- generate_data.
"""
from typing import Any

from data_generators.provenance import _kandel, _nieuwenhuys
from data_generators.connectivity import (
    _KQ_CORPUS_CALLOSUM,
    _KQ_CORTICOPONTINE,
    _KQ_CORTICOSTRIATAL,
    _KQ_MONOAMINE_INNERV,
    _KQ_MONOAMINE_LIMBIC,
    _KQ_NIGROSTRIATAL,
    _KQ_PAPEZ,
    _KQ_STRIATONIGRAL,
    _KQ_STRIATOPALLIDAL,
    _KQ_VTA_REWARD,
)

# Verified quote-sources for pathways, keyed by RIGHT-side ``(from, to)``
# endpoint pair (matching how PROJECTIONS defines each pathway once on the right).
# Most are Kandel (the ``_kandel`` helper); a few connectivity claims Kandel does
# not state in prose are backed by the Nieuwenhuys atlas (``_nieuwenhuys``). Each
# quote carries its own ``corpus``, so the table is corpus-agnostic.
# ``_projection_records`` merges the matching quote entry's ``sources``
# before mirroring, so both hemispheres inherit it; a single sentence backing many
# pathways (e.g. one naming the whole striatal output) is written once as a
# ``_KQ_*`` constant (those reused by CIRCUITS/PROJECTION_GROUPS live in
# data_generators.connectivity, imported above), not duplicated per entry.
# Every key must match a PROJECTIONS entry or
# ``build_records`` raises (typo guard). This is the projection analogue of the
# per-binding drug sources; ``check_data.py`` confirms each quote verbatim on the
# cited page (the verify gate).
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
    # Ascending histaminergic: one Kandel sentence (p.1052) names the
    # tuberomammillary histamine neurons innervating cortex/thalamus/hypothalamus/
    # basal forebrain, backing all four TMN targets.
    ("tuberomammillary_R", "frontal_R"): _KQ_MONOAMINE_INNERV,
    ("tuberomammillary_R", "thalamus_R"): _KQ_MONOAMINE_INNERV,
    ("tuberomammillary_R", "hypothalamus_R"): _KQ_MONOAMINE_INNERV,
    ("tuberomammillary_R", "septal_nuclei_R"): _KQ_MONOAMINE_INNERV,
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
