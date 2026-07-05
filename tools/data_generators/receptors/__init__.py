"""Receptor classification records, one module per neurotransmitter family.

Each family module exposes ``ENTRIES`` (its receptor dicts in original order).
``RECEPTORS`` concatenates them in the original first-appearance order so the
emitted ``receptors.jsonl`` is byte-for-byte unchanged.
"""

from typing import Any

from . import (
    adrenergic,
    cannabinoid,
    cholinergic,
    dopaminergic,
    gabaergic,
    glutamatergic,
    glycinergic,
    histaminergic,
    melatonergic,
    opioidergic,
    purinergic,
    serotonergic,
    sigma,
)

RECEPTORS: list[dict[str, Any]] = (
    adrenergic.ENTRIES
    + cholinergic.ENTRIES
    + dopaminergic.ENTRIES
    + gabaergic.ENTRIES
    + glutamatergic.ENTRIES
    + glycinergic.ENTRIES
    + histaminergic.ENTRIES
    + opioidergic.ENTRIES
    + serotonergic.ENTRIES
    + cannabinoid.ENTRIES
    + purinergic.ENTRIES
    + sigma.ENTRIES
    + melatonergic.ENTRIES
)
