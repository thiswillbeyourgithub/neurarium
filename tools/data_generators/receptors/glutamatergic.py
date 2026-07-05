ENTRIES = [

    # --- Glutamatergic ---------------------------------------------------------
    dict(id="nmda", name="NMDA", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic", locations="ALL",
         description="Coincidence-detecting Ca2+ channel driving LTP/memory; "
                     "ketamine/memantine target, schizophrenia hypofunction.",
         description_fr="Canal Ca2+ détecteur de coïncidence pilotant la "
                        "LTP/mémoire ; cible kétamine/mémantine, hypofonction dans "
                        "la schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/NMDA_receptor"),
    dict(id="ampa", name="AMPA", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="ionotropic",
         sign="excitatory", synaptic="postsynaptic", locations="ALL",
         description="Fast cation channel mediating most fast excitatory "
                     "transmission; its trafficking underlies synaptic plasticity.",
         description_fr="Canal cationique rapide assurant l'essentiel de la "
                        "transmission excitatrice rapide ; son trafic sous-tend la "
                        "plasticité.",
         wikipedia="https://en.wikipedia.org/wiki/AMPA_receptor"),
    dict(id="kainate", name="Kainate", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="ionotropic",
         sign="excitatory", synaptic="both",
         locations=["hippocampus", "frontal", "parietal", "temporal", "occipital",
                    "amygdala", "cerebellum"],
         description="Cation channel with more limited distribution; postsynaptic "
                     "excitation plus presynaptic modulation of release.",
         description_fr="Canal cationique à distribution plus limitée ; excitation "
                        "postsynaptique et modulation présynaptique de la "
                        "libération.",
         wikipedia="https://en.wikipedia.org/wiki/Kainate_receptor"),
    dict(id="mglur1", name="mGluR1", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["cerebellum", "hippocampus", "thalamus", "frontal", "parietal",
                    "temporal", "occipital"],
         description="Group I Gq receptor; postsynaptic excitation, potentiates "
                     "NMDA currents; strong in cerebellar Purkinje cells.",
         description_fr="Récepteur Gq du groupe I ; excitation postsynaptique, "
                        "potentialise les courants NMDA ; abondant dans les "
                        "cellules de Purkinje.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur2", name="mGluR2", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "amygdala"],
         description="Group II Gi presynaptic autoreceptor lowering glutamate "
                     "release; agonists target anxiety and schizophrenia.",
         description_fr="Autorécepteur présynaptique Gi du groupe II réduisant la "
                        "libération de glutamate ; agonistes visés pour l'anxiété "
                        "et la schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur3", name="mGluR3", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "thalamus"],
         description="Group II Gi receptor on terminals and glia reducing "
                     "glutamate release; neuroprotective, schizophrenia interest.",
         description_fr="Récepteur Gi du groupe II sur terminaisons et glie "
                        "réduisant la libération de glutamate ; neuroprotecteur, "
                        "intérêt schizophrénie.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur4", name="mGluR4", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic",
         locations=["cerebellum", "thalamus", "hypothalamus", "caudate", "putamen"],
         description="Group III Gi presynaptic receptor suppressing release; "
                     "basal-ganglia activation proposed for Parkinson's.",
         description_fr="Récepteur présynaptique Gi du groupe III réduisant la "
                        "libération ; activation des noyaux gris visée pour la "
                        "maladie de Parkinson.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur5", name="mGluR5", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["caudate", "putamen", "accumbens", "hippocampus", "frontal",
                    "parietal", "temporal", "occipital", "amygdala"],
         description="Group I Gq receptor potentiating NMDA; fragile-X and "
                     "psychiatric drug target, dense in striatum/cortex.",
         description_fr="Récepteur Gq du groupe I potentialisant le NMDA ; cible X "
                        "fragile/psychiatrie, dense dans le striatum et le cortex.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    # Stub: mGluR6 is restricted to retinal ON-bipolar cells.
    dict(id="mglur6", name="mGluR6", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
    dict(id="mglur7", name="mGluR7", family="glutamatergic",
         neurotransmitter="Glutamate", receptor_class="metabotropic",
         sign="inhibitory", synaptic="presynaptic", locations="ALL",
         description="Group III Gi presynaptic autoreceptor, the most widespread "
                     "mGluR, gating release at active zones; lowest affinity.",
         description_fr="Autorécepteur présynaptique Gi du groupe III, le mGluR le "
                        "plus répandu, contrôle la libération aux zones actives ; "
                        "plus faible affinité.",
         wikipedia="https://en.wikipedia.org/wiki/Metabotropic_glutamate_receptor"),
]
