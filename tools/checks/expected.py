"""Warnings the author confirmed are expected by design, each with its reason.

An entry here moves its item from a ``[warn]`` to the review list (``--verbose`` prints
it), so the remaining warnings are only the ones worth fixing. Add an entry only with a
reason a reader can check; remove it when the data changes.

Built with the help of Claude Code.
"""
from __future__ import annotations

# Structures (base id) wired one way on purpose: their other side is not modeled.
ONE_WAY_STRUCTURES: dict[str, str] = {
    "tuberomammillary": "a histaminergic source nucleus, modeled as an ascending source only",
    "nucleus_basalis": "a cholinergic source nucleus, modeled as an ascending source only",
    "pineal": "an endocrine gland: its melatonin output is modeled, its sympathetic input is not",
    "pituitary": "an endocrine gland: hypothalamic input modeled, its output is hormonal",
}

# (system, region base id) expressed but reached by no long pathway, because local
# interneurons of that system supply it.
LOCAL_INTERNEURON_REGIONS: dict[tuple[str, str], str] = {
    ("cholinergic", "accumbens"): "striatal cholinergic interneurons",
    ("cholinergic", "caudate"): "striatal cholinergic interneurons",
    ("cholinergic", "putamen"): "striatal cholinergic interneurons",
    ("dopaminergic", "olfactory_bulb"): "periglomerular dopaminergic interneurons",
}

# Receptor families acting locally, with no single source nucleus to draw a pathway from.
LOCAL_SYSTEMS: dict[str, str] = {
    fam: "local neuromodulator / fast transmitter, no single source nucleus"
    for fam in ("opioidergic", "cannabinoid", "sigma", "glycinergic", "purinergic",
                "glutamatergic", "gabaergic")
}

# (context prefix, quote) short on purpose and still genuine.
SHORT_QUOTES: dict[tuple[str, str], str] = {
    ("drug methadone binding mu", "Opioid agonist"):
        "Stahl's own class line for methadone, the whole statement",
}
