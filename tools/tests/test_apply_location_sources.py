"""apply_location_sources.py writes its cache in the committed format, so a re-run
diffs only the sources it changed, never every line's indentation."""

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "sourcing"))
sys.path.insert(0, str(TOOLS))

import apply_location_sources as A  # noqa: E402


class SerializeTest(unittest.TestCase):
    def test_round_trips_the_committed_cache_byte_for_byte(self):
        raw = A.OUT.read_text(encoding="utf-8")
        self.assertEqual(A.serialize(json.loads(raw)), raw)


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


if __name__ == "__main__":
    unittest.main()
