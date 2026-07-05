ENTRIES = [

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
]
