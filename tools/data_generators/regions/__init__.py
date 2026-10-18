"""Brain-region anatomy records, one module per anatomical ``group``.

Each group module exposes ``PAIRED`` (L/R-paired, right side) and ``MIDLINE``
(emitted once, no hemisphere suffix); either may be empty. ``PAIRED`` and
``MIDLINE`` below concatenate the group slices in the original first-appearance
order so the emitted ``structures.jsonl`` is byte-for-byte unchanged.
"""

from typing import Any

from . import (
    basal_ganglia,
    brainstem_nuclei,
    cortex,
    diencephalon,
    hindbrain,
    limbic,
)

PAIRED: list[dict[str, Any]] = (
    cortex.PAIRED
    + basal_ganglia.PAIRED
    + limbic.PAIRED
    + diencephalon.PAIRED
    + brainstem_nuclei.PAIRED
)

MIDLINE: list[dict[str, Any]] = (
    diencephalon.MIDLINE
    + hindbrain.MIDLINE
    + brainstem_nuclei.MIDLINE
)


# Search-only alternate names of a region, keyed by its *base* id (both hemispheres
# share them): the acronyms a reader types ("VTA", "LC", "NAc") and that the region's
# own name does not contain. Like ``drugs.DRUG_ALIASES`` these are never rendered and
# never graded (a fact about how people refer to a region, not a claim about the
# brain). The search box folds accents + case, and the French name is already found
# via ``search_names.fr.json``, so only genuinely different words belong here.
# The frontal lobe answers "PFC" because it holds the prefrontal cortex until that
# finer cut is modeled (see CLAUDE.md, structure granularity).
STRUCTURE_ALIASES: dict[str, list[str]] = {
    "frontal": ["PFC", "prefrontal cortex", "cortex préfrontal", "CPF"],
    "cingulate": ["ACC", "anterior cingulate cortex", "cortex cingulaire antérieur"],
    "globus_pallidus": ["GP", "GPe", "GPi", "pallidum"],
    "subthalamic_nucleus": ["STN"],
    "substantia_nigra": ["SN", "SNc", "SNr", "pars compacta", "pars reticulata"],
    "accumbens": ["NAc", "NAcc", "ventral striatum", "striatum ventral"],
    "locus_coeruleus": ["LC"],
    "vta": ["VTA", "AVT"],
    "tuberomammillary": ["TMN"],
    "nucleus_basalis": ["NBM", "nbM"],
    "raphe": ["DRN", "dorsal raphe", "raphé dorsal"],
    "hypothalamus": ["HPA axis"],
}


def structure_bases() -> set[str]:
    """Every region *base* id (paired and midline), the id a receptor location, a
    target region, a structure quote or an addon anchor keys on (a fresh set)."""
    return {e["base"] for e in PAIRED} | {e["base"] for e in MIDLINE}
