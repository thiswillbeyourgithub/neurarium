#!/usr/bin/env python
"""Unit tests for tools/sourcing/demote_quotes.py.

A flag is not an outcome: while a source a judge rejected is still stored, the node
keeps its green pill and tells the reader a sentence backs a claim it does not. These
cover the three ways that gets resolved (remove, replace, reject a bad replacement) and
the two invariants that make the tool safe to run: it never touches the claim, and it
never silently skips an id it could not reach.

Built with the help of Claude Code.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sourcing"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import demote_quotes as D  # noqa: E402
from data_generators.quote_table import quote_id  # noqa: E402

STAHL = {"corpus": "stahl", "page": 42, "quote": "A wrong sentence.",
         "provenance": "verified"}


def _drug(sources):
    return {"id": "testolol", "categories": ["ssri"], "category_sources": sources}


class DemoteTest(unittest.TestCase):

    def _run(self, tmp, drug, targets, page_text=None):
        """Run the editor over one drug record, returning ``(record, editor)``."""
        pages = {}
        if page_text is not None:
            d = Path(tmp) / "pages"
            d.mkdir(exist_ok=True)
            (d / "42.md").write_text(page_text, encoding="utf-8")
            pages = {"stahl": os.path.relpath(d, D.ROOT)}
        ed = D.Editor(targets, pages)
        return ed.walk(json.loads(json.dumps(drug))), ed

    def test_a_rejected_source_is_removed_and_its_key_with_it(self):
        qid = quote_id(STAHL)
        with tempfile.TemporaryDirectory() as tmp:
            rec, ed = self._run(tmp, _drug([dict(STAHL)]), {qid: {}})
        self.assertEqual(ed.removed, [qid])
        # The key goes, not just its contents: an empty `sources` list would read as
        # "sourced by nothing" rather than as unsourced.
        self.assertNotIn("category_sources", rec)
        # The claim itself is untouched. Demoting a source is not retracting a fact.
        self.assertEqual(rec["categories"], ["ssri"])

    def test_a_sibling_source_survives_the_removal(self):
        qid = quote_id(STAHL)
        other = dict(STAHL, quote="A sentence nobody doubted.")
        with tempfile.TemporaryDirectory() as tmp:
            rec, _ = self._run(tmp, _drug([dict(STAHL), other]), {qid: {}})
        self.assertEqual([s["quote"] for s in rec["category_sources"]], [other["quote"]])

    def test_a_verbatim_replacement_is_written_in_place(self):
        qid = quote_id(STAHL)
        with tempfile.TemporaryDirectory() as tmp:
            rec, ed = self._run(tmp, _drug([dict(STAHL)]),
                                {qid: {"quote": "The better sentence."}},
                                page_text="Preamble. The better sentence. More text.")
        self.assertEqual(ed.replaced, [qid])
        self.assertEqual(rec["category_sources"][0]["quote"], "The better sentence.")

    def test_a_replacement_not_on_the_page_is_rejected_not_written(self):
        qid = quote_id(STAHL)
        with tempfile.TemporaryDirectory() as tmp:
            rec, ed = self._run(tmp, _drug([dict(STAHL)]),
                                {qid: {"quote": "A sentence the book never prints."}},
                                page_text="Preamble. The better sentence. More text.")
        self.assertEqual(ed.rejected, [qid], "a paraphrase was written as a real quote")
        # Rejected means removed, not kept: the honest fallback is no source at all.
        self.assertNotIn("category_sources", rec)

    def test_an_id_that_reaches_nothing_is_reported_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, ed = self._run(tmp, _drug([dict(STAHL)]), {"q_notreal": {}})
        self.assertEqual(ed.removed, [])
        self.assertNotIn("q_notreal", ed.seen,
                         "an unreachable id must fall through to the hand-edit report")


if __name__ == "__main__":
    unittest.main(verbosity=2)
