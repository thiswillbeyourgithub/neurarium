"""apply_location_sources.py prunes and refutes cached location sources (its cache's
format is held by test_cache_io, like every other cache's)."""

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "sourcing"))
sys.path.insert(0, str(TOOLS))

import apply_location_sources as A  # noqa: E402


class PruneTest(unittest.TestCase):
    """A cached source whose owner or region the data no longer claims is dropped,
    so a removed owner's sources cannot sit in the cache going stale unseen."""

    def test_drops_unclaimed_owner_and_region(self):
        src = {"corpus": "allen_ahba", "page": "G", "quote": "q"}
        buckets = {"receptor": {"r1": {"frontal": [src], "gone": [src]}},
                   "target": {"beta": {"accumbens": [src]}, "t1": {"pons": [src]}}}
        dropped = A.prune_unclaimed(buckets, {"r1": {"frontal"}}, {"t1": {"pons"}})
        self.assertEqual(buckets, {"receptor": {"r1": {"frontal": [src]}},
                                   "target": {"t1": {"pons": [src]}}})
        self.assertEqual(len(dropped), 2)

    def test_committed_cache_has_nothing_to_prune(self):
        raw = json.loads(A.OUT.read_text(encoding="utf-8"))
        buckets = {"receptor": raw.get("receptors", {}), "target": raw.get("targets", {})}
        self.assertEqual(A.prune_unclaimed(buckets, *A.owner_regions()), [])


class RefutedTest(unittest.TestCase):
    """The applier gate agrees with check_data's: lenient only on an absent tree."""

    def test_missing_or_empty_page_in_present_tree_refutes(self):
        import tempfile
        from pipeline.gate import PageGate
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "pages"
            tree.mkdir()
            (tree / "G.md").write_text("G detected in frontal\n", "utf-8")
            (tree / "E.md").write_text("", "utf-8")
            gate = PageGate({"allen_ahba": tree, "gone": Path(tmp) / "absent"})
            self.assertFalse(gate.refuted("allen_ahba", "G", "G detected in frontal"))
            self.assertTrue(gate.refuted("allen_ahba", "G", "G detected in pons"))
            self.assertTrue(gate.refuted("allen_ahba", "MISSING", "G detected in frontal"))
            self.assertTrue(gate.refuted("allen_ahba", "E", "G detected in frontal"))
            self.assertFalse(gate.refuted("gone", "G", "anything"))


if __name__ == "__main__":
    unittest.main()
