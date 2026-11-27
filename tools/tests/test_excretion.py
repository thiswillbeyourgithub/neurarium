#!/usr/bin/env python
"""Unit tests for the excretion pass (kind ``drug_excretion``): the vocabulary patterns,
the applier's gates and the generator's validation.

Stdlib ``unittest`` only, hand-built inputs, so it runs on a clone lacking the
gitignored ``data_sources/``::

    python -m unittest discover -t tools/tests -s tools/tests -p test_excretion.py

Built with the help of Claude Code.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_excretion as A  # noqa: E402
from judged_fixture import fill  # noqa: E402
from data_generators import excretion as X  # noqa: E402
from data_generators.provenance import _quote_sources  # noqa: E402

LINE0 = "About 95% of a dose is excreted unchanged in the urine."
LINE1 = "Renal excretion is increased in acidic urine (pH below 5.6)."


class VocabularyTest(unittest.TestCase):
    def test_says_and_named(self):
        self.assertTrue(X.says("route", "renal", LINE0))
        self.assertFalse(X.says("route", "fecal", LINE0))
        self.assertTrue(X.says("urine_ph", "acidic_faster", LINE1))
        self.assertFalse(X.says("urine_ph", "nope", LINE1))
        self.assertEqual(X.named(LINE0), ["route:renal", "unchanged:urine"])
        self.assertIn("urine_ph:dependent", X.named(LINE1))

    def test_french_faeces_with_grave_accent(self):
        # BDPM RCPs spell it "fèces" (grave), not "féces": the fecal route was unmatched.
        line = "la radioactivité totale est principalement excrétée dans les fèces (79 %)"
        self.assertTrue(X.says("route", "fecal", line))

    def test_is_span(self):
        self.assertTrue(X.is_span("95%", LINE0))
        self.assertTrue(X.is_span("ABOUT  95%", LINE0))
        self.assertFalse(X.is_span("80%", LINE0))
        self.assertFalse(X.is_span("9", LINE0))

    def test_meta_labels_drop_patterns(self):
        meta = X.meta_labels()
        self.assertEqual(list(meta), list(X.ASPECTS))
        self.assertNotIn("attests", meta["route"]["values"]["renal"])
        # Every label is exactly {en, fr}, the shape externalize collapses to a string;
        # a label spread beside "values" shipped as an object and crashed the panel.
        self.assertEqual(set(meta["route"]), {"label", "values"})
        self.assertEqual(set(meta["route"]["label"]), {"en", "fr"})


class FakePages:
    def __init__(self, text):
        self.text = text

    def on_page(self, corpus, page, line):
        return line in self.text


class ApplierGateTest(unittest.TestCase):
    OFFERED = {"lithium": {"name": "Lithium", "candidates": [
        {"index": 0, "corpus": "wikipedia_pharm", "page": "lithium", "line": LINE0},
        {"index": 1, "corpus": "dailymed", "page": "abc", "line": LINE1}]}}

    def gate(self, judged, page=LINE0 + "\n" + LINE1):
        judged = {d: [fill(dict(p), self.OFFERED.get(d, {}).get("candidates", []))
                      for p in ps] for d, ps in judged.items()}
        return A.gate(judged, self.OFFERED, {"lithium", "clozapine"}, FakePages(page))

    def test_accepts_and_merges_one_node_per_aspect_value(self):
        out, rej = self.gate({"lithium": [
            {"index": 0, "aspect": "unchanged", "value": "urine", "amount": "95%"},
            {"index": 0, "aspect": "route", "value": "renal"},
            {"index": 1, "aspect": "route", "value": "renal"},
            {"index": 1, "aspect": "urine_ph", "value": "acidic_faster"}]})
        self.assertEqual(rej, [])
        nodes = {(n["aspect"], n["value"]): n for n in out["lithium"]}
        self.assertEqual(nodes[("unchanged", "urine")]["amount"], "95%")
        self.assertEqual(len(nodes[("route", "renal")]["sources"]), 2)
        self.assertEqual(nodes[("route", "renal")]["sources"][0],
                         {"corpus": "wikipedia_pharm", "page": "lithium", "quote": LINE0,
                          "provenance": "verified"})

    def test_rejections(self):
        out, rej = self.gate({
            "ghost": [{"index": 0, "aspect": "route", "value": "renal"}],
            "clozapine": [{"index": 0, "aspect": "route", "value": "renal"}],
            "lithium": [
                {"index": 9, "aspect": "route", "value": "renal"},
                {"index": 0, "qid": "deadbeef", "aspect": "route", "value": "renal"},
                {"index": 0, "aspect": "route", "value": "lungs"},
                {"index": 0, "aspect": "route", "value": "fecal"},
                {"index": 0, "aspect": "unchanged", "value": "urine", "amount": "80%"}]})
        self.assertEqual(out, {})
        joined = "\n".join(rej)
        self.assertEqual(len(rej), 7, joined)
        for why in ("not a dataset drug", "offers no candidate", "not in excretion.ASPECTS",
                    "does not name it", "not a span"):
            self.assertIn(why, joined)

    def test_quote_must_be_on_the_page(self):
        out, rej = self.gate({"lithium": [{"index": 0, "aspect": "route", "value": "renal"}]},
                             page="other text")
        self.assertEqual(out, {})
        self.assertIn("quote not found", rej[0])

    def test_undecided_lists_offered_drugs_with_no_key(self):
        self.assertEqual(A.undecided({}, self.OFFERED), ["lithium"])
        self.assertEqual(A.undecided({"lithium": []}, self.OFFERED), [])


class JudgedCoverageTest(unittest.TestCase):
    """Every drug the committed worklist offers has an explicit decision."""

    def test_every_offered_drug_is_judged(self):
        cache = ROOT / "tools" / "generated_cache"
        worklist = json.loads((cache / "excretion_worklist.json").read_text(encoding="utf-8"))
        judged = json.loads((cache / "excretion_judged.json").read_text(encoding="utf-8"))
        self.assertEqual(A.undecided(judged, worklist), [])


class GeneratorTest(unittest.TestCase):
    SRC = [{"corpus": "wikipedia_pharm", "page": "x", "quote": LINE0, "provenance": "verified"}]

    def run_rows(self, rows):
        return X.drug_excretion("x", _quote_sources, {"drugs": {"x": rows}})

    def test_sorted_in_vocabulary_order(self):
        rows = self.run_rows([
            {"aspect": "urine_ph", "value": "dependent", "sources": self.SRC},
            {"aspect": "unchanged", "value": "urine", "amount": "95%", "sources": self.SRC},
            {"aspect": "route", "value": "renal", "sources": self.SRC}])["excretion"]
        self.assertEqual([(r["aspect"], r["value"]) for r in rows],
                         [("route", "renal"), ("unchanged", "urine"), ("urine_ph", "dependent")])
        self.assertEqual(rows[1]["amount"], "95%")
        self.assertEqual(X.drug_excretion("y", _quote_sources, {"drugs": {}}), {})

    def test_validation(self):
        with self.assertRaises(KeyError):
            self.run_rows([{"aspect": "route", "value": "lungs", "sources": self.SRC}])
        with self.assertRaises(ValueError):
            self.run_rows([{"aspect": "route", "value": "renal", "sources": []}])
        with self.assertRaises(ValueError):
            self.run_rows([{"aspect": "route", "value": "renal", "sources": self.SRC}] * 2)
        with self.assertRaises(ValueError):
            self.run_rows([{"aspect": "unchanged", "value": "urine", "amount": "80%",
                            "sources": self.SRC}])

    def test_cache_is_valid(self):
        if not X.CACHE.exists():
            self.skipTest("no excretion cache yet")
        data = json.loads(X.CACHE.read_text(encoding="utf-8"))
        for did in data["drugs"]:
            X.drug_excretion(did, _quote_sources, data)


if __name__ == "__main__":
    unittest.main()
