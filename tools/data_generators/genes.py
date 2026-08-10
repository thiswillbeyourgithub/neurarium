"""HGNC gene symbol per receptor / non-receptor target, for lookup links.

The gene is an **identifier, not a knowledge node**: it is not graded, not tallied
and not rendered as a claim. It exists because the pharmacogenomics databases are
gene-keyed, so a "look this receptor up on ClinPGx" link needs ``ADRA1A``, not the
display name ``α1A`` (which no such database indexes).

Direction of the borrow: the maps are **owned by the author-side fetchers**, which
resolve them against the external databases (``fetch_gtopdb`` for the GtoPdb tissue
pass, ``fetch_gtopdb_class`` for the receptors it completed, ``fetch_allen`` for the
non-receptor targets). This module re-exports them rather than restating them, so a
symbol lives in exactly one place and a fetcher's correction reaches the emitted data
for free. Both fetchers are stdlib-only at import time, so ``generate_data.py`` stays
offline + stdlib-only.

A group target (``alpha1`` = ADRA1A/B/D) maps to several genes; the representative is
the first, matching the convention the fetchers already use for a heteromer (nAChR
α4β2 -> CHRNA4). ``alpha2d`` is deliberately absent: a rodent pharmacological subtype
with no human gene.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fetch"))

from fetch_allen import TARGET_GENES as _TARGET_GENE_LISTS  # noqa: E402
from fetch_gtopdb_class import receptor_genes as _receptor_genes  # noqa: E402

#: receptor id -> its HGNC symbol (61 of the 62 receptors).
RECEPTOR_GENES: dict[str, str] = dict(_receptor_genes())

#: non-receptor target id -> the representative HGNC symbol of the group.
TARGET_GENES: dict[str, str] = {
    tid: genes[0] for tid, genes in _TARGET_GENE_LISTS.items() if genes
}
