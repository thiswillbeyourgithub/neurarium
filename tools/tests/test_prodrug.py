#!/usr/bin/env python
"""Unit tests for the prodrug pass (applier gates + the generator's validation).

Stdlib ``unittest`` only; drives ``apply_prodrug.apply`` over a hand-built worklist and
a fake page store in a temp dir, so it runs on a clone lacking the corpus trees::

    python -m unittest discover -t tools/tests -s tools/tests -p test_prodrug.py

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_prodrug as A  # noqa: E402
from judged_fixture import fill  # noqa: E402
import generate_data as G  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)

LINES = [
    "Psilocybin is a prodrug that is converted into the pharmacologically active "
    "compound psilocin in the body.",                                       # 0
    "Psilocybin is a prodrug.",                                              # 1
    "Psilocin is an agonist of the 5-HT2A receptor.",                        # 2
]


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        en = Path(self.tmp.name)
        (en / "psilocybin.md").write_text("Header\n" + "\n".join(LINES) + "\n", "utf-8")
        self.gate = PageGate({"wikipedia_pharm": en})
        self.offered = {"psilocybin": {"candidates": [
            {"corpus": "wikipedia_pharm", "page": "psilocybin", "line": ln} for ln in LINES]}}
        self.drugs = [{"id": "psilocybin", "bindings": [{"target": "5ht2a",
                                                         "action": "agonist"}]},
                      {"id": "sertraline"}]
        self.store: list = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_apply(self, rec):
        rec = fill(dict(rec), self.offered["psilocybin"]["candidates"])
        return A.apply({"psilocybin": rec}, self.offered, self.drugs, self.gate, self.store)

    def test_good_pick_flags_drops_bindings_adds_metabolite(self):
        applied, dropped, rejected = self.run_apply({"index": 0, "metabolite": "Psilocin"})
        self.assertEqual((applied, rejected), (["psilocybin"], []))
        d = self.drugs[0]
        self.assertTrue(d["prodrug"])
        self.assertEqual(d["bindings"], [])
        self.assertEqual(dropped, ["psilocybin: 5ht2a agonist"])
        # One store record for the molecule, a sourced reference on the drug.
        self.assertEqual(self.store, [{"id": "psilocin", "name": "Psilocin"}])
        self.assertEqual(d["metabolites"][0]["id"], "psilocin")
        self.assertEqual(d["metabolites"][0]["sources"][0]["quote"], LINES[0])
        self.assertEqual(d["prodrug_sources"][0]["quote"], LINES[0])

    def test_metabolite_already_in_the_store_is_reused(self):
        """A second prodrug of a known molecule references it instead of copying it."""
        self.store.append({"id": "psilocin", "name": "Psilocin", "bindings": [{"target": "x"}]})
        self.run_apply({"index": 0, "metabolite": "Psilocin"})
        self.assertEqual(len(self.store), 1)
        self.assertEqual(self.store[0]["bindings"], [{"target": "x"}])

    def test_activating_enzyme_substrate_binding_is_kept(self):
        """Levodopa is AADC's substrate: that IS the conversion, so it stays."""
        aadc = {"target": "aadc", "action": "precursor"}
        self.drugs[0]["bindings"].append(aadc)
        _, dropped, _ = self.run_apply({"index": 0, "metabolite": "Psilocin"})
        self.assertEqual(self.drugs[0]["bindings"], [aadc])
        self.assertEqual(dropped, ["psilocybin: 5ht2a agonist"])

    def test_metabolite_not_named_rejected(self):
        _, _, rejected = self.run_apply({"index": 1, "metabolite": "Psilocin"})
        self.assertIn("not named", rejected[0])
        self.assertNotIn("prodrug", self.drugs[0])

    def test_non_prodrug_sentence_rejected(self):
        _, _, rejected = self.run_apply({"index": 2, "metabolite": "Psilocin"})
        self.assertIn("prodrug", rejected[0])

    def test_bad_drug_id_rejected(self):
        _, _, rejected = self.run_apply({"index": 0, "metabolite": "Psilocin",
                                         "drug_id": "psilocybin"})
        self.assertIn("drug_id", rejected[0])

    def test_synonym_in_parentheses_matches(self):
        self.assertEqual(A.names_of("Desmethyldiazepam (nordazepam)"),
                         ["desmethyldiazepam", "nordazepam"])


class GeneratorTest(unittest.TestCase):
    """``_drug_prodrug``: a prodrug may carry no own binding and needs a metabolite,
    else the viewer would double-count it or light nothing."""

    def test_not_a_prodrug_emits_nothing(self):
        self.assertEqual(G._drug_prodrug({"id": "x", "bindings": [{"target": "d2"}]}), {})

    def test_prodrug_with_own_binding_raises(self):
        with self.assertRaises(ValueError):
            G._drug_prodrug({"id": "x", "prodrug": True, "bindings": [{"target": "d2"}],
                             "metabolites": [{"name": "Y"}]})

    def test_prodrug_may_keep_its_precursor_binding(self):
        self.assertEqual(G._drug_prodrug({"id": "x", "prodrug": True,
                                          "bindings": [{"target": "aadc",
                                                        "action": "precursor"}],
                                          "metabolites": [{"name": "Y"}]}),
                         {"prodrug": True})

    def test_prodrug_without_metabolite_raises(self):
        with self.assertRaises(ValueError):
            G._drug_prodrug({"id": "x", "prodrug": True, "bindings": []})

    def test_prodrug_emits_flag(self):
        self.assertEqual(G._drug_prodrug({"id": "x", "prodrug": True,
                                          "metabolites": [{"name": "Y"}]}),
                         {"prodrug": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
