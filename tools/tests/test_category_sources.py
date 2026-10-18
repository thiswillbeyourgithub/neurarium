#!/usr/bin/env python
"""Unit tests for ``apply_category_sources.apply_wikipedia``, the Wikipedia input mode.

Stdlib ``unittest`` only. Drives the gate over a hand-built worklist and a fake page store
in a temp dir, so it runs on a clone that lacks the gitignored corpus #9 / #10 trees::

    python tools/tests/test_category_sources.py

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_category_sources as A  # noqa: E402
from judged_fixture import refs  # noqa: E402

PAGE = "Header\nRopinirole is a dopamine agonist and works by triggering D2 receptors.\n"


class WikipediaGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        en = Path(self.tmp.name) / "en"
        en.mkdir()
        (en / "ropinirole.md").write_text(PAGE, encoding="utf-8")
        self.pages = {"wikipedia_pharm": en}
        self.worklist = {"ropinirole": {"candidates": [
            {"corpus": "wikipedia_pharm", "page": "ropinirole",
             "line": "Ropinirole is a dopamine agonist and works by triggering D2 receptors."},
            {"corpus": "wikipedia_pharm", "page": "ropinirole",
             "line": "Ropinirole is an atypical antipsychotic."},
        ]}}

    def tearDown(self):
        self.tmp.cleanup()

    def cands(self):
        return self.worklist["ropinirole"]["candidates"]

    def test_writes_a_quote_found_on_its_page(self):
        drugs = [{"id": "ropinirole", "categories": ["other"]}]
        n, misses = A.apply_wikipedia(drugs, self.worklist, {"ropinirole": refs(self.cands(), 0)}, self.pages)
        self.assertEqual((n, misses), (1, []))
        self.assertEqual(drugs[0]["category_sources"], [{
            "corpus": "wikipedia_pharm", "page": "ropinirole",
            "quote": self.worklist["ropinirole"]["candidates"][0]["line"],
            "provenance": "verified"}])

    def test_rejects_a_quote_not_on_the_page(self):
        drugs = [{"id": "ropinirole", "categories": ["other"]}]
        n, misses = A.apply_wikipedia(drugs, self.worklist, {"ropinirole": refs(self.cands(), 1)}, self.pages)
        self.assertEqual(n, 0)
        self.assertNotIn("category_sources", drugs[0])
        self.assertIn("quote not on", misses[0])

    def test_never_overrides_a_stahl_source(self):
        stahl = [{"corpus": "stahl", "page": 700, "quote": "Dopamine agonist",
                  "provenance": "verified"}]
        drugs = [{"id": "ropinirole", "categories": ["other"],
                  "category_sources": list(stahl)}]
        n, misses = A.apply_wikipedia(drugs, self.worklist, {"ropinirole": refs(self.cands(), 0)}, self.pages)
        self.assertEqual(n, 0)
        self.assertEqual(drugs[0]["category_sources"], stahl)
        self.assertIn("already carries", misses[0])

    def test_null_and_out_of_range_picks_write_nothing(self):
        drugs = [{"id": "ropinirole", "categories": ["other"]}]
        self.assertEqual(A.apply_wikipedia(drugs, self.worklist, {"ropinirole": None},
                                           self.pages), (0, []))
        n, misses = A.apply_wikipedia(drugs, self.worklist, {"ropinirole": refs(self.cands(), 9)}, self.pages)
        self.assertEqual(n, 0)
        self.assertIn("out of range", misses[0])



class ScopedWorklistMergeTest(unittest.TestCase):
    """``fetch_category_worklist --only`` must MERGE into the existing worklist: the
    committed judged file answers by index into every other drug's entry, and an
    overwrite silently orphaned them (it once dropped 5600 lines of candidates)."""

    def test_only_build_keeps_other_drugs(self):
        from lib.worklist_io import merge_scoped
        existing = {"vocabulary": {"a": "A"},
                    "drugs": {"x": {"candidates": [1]}, "y": {"candidates": [2]}}}
        scoped = {"vocabulary": {"a": "A", "b": "B"}, "drugs": {"y": {"candidates": [3]}}}
        out = merge_scoped(existing, scoped, "drugs")
        self.assertEqual(out["drugs"], {"x": {"candidates": [1]}, "y": {"candidates": [3]}})
        self.assertEqual(out["vocabulary"], {"a": "A", "b": "B"})

    def test_list_worklist_merge_keeps_other_entries(self):
        """``fetch_metabolite_bindings --only`` once overwrote all 24 metabolite entries
        with the one it rebuilt; the list-shaped merge keeps them, in place."""
        from lib.worklist_io import merge_scoped_list
        existing = [{"key": "a", "v": 1}, {"key": "b", "v": 2}]
        out = merge_scoped_list(existing, [{"key": "b", "v": 3}, {"key": "c", "v": 4}], "key")
        self.assertEqual(out, [{"key": "a", "v": 1}, {"key": "b", "v": 3},
                               {"key": "c", "v": 4}])


if __name__ == "__main__":
    unittest.main()
