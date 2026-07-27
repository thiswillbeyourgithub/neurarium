"""Connectivity data: projections (pathways), named circuits, projection groups.

The three connectivity node literals (``PROJECTIONS``, ``CIRCUITS``,
``PROJECTION_GROUPS``) plus the verified pathway quote-source constants they cite
(``_KQ_*`` / ``_SG_*``). Every literal references region ids only as bare strings,
so this module builds only on the shared provenance quote helpers and never
imports the ``generate_data`` CLI module (no import cycle). ``generate_data``
imports these lists (and re-imports the ``_KQ_*`` constants its ``PROJECTION_QUOTES``
map cites) from here.
"""
from __future__ import annotations

from typing import Any

from data_generators.provenance import _kandel, _stahl_ess


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
    "In contrast, striatal neurons containing enkephalin and expressing mainly "
    "D2 dopamine receptors make excitatory contact with the output nuclei via relays in the "
    "globus pallidus and subthalamus: the indirect pathway.")

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
         description="The main output of the hippocampal formation, arising "
                     "chiefly from the subiculum, gathers into the fornix, the "
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
    # --- Ascending histaminergic from the tuberomammillary nucleus (the sole
    #     histamine source, ventral posterior hypothalamus): a diffuse
    #     wakefulness-promoting fan. One Kandel sentence (p.1052, PROJECTION_QUOTES)
    #     backs all four targets. tuberomammillary is paired, so these mirror
    #     fully. Histaminergic is a tone-setter kind (SYSTEM_FLOW_KINDS), so an H3
    #     autoreceptor drug (pitolisant) rides these arrows. ---
    dict(**{"from": "tuberomammillary_R", "to": "frontal_R"},
         kind="histaminergic", neurotransmitter="Histamine",
         label="Ascending histaminergic (prefrontal)",
         description="Tuberomammillary histamine neurons project diffusely to the "
                     "cortex, promoting wakefulness and arousal."),
    dict(**{"from": "tuberomammillary_R", "to": "thalamus_R"},
         kind="histaminergic", neurotransmitter="Histamine",
         label="Ascending histaminergic (thalamic)",
         description="Tuberomammillary histamine projects to the thalamus, gating "
                     "cortical arousal."),
    dict(**{"from": "tuberomammillary_R", "to": "hypothalamus_R"},
         kind="histaminergic", neurotransmitter="Histamine",
         label="Ascending histaminergic (hypothalamic)",
         description="Tuberomammillary histamine projects within the hypothalamus, "
                     "supporting the sleep-wake switch."),
    dict(**{"from": "tuberomammillary_R", "to": "septal_nuclei_R"},
         kind="histaminergic", neurotransmitter="Histamine",
         label="Ascending histaminergic (basal forebrain)",
         description="Tuberomammillary histamine projects to the basal forebrain, "
                     "reinforcing cortical activation."),
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
    dict(mode="kind", key="histaminergic", name="Histamine",
         sources=[_KQ_MONOAMINE_INNERV],
         description="Histaminergic projections from the tuberomammillary nucleus "
                     "promote wakefulness and arousal across the cortex and thalamus.",
         description_fr="Les projections histaminergiques du noyau tubéromammillaire "
                        "favorisent l'éveil et la vigilance dans le cortex et le "
                        "thalamus.",
         wikipedia="https://en.wikipedia.org/wiki/Histaminergic"),
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
