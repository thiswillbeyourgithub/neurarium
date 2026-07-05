ENTRIES = [

    # --- Sigma (added; sigma-1 is an intracellular ER chaperone, not a channel
    #     or GPCR, hence receptor_class="chaperone") ---------------------------
    dict(id="sigma1", name="σ1", family="sigma",
         neurotransmitter="Sigma ligands", receptor_class="chaperone",
         sign="modulatory", synaptic="both",
         locations=["frontal", "parietal", "temporal", "occipital", "hippocampus",
                    "midbrain", "pons", "medulla", "cerebellum"],
         description="Intracellular ER chaperone (not a classic channel/GPCR); "
                     "fluvoxamine acts partly via it.",
         description_fr="Chaperon intracellulaire du RE (ni canal ni RCPG "
                        "classique) ; la fluvoxamine agit en partie via lui.",
         wikipedia="https://en.wikipedia.org/wiki/Sigma-1_receptor"),
]
