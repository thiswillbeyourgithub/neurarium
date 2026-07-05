ENTRIES = [

    # --- GABAergic -------------------------------------------------------------
    dict(id="gaba_a", name="GABA-A", family="gabaergic",
         neurotransmitter="GABA", receptor_class="ionotropic",
         sign="inhibitory", synaptic="postsynaptic", locations="ALL",
         description="Ubiquitous Cl- channel; target of benzodiazepines, alcohol, "
                     "anaesthetics, neurosteroids; anxiety/epilepsy/insomnia.",
         description_fr="Canal Cl- ubiquitaire ; cible des benzodiazépines, de "
                        "l'alcool, des anesthésiques, des neurostéroïdes ; "
                        "anxiété/épilepsie/insomnie.",
         wikipedia="https://en.wikipedia.org/wiki/GABAA_receptor"),
    dict(id="gaba_b", name="GABA-B", family="gabaergic",
         neurotransmitter="GABA", receptor_class="metabotropic",
         sign="inhibitory", synaptic="both", locations="ALL",
         description="Widespread Gi/o GPCR; opens K+ channels, curbs Ca2+ and "
                     "transmitter release; baclofen target.",
         description_fr="RCPG Gi/o répandu ; ouvre les canaux K+, réduit le Ca2+ "
                        "et la libération de neurotransmetteur ; cible du "
                        "baclofène.",
         wikipedia="https://en.wikipedia.org/wiki/GABAB_receptor"),
    # Stub: GABA-A-rho (formerly "GABA-C") is predominantly retinal.
    dict(id="gaba_a_rho", name="GABA-A-ρ", family="gabaergic",
         neurotransmitter="GABA", receptor_class="ionotropic",
         sign="inhibitory", synaptic="postsynaptic", locations=[],
         wikipedia="https://en.wikipedia.org/wiki/GABAA-rho_receptor"),
]
