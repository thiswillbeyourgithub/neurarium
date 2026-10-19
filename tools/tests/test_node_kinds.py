#!/usr/bin/env python
"""Pin every node-kind list to the one roster in tools/data_generators/node_kinds.py.

The emitted ``meta.provenance_stats.by_kind``, the README label table
(``update_readme_stats.KIND_LABELS``), the viewer registry (``public/js/kinds.js``) and
the claim walk's per-pass kind labels (``tools/sourcing/claim_walk.py``) each name kinds;
a kind added to one and forgotten in another drops silently out of a chart or a tally.
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import update_readme_stats  # noqa: E402
from data_generators.node_kinds import NODE_KINDS, TALLY_ONLY_KINDS  # noqa: E402

META = REPO_ROOT / "public" / "data" / "meta.json"
KINDS_JS = REPO_ROOT / "public" / "js" / "kinds.js"
CLAIM_WALK = REPO_ROOT / "tools" / "sourcing" / "claim_walk.py"

# The claim walk labels its judge passes coarser or finer than the tally: one
# ``receptor_classification`` pass covers the four per-attribute receptor kinds, and
# ``other`` / ``target_other`` collect the citations no tally kind names.
CLAIM_WALK_ONLY_KINDS = {"receptor_classification", "other", "target_other"}


class NodeKindRosterTest(unittest.TestCase):
    def test_roster_has_no_duplicates(self):
        everything = NODE_KINDS + TALLY_ONLY_KINDS
        self.assertEqual(len(everything), len(set(everything)))

    def test_emitted_by_kind_matches_roster(self):
        by_kind = json.loads(META.read_text(encoding="utf-8"))["provenance_stats"]["by_kind"]
        self.assertEqual(set(by_kind), set(NODE_KINDS + TALLY_ONLY_KINDS))

    def test_readme_labels_match_roster(self):
        self.assertEqual(set(update_readme_stats.KIND_LABELS),
                         set(NODE_KINDS + TALLY_ONLY_KINDS))

    def test_viewer_registry_matches_roster(self):
        js = set(re.findall(r'\{\s*kind:\s*"(\w+)"', KINDS_JS.read_text(encoding="utf-8")))
        self.assertTrue(js, "parsed no kind out of public/js/kinds.js")
        # Exact equality: `references` (TALLY_ONLY_KINDS) is outside NODE_KINDS, and the
        # viewer leaves it out on purpose (a pointer at a node, see kinds.js header).
        self.assertEqual(js, set(NODE_KINDS))

    def test_claim_walk_labels_are_known_kinds(self):
        labels = set(re.findall(r'kind\["now"\] = "(\w+)"',
                                CLAIM_WALK.read_text(encoding="utf-8")))
        self.assertTrue(labels, "parsed no kind label out of claim_walk.py")
        self.assertEqual(labels - set(NODE_KINDS) - CLAIM_WALK_ONLY_KINDS, set())


if __name__ == "__main__":
    unittest.main()
