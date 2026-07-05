ENTRIES = [

    # --- Cholinergic (acetylcholine) -------------------------------------------
    dict(id="m1", name="M1", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "cingulate",
                    "hippocampus", "accumbens"],
         description="Gq postsynaptic muscarinic receptor; slow EPSP, drives "
                     "cortical/hippocampal cognition and memory.",
         description_fr="Récepteur muscarinique Gq postsynaptique ; PPSE lent, "
                        "soutient la cognition et la mémoire corticale et "
                        "hippocampique.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M1"),
    dict(id="m2", name="M2", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["olfactory_bulb", "midbrain", "pons", "medulla", "frontal", "parietal",
                    "temporal", "occipital", "hippocampus"],
         description="Gi-coupled presynaptic autoreceptor; restrains acetylcholine "
                     "release (also slows the heart).",
         description_fr="Autorécepteur présynaptique couplé à Gi ; freine la "
                        "libération d'acétylcholine (ralentit aussi le cœur).",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M2"),
    dict(id="m3", name="M3", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["hypothalamus", "midbrain", "pons", "medulla", "thalamus", "frontal", "temporal",
                    "occipital"],
         description="Gq postsynaptic muscarinic receptor; acts in hypothalamus "
                     "and brainstem autonomic centres.",
         description_fr="Récepteur muscarinique Gq postsynaptique ; agit dans "
                        "l'hypothalamus et les centres autonomes du tronc "
                        "cérébral.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M3"),
    dict(id="m4", name="M4", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["caudate", "putamen", "accumbens", "frontal", "cingulate"],
         description="Gi-coupled receptor enriched in striatum; presynaptic "
                     "autoreceptor that brakes D1 dopamine drive.",
         description_fr="Récepteur couplé à Gi enrichi dans le striatum ; "
                        "autorécepteur présynaptique freinant l'activité "
                        "dopaminergique D1.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M4"),
    dict(id="m5", name="M5", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["substantia_nigra", "vta", "hypothalamus", "frontal",
                    "amygdala", "hippocampus", "mammillary"],
         description="Gq receptor on substantia nigra/VTA dopamine neurons; "
                     "facilitates dopamine release.",
         description_fr="Récepteur Gq sur les neurones dopaminergiques de la "
                        "substance noire et de l'ATV ; facilite la libération de "
                        "dopamine.",
         wikipedia="https://en.wikipedia.org/wiki/Muscarinic_acetylcholine_receptor_M5"),
    # Stub: muscle-type nAChR sits at the neuromuscular junction (peripheral).
    dict(id="nachr_muscle", name="Muscle nAChR", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor"),
    dict(id="nachr_a4b2", name="Neuronal α4β2 nAChR", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="ionotropic",
         sign="excitatory", synaptic="both",
         locations=["frontal", "parietal", "temporal", "occipital", "thalamus",
                    "vta", "substantia_nigra", "accumbens", "caudate", "putamen"],
         description="High-affinity nicotine receptor; cation channel on dopamine "
                     "terminals, drives nicotine addiction.",
         description_fr="Récepteur nicotinique à haute affinité ; canal cationique "
                        "sur les terminaisons dopaminergiques, moteur de "
                        "l'addiction à la nicotine.",
         wikipedia="https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor"),
    dict(id="nachr_a7", name="Neuronal α7 nAChR", family="cholinergic",
         neurotransmitter="Acetylcholine", receptor_class="ionotropic",
         sign="excitatory", synaptic="both",
         locations=["hippocampus", "frontal", "parietal", "temporal", "occipital",
                    "thalamus", "amygdala"],
         description="Homomeric Ca2+-permeable cation channel; "
                     "α-bungarotoxin-sensitive, implicated in schizophrenia.",
         description_fr="Canal cationique homomérique perméable au Ca2+ ; sensible "
                        "à l'α-bungarotoxine, impliqué dans la schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/Nicotinic_acetylcholine_receptor"),
]
