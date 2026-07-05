ENTRIES = [
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
]
