"""Internationalization (en / fr) for the data generator.

The data file is bilingual. The anatomy is authored in English; every
translatable *display* string (region names, group headings, projection-kind
labels, neurotransmitters, pathway labels + descriptions, circuit names) is
wrapped with :func:`_t` when the records are built, turning "Foo" into
``{"en": "Foo", "fr": FR["Foo"]}``. The viewer (js/data.js +
window.__I18N__.pick) collapses that to the chosen language.

FR is the single French translation source, keyed by the exact English string
(so a string used in several places is translated once and stays consistent).
A missing key is collected in :data:`_MISSING_TRANSLATIONS` and raised at build
time (see ``build_records``), so the data can never silently ship a
half-translated record. Source citations + URLs are intentionally NOT translated.

Per-hemisphere names are composed, not stored: English prefixes "Right "/"Left "
to the lowercased base name; French suffixes the gender/number-agreed
"droit/droite/droits/droites" (right) or "gauche/gauches" (left). A paired
entry may set ``fr_gender`` ("m" default, "f", "mp", "fp") for that agreement.
"""

from __future__ import annotations

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
