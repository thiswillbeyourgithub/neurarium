"""The animal_evidence flag (quotes/animal_evidence.py) and the species vocabulary it
folds every corpus's spelling into (tools/species.py)."""
import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from data_generators.quotes.animal_evidence import apply_animal_evidence  # noqa: E402
from lib.species import SPECIES, species_key  # noqa: E402

ROOT = TOOLS.parent


def _rat(q="rat line"):
    return {"corpus": "gtopdb", "page": 1, "quote": q, "species": "Rat",
            "provenance": "verified"}


def _run(**kw):
    args = {"drugs": [], "metabolites": [], "projections": [], "receptors": [],
            "targets": {}}
    args.update(kw)
    return apply_animal_evidence(**args)


class SpeciesKeyTest(unittest.TestCase):
    def test_every_corpus_spelling_folds(self):
        cases = {"HUMAN": "human", "? HUMAN": "human", "GUINEA PIG": "guinea_pig",
                 "PIG": "pig", "NEONATAL RAT": "rat", "N1E-115": "mouse",
                 "C0S-7": "monkey", "Rats, Wistar": "rat", "Macaca mulatta": "monkey",
                 "Mice, Inbred C57BL": "mouse", "Rat": "rat", "Monkey": "monkey"}
        for label, key in cases.items():
            self.assertEqual(species_key(label), key, label)
        self.assertIsNone(species_key("Animals"))

    def test_every_key_has_both_viewer_labels(self):
        i18n = (ROOT / "public" / "js" / "i18n.js").read_text("utf-8")
        for key in SPECIES:
            self.assertEqual(i18n.count(f'"species.{key}":'), 2, key)


class AnimalEvidenceTest(unittest.TestCase):
    def test_rat_only_binding_is_flagged_with_its_species(self):
        b = {"target": "5ht7", "sources": [_rat()],
             "ki": {"n_human": 0, "source": {"corpus": "pdsp_ki", "species": "GUINEA PIG"}}}
        counts = _run(drugs=[{"id": "x", "bindings": [b]}])
        self.assertEqual(counts["drug_bindings"], 1)
        bullet = b["uncertainty"][-1]
        self.assertEqual(bullet["kind"], "animal_evidence")
        self.assertEqual(bullet["args"], {"species": ["guinea_pig", "rat"]})
        self.assertTrue(bullet["sources"])

    def test_one_human_or_unknown_source_clears_it(self):
        human_ki = {"target": "a", "sources": [_rat()],
                    "ki": {"n_human": 2, "source": {"corpus": "pdsp_ki", "species": "RAT"}}}
        book = {"target": "b", "sources": [_rat(), {"corpus": "stahl", "page": 3,
                                                    "quote": "q"}]}
        monkey = {"target": "c", "sources": [_rat(), dict(_rat(), species="Monkey")]}
        _run(drugs=[{"id": "x", "bindings": [human_ki, book, monkey]}])
        for b in (human_ki, book, monkey):
            self.assertNotIn("uncertainty", b, b["target"])

    def test_projection_sub_claim_and_location_are_flagged(self):
        p = {"from": "a", "to": "b", "sources": [{"corpus": "kandel", "quote": "x"}],
             "claims": {"sign": {"sources": [_rat()]}}}
        r = {"id": "d2", "location_sources": {"hippocampus": [_rat()],
                                             "striatum": [dict(_rat(), species="Human")]}}
        counts = _run(projections=[p], receptors=[r])
        self.assertNotIn("uncertainty", p)
        self.assertEqual(p["claims"]["sign"]["uncertainty"][0]["kind"], "animal_evidence")
        self.assertEqual(set(r["location_uncertainty"]), {"hippocampus"})
        self.assertEqual((counts["projection_sign"], counts["receptor_locations"]), (1, 1))

    def test_europepmc_species_comes_from_the_ledger(self):
        ledger = json.loads((TOOLS / "generated_cache" / "europepmc_species.json")
                            .read_text("utf-8"))
        rat_pmid = next(k for k, v in ledger.items() if v == ["rat"])
        b = {"target": "t", "sources": [{"corpus": "europepmc", "page": rat_pmid,
                                         "quote": "q"}]}
        _run(drugs=[{"id": "x", "bindings": [b]}])
        self.assertEqual(b["uncertainty"][0]["args"], {"species": ["rat"]})
        stray = {"target": "t", "sources": [{"corpus": "europepmc", "page": "0",
                                             "quote": "q"}]}
        with self.assertRaises(KeyError):
            _run(drugs=[{"id": "x", "bindings": [stray]}])


if __name__ == "__main__":
    unittest.main()
