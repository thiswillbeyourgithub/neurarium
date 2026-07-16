#!/usr/bin/env python
"""Unit tests for tools/fetch/fetch_ki.py's Ki-ownership guard.

Stdlib ``unittest`` only (no deps), matching test_generate.py. Runnable directly:

    python tools/tests/test_fetch_ki.py

pytest-discoverable. These lock the ``--apply`` idempotency contract: the pass may
only write into a Ki slot it *owns* (empty, or its own prior non-curated PDSP Ki). A
``wikipedia_pharm`` fallback Ki (corpus #9) or a hand-curated Ki belongs to another
tool and must be left untouched, else annotate would flip its corpus to ``pdsp_ki``
and the next --apply's strip would delete the binding (the destructive oscillation
this guard fixes). No CSV needed: ``_ki_owned_by_pdsp`` is a pure predicate.

Built with the help of Claude Code.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fetch"))
import fetch_ki  # noqa: E402


def _binding(corpus=None, curated=False, has_ki=True):
    if not has_ki:
        return {"target": "x", "affinity_only": True}
    src = {}
    if corpus is not None:
        src["corpus"] = corpus
    if curated:
        src["curated"] = True
    return {"target": "x", "affinity_only": True, "ki": {"median": 100.0, "source": src}}


class KiOwnershipTest(unittest.TestCase):
    def test_no_ki_is_ownable(self):
        # An empty slot is fetch_ki's to fill (annotate or auto-add).
        self.assertTrue(fetch_ki._ki_owned_by_pdsp(_binding(has_ki=False)))

    def test_pdsp_non_curated_is_ownable(self):
        # Its own prior output: refreshable in place.
        self.assertTrue(fetch_ki._ki_owned_by_pdsp(_binding(corpus="pdsp_ki")))

    def test_pdsp_curated_is_not_ownable(self):
        # Hand-attached weak binder (source.curated): never overwritten/stripped.
        self.assertFalse(fetch_ki._ki_owned_by_pdsp(_binding(corpus="pdsp_ki", curated=True)))

    def test_wikipedia_fallback_is_not_ownable(self):
        # The regression this test exists for: a wikipedia_pharm Ki must be left
        # alone, or annotate flips it to pdsp_ki and the next strip deletes it.
        self.assertFalse(fetch_ki._ki_owned_by_pdsp(_binding(corpus="wikipedia_pharm")))

    def test_unknown_corpus_is_not_ownable(self):
        # Any non-PDSP corpus is another tool's slot; only PDSP is owned.
        self.assertFalse(fetch_ki._ki_owned_by_pdsp(_binding(corpus="something_else")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
