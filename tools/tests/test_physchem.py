#!/usr/bin/env python
"""Unit tests for the physicochemistry pass (PubChem #21 + B3DB #22): the fetcher's join
(CID, name fallback, chirality guard, InChI guard, conflicting labels, combination and
salt drugs) and the generator's validation.

Stdlib ``unittest`` only, hand-built rows, so it runs on a clone lacking the gitignored
``data_sources/``::

    python -m unittest discover -t tools/tests -s tools/tests -p test_physchem.py

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
from lib import drugs_io  # noqa: E402
import fetch_physchem as F  # noqa: E402
from data_generators import physchem as P  # noqa: E402
from data_generators.provenance import _quote_sources  # noqa: E402

OLZ = "InChI=1S/C17H20N4S/c1-12-11-13-16(21-9-7-20(2)8-10-21)18-14-5-3-4-6-15(14)19-17(13)22-12"
OLZ_DRUGBOX = OLZ + "/h3-6,11,18H,7-10H2,1-2H3"
OLZ_TAUTOMER = OLZ + "/h3-6,11,19H,7-10H2,1-2H3"
OTHER = "InChI=1S/C18H13ClN2O3S/c1-24-14-6-2-12(3-7-14)16-17/h2-9H"


def row(no, name, cid, label, inchi, logbb="", group="A", ref="R8|R21|"):
    return {"NO.": str(no), "compound_name": name, "CID": cid, "logBB": logbb,
            "BBB+/BBB-": label, "Inchi": inchi, "group": group, "reference": ref}


class ParseTest(unittest.TestCase):
    def test_drugbox_cid_takes_the_first_id(self):
        self.assertEqual(F.drugbox_cid("x\nPubChem CID | 2130 as HCl: 64150\n"), 2130)
        self.assertEqual(F.drugbox_cid("PubChem CID | 28486 11125"), 28486)
        self.assertIsNone(F.drugbox_cid("ChemSpider | 123"))

    def test_row_cids_reads_floats_and_lists(self):
        self.assertEqual(F.row_cids("3889.0|"), [3889])
        self.assertEqual(F.row_cids("1|2.0"), [1, 2])
        self.assertEqual(F.row_cids(""), [])

    def test_inchi_core_drops_hydrogen_and_stereo_layers(self):
        self.assertEqual(F.inchi_core(OLZ_DRUGBOX), F.inchi_core(OLZ_TAUTOMER))
        self.assertNotEqual(F.inchi_core(OLZ_DRUGBOX), F.inchi_core(OTHER))
        self.assertIsNone(F.inchi_core("not an inchi"))

    def test_salts_mixtures_and_inorganics_are_skipped(self):
        self.assertEqual(F.compound_skip("InChI=1S/C4H8O3.Na/c5-3/h5H"), "a salt or mixture")
        self.assertEqual(F.compound_skip("InChI=1S/Li/q+1"), "inorganic")
        self.assertEqual(F.compound_skip("InChI=1S/ClH.Rb/h1H"), "a salt or mixture")
        self.assertIsNone(F.compound_skip(OLZ_DRUGBOX))
        self.assertIsNone(F.compound_skip("InChI=1S/CH4/h1H4"))   # methane: carbon, no digit
        self.assertEqual(F.compound_skip("InChI=1S/Cl2/c1-2"), "inorganic")  # Cl is not C

    def test_combinations(self):
        self.assertTrue(F.is_combination(
            {"wikipedia": "https://en.wikipedia.org/wiki/Naltrexone/bupropion"}))
        self.assertTrue(F.is_combination({"wikipedia": "https://en.wikipedia.org/wiki/D",
                                          "constituents": ["A", "B"]}))
        self.assertFalse(F.is_combination({"wikipedia": "https://en.wikipedia.org/wiki/X"}))

    def test_one_combination_test_for_every_corpus(self):
        """``drugs_io.is_combination`` is the shared test: an en dash name with no "+"
        (Phentermine–Topiramate) is a combination, a hyphenated name is not, and a salt
        is one product there (physchem alone also refuses it: no single molecule)."""
        self.assertTrue(drugs_io.is_combination({"name": "Phentermine–Topiramate"}))
        self.assertTrue(drugs_io.is_combination({"name": "Naltrexone + Bupropion"}))
        self.assertFalse(drugs_io.is_combination({"name": "N-desmethylclozapine"}))
        salt = {"name": "Dimenhydrinate", "constituents": ["diphenhydramine"]}
        self.assertFalse(drugs_io.is_combination(salt))
        self.assertTrue(F.is_combination(salt))
        self.assertEqual(drugs_io.combo_parts("Phentermine–Topiramate"),
                         ["Phentermine", "Topiramate"])


class MatchTest(unittest.TestCase):
    OLANZAPINE = {"id": "olanzapine", "name": "Olanzapine"}

    def test_cid_match_wins_over_name(self):
        rows = [row(1, "olanzapine", "4585", "BBB+", OLZ_DRUGBOX),
                row(2, "olanzapine", "135398745", "BBB-", OLZ_TAUTOMER)]
        how, kept, refused = F.match_rows(self.OLANZAPINE, 4585, OLZ_DRUGBOX, rows)
        self.assertEqual((how, [r["NO."] for r in kept], refused), ("cid", ["1"], []))

    def test_name_fallback_keeps_the_tautomer_refuses_another_structure(self):
        rows = [row(916, "olanzapine", "135398745", "BBB+", OLZ_TAUTOMER, "0.78"),
                row(3985, "olanzapine", "100004585", "BBB+", OTHER, group="B")]
        how, kept, refused = F.match_rows(self.OLANZAPINE, 4585, OLZ_DRUGBOX, rows)
        self.assertEqual(how, "name")
        self.assertEqual([r["NO."] for r in kept], ["916"])
        self.assertEqual([r["NO."] for r in refused], ["3985"])

    def test_name_fallback_is_exact(self):
        rows = [row(1, "olanzapine pamoate", "", "BBB+", OLZ_TAUTOMER)]
        self.assertEqual(F.match_rows(self.OLANZAPINE, 4585, OLZ_DRUGBOX, rows)[0], None)

    def test_chirality_guard(self):
        # A racemate (no chirality.STEREO entry) never takes a single enantiomer's row,
        # takes an explicitly racemic one; cocaine (STEREO "-") takes its own.
        rac = {"id": "olanzapine", "name": "Olanzapine"}
        self.assertFalse(F.name_matches("(-)-olanzapine", rac))
        self.assertTrue(F.name_matches("(±)-olanzapine", rac))
        self.assertTrue(F.name_matches("OLANZAPINE", rac))
        coc = {"id": "cocaine", "name": "Cocaine"}
        self.assertTrue(F.name_matches("(-)-cocaine", coc))
        self.assertFalse(F.name_matches("(+)-cocaine", coc))

    def test_no_row(self):
        self.assertEqual(F.match_rows(self.OLANZAPINE, 1, OLZ_DRUGBOX, []), (None, [], []))


class ClaimTest(unittest.TestCase):
    def test_agreeing_rows_give_a_label_and_a_logbb_range(self):
        rows = [row(923, "olanzapine", "135398745", "BBB+", OLZ_TAUTOMER, "0.8"),
                row(916, "olanzapine", "135398745", "BBB+", OLZ_TAUTOMER, "0.78"),
                row(3000, "olanzapine", "135398745", "BBB+", OLZ_TAUTOMER, group="B")]
        claim, status = F.bbb_claim(rows, "135398745")
        self.assertEqual(status, "found")
        self.assertEqual((claim["label"], claim["logbb"], claim["logbb_max"]),
                         ("BBB+", 0.78, 0.8))
        self.assertEqual([s["quote"].split(":")[0] for s in claim["sources"]],
                         ["B3DB row 916", "B3DB row 923", "B3DB row 3000"])
        self.assertTrue(all(s["page"] == "135398745" and s["extraction"] == "code"
                            for s in claim["sources"]))

    def test_one_logbb_has_no_max(self):
        claim, _ = F.bbb_claim([row(1, "x", "1", "BBB-", OTHER, "-1.2")], "1")
        self.assertEqual(claim["logbb"], -1.2)
        self.assertNotIn("logbb_max", claim)

    def test_conflicting_labels_publish_nothing(self):
        rows = [row(1, "x", "1", "BBB+", OTHER), row(2, "x", "1", "BBB-", OTHER)]
        self.assertEqual(F.bbb_claim(rows, "1"), (None, "conflict"))

    def test_row_line_is_on_the_page(self):
        r = row(986, "citalopram", "2771", "BBB+", OTHER, "0.99", ref="R42|R18|")
        self.assertEqual(F.row_line(r), "B3DB row 986: citalopram | CID 2771 | logBB 0.99 "
                                        "| BBB+ | group A | references R42, R18")

    def test_pubchem_page_round_trips(self):
        text = F.pubchem_page(2771, {"Title": "Citalopram", "XLogP": 3.2, "TPSA": 36.3,
                                     "MolecularWeight": "324.4", "InChI": OLZ}, "2026-10-15")
        self.assertIn("XLogP3: 3.2\n", text)
        self.assertIn("Topological polar surface area: 36.3 Å²\n", text)
        self.assertIn("fetched: 2026-10-15\n", text)
        claims = F.pubchem_claims(2771, text)
        self.assertEqual(claims["xlogp"]["value"], 3.2)
        self.assertEqual(claims["tpsa"]["sources"][0]["quote"],
                         "Topological polar surface area: 36.3 Å²")

    def test_missing_xlogp_gives_no_claim(self):
        text = F.pubchem_page(1, {"TPSA": 10}, "2026-10-15")
        self.assertEqual(set(F.pubchem_claims(1, text)), {"tpsa"})


class GeneratorTest(unittest.TestCase):
    SRC = [{"corpus": "pubchem", "page": "1", "quote": "XLogP3: 3.2",
            "provenance": "verified", "extraction": "code"}]

    def emit(self, entry):
        return P.drug_physchem("x", _quote_sources, {"drugs": {"x": entry}})

    def test_emits_values_and_sources(self):
        out = self.emit({"xlogp": {"value": 3.2, "sources": self.SRC},
                         "bbb": {"label": "BBB+", "logbb": 0.78, "logbb_max": 0.8,
                                 "match": "name", "sources": self.SRC}})
        self.assertEqual(out["xlogp"], 3.2)
        self.assertEqual(out["bbb"], {"label": "BBB+", "logbb": 0.78, "logbb_max": 0.8})
        self.assertEqual(out["bbb_sources"][0]["corpus"], "pubchem")
        self.assertNotIn("tpsa", out)

    def test_absent_drug_emits_nothing(self):
        self.assertEqual(P.drug_physchem("y", _quote_sources, {"drugs": {}}), {})

    def test_bad_label_or_value_raises(self):
        with self.assertRaises(ValueError):
            self.emit({"bbb": {"label": "maybe", "sources": self.SRC}})
        with self.assertRaises(ValueError):
            self.emit({"tpsa": {"value": "36", "sources": self.SRC}})
        with self.assertRaises(ValueError):
            self.emit({"bbb": {"label": "BBB+", "logbb": 1, "logbb_max": 0.5}})


if __name__ == "__main__":
    unittest.main()
