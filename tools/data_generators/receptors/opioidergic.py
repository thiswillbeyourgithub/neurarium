ENTRIES = [

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
]
