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
