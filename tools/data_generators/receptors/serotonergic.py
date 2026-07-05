ENTRIES = [

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
         sign="excitatory", synaptic="presynaptic",
         locations=["hypothalamus", "frontal", "amygdala"],
         description="Gq-coupled; presynaptic autoreceptor on raphe 5-HT neurons; "
                     "also peripheral (cardiac valves, valvulopathy risk); sparse CNS "
                     "in hypothalamus, cortex, amygdala.",
         description_fr="Couplé à Gq ; autorécepteur présynaptique sur les neurones "
                        "sérotoninergiques du raphé ; aussi périphérique (valves "
                        "cardiaques, risque de valvulopathie) ; rare dans le SNC : "
                        "hypothalamus, cortex, amygdale.",
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
]
