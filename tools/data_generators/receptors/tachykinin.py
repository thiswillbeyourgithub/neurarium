ENTRIES = [

    # --- Tachykinin (substance P) ----------------------------------------------
    # NK1 is the substance P receptor and the target of the antiemetic
    # aprepitant. Its central antiemetic site is the area postrema /
    # nucleus tractus solitarius, which the model folds into the medulla.
    dict(id="nk1", name="NK1", family="tachykinin",
         neurotransmitter="Substance P", receptor_class="metabotropic",
         sign="excitatory", synaptic="postsynaptic",
         locations=["caudate", "putamen", "amygdala", "hippocampus", "thalamus",
                    "cerebellum", "frontal", "midbrain"],
         description="Gq GPCR for substance P; in the brainstem vomiting centre, "
                     "striatum and amygdala, aprepitant's antiemetic target.",
         description_fr="RCPG Gq de la substance P ; dans le centre du vomissement du "
                        "tronc cérébral, le striatum et l'amygdale, cible antiémétique "
                        "de l'aprépitant.",
         wikipedia="https://en.wikipedia.org/wiki/Tachykinin_receptor_1"),
]
