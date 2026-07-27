#!/usr/bin/env python
"""Unit tests for tools/sourcing/apply_gtopdb_ki.py's idempotency rollback.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable
directly::

    python tools/tests/test_apply_gtopdb_ki.py

pytest-discoverable. ``strip_previous`` is the applier's "undo my own prior
write" step, run over every binding before the merge so a re-run rebuilds rather
than stacks. It has to undo exactly what the script wrote and nothing else: a
hand-authored ``gtopdb_ki`` source cites the same corpus, so telling them apart
by corpus alone quietly deleted furosemide's GABA-A alpha6 citation on every run.

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sourcing"))
import apply_gtopdb_ki  # noqa: E402

CORPUS = apply_gtopdb_ki.CORPUS


def _source(quote="a verbatim interaction row"):
    return {"corpus": CORPUS, "page": "furosemide", "quote": quote,
            "provenance": "verified"}


class StripPreviousTest(unittest.TestCase):
    def test_our_direction_write_is_rolled_back(self):
        """The write we DO make: an affinity-only binding given a provisional action
        plus the source that justified it. Both go, so the merge can redo them."""
        binding = {"target": "d2", "action": "agonist", "provisional_action": True,
                   "sources": [_source()]}
        apply_gtopdb_ki.strip_previous(binding)
        self.assertEqual(binding, {"target": "d2", "affinity_only": True})

    def test_hand_authored_source_survives(self):
        """The write we never make: a binding whose direction was authored by hand,
        citing GtoPdb by hand too (no ``provisional_action``). Stripping it would
        drop a real, quote-gated citation and silently downgrade the node."""
        binding = {"target": "gaba_a", "action": "nam", "sources": [_source()]}
        before = {"target": "gaba_a", "action": "nam", "sources": [_source()]}
        apply_gtopdb_ki.strip_previous(binding)
        self.assertEqual(binding, before)

    def test_our_ki_write_is_rolled_back_but_other_sources_stay(self):
        """A Ki we wrote lives under ``ki.source``; it is independent of the
        direction, so rolling it back must not touch a hand-authored ``sources``."""
        binding = {"target": "d3", "action": "agonist", "sources": [_source()],
                   "ki": {"median": 1.0, "source": {"corpus": CORPUS}}}
        apply_gtopdb_ki.strip_previous(binding)
        self.assertNotIn("ki", binding)
        self.assertEqual(binding["sources"], [_source()])
        self.assertEqual(binding["action"], "agonist")

    def test_measured_ki_from_another_corpus_is_kept(self):
        binding = {"target": "sert", "action": "reuptake_inhibitor",
                   "ki": {"median": 1.0, "source": {"corpus": "pdsp_ki"}}}
        apply_gtopdb_ki.strip_previous(binding)
        self.assertIn("ki", binding)

    def test_rollback_removes_only_one_of_two_gtopdb_sources(self):
        """A binding can carry both: one hand-authored citation and the one we
        appended with the direction. Exactly the appended (last) one goes."""
        hand = _source("the hand-picked row")
        ours = _source("the row the applier appended")
        binding = {"target": "d2", "action": "agonist", "provisional_action": True,
                   "sources": [hand, ours]}
        apply_gtopdb_ki.strip_previous(binding)
        self.assertEqual(binding["sources"], [hand])
        self.assertTrue(binding["affinity_only"])


if __name__ == "__main__":
    unittest.main()
