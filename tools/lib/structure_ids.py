"""The one rule for a structure id's hemisphere suffix.

A paired region is emitted twice (``frontal_R`` / ``frontal_L``) and every receptor
location, target region or projection endpoint compares on its *base* (``frontal``);
a midline structure (``raphe``) has no suffix. Exactly one trailing ``_R`` / ``_L``
is stripped, so an odd id keeps the rest (``x_L_R`` -> ``x_L``, never ``x``).

Stdlib only, so ``check_data.py`` and ``generate_data.py`` stay runnable offline.

Built with the help of Claude Code.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# A trailing hemisphere suffix ("frontal_R" -> "frontal").
HEMISPHERE_RE = re.compile(r"_(R|L)$")


def base_id(structure_id):
    """``structure_id`` with its one trailing ``_R`` / ``_L`` dropped (a falsy id as is).

    >>> base_id("accumbens_R"), base_id("raphe"), base_id("x_L_R"), base_id(None)
    ('accumbens', 'raphe', 'x_L', None)
    """
    return HEMISPHERE_RE.sub("", structure_id) if structure_id else structure_id


def bases_of(structures: Iterable[dict]) -> set[str]:
    """The base id of every emitted structure record (mirrored ``x_R`` counts as ``x``).
    The authored set is ``data_generators.regions.structure_bases``."""
    return {base_id(s.get("id", "")) for s in structures}
