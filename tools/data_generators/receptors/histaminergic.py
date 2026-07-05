ENTRIES = [

    # --- Histaminergic ---------------------------------------------------------
    dict(id="h1", name="H1", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "cingulate",
                    "amygdala", "hippocampus", "thalamus", "hypothalamus",
                    "midbrain", "pons", "medulla"],
         description="Gq excitatory; drives wakefulness and arousal; its blockade "
                     "by antihistamines causes sedation.",
         description_fr="Gq excitateur ; favorise l'éveil et la vigilance ; son "
                        "blocage par les antihistaminiques cause la sédation.",
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H1_receptor"),
    dict(id="h2", name="H2", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "caudate",
                    "putamen", "hippocampus", "cerebellum"],
         description="Gs cAMP receptor; mainly gastric, with a lighter CNS role in "
                     "basal ganglia and cortex.",
         description_fr="Récepteur Gs/AMPc ; surtout gastrique, avec un rôle "
                        "central plus léger dans les noyaux gris et le cortex.",
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H2_receptor"),
    dict(id="h3", name="H3", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "cingulate",
                    "caudate", "putamen", "accumbens", "hippocampus", "hypothalamus",
                    "olfactory_bulb"],
         description="Gi presynaptic auto/heteroreceptor; CNS-wide; curbs "
                     "transmitter release; cognition and wakefulness target.",
         description_fr="Auto/hétérorécepteur présynaptique Gi ; pan-cérébral ; "
                        "freine la libération de neurotransmetteurs ; cible "
                        "cognition/éveil.",
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H3_receptor"),
    # Stub: H4 is an immune/haematopoietic receptor (no neuronal CNS role).
    dict(id="h4", name="H4", family="histaminergic",
         neurotransmitter="Histamine", receptor_class="metabotropic",
         sign="modulatory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Histamine_H4_receptor"),
]
