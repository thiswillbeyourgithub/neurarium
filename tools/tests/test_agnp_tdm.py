"""AGNP TDM guideline corpus #19: the Table 5 cell parsers (fetch_agnp_tdm.py) and the
generator side (data_generators/tdm.py): one range per drug or nothing, and the
Table 1 enzyme merge (confirm an existing substrate row, else add one)."""

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "fetch"))
sys.path.insert(0, str(TOOLS))

import fetch_agnp_tdm as F  # noqa: E402
from data_generators import tdm as T  # noqa: E402
from data_generators.provenance import _quote_sources  # noqa: E402


class CellParserTest(unittest.TestCase):
    def test_clean_joins_hyphen_breaks_and_drops_revision_marker(self):
        self.assertEqual(F.clean("Brexpi­\n+\nprazole"), "Brexpiprazole")
        self.assertEqual(F.clean("Ampheta-\nmine"), "Amphetamine")

    def test_single_range_with_analyte(self):
        self.assertEqual(
            F.parse_range("80–200 ng/mL (amitriptyline plus nortriptyline)"),
            {"low": 80, "high": 200, "unit": "ng/mL",
             "analyte": "amitriptyline + nortriptyline"})

    def test_thousands_and_decimal_and_units(self):
        self.assertEqual(F.parse_range("0.4–0.8 mmol/L"),
                         {"low": 0.4, "high": 0.8, "unit": "mmol/L"})
        self.assertEqual(F.parse_value("1,000 ng/mL"), {"value": 1000, "unit": "ng/mL"})
        self.assertEqual(F.parse_range("50–100 μg/ml")["unit"], "µg/mL")

    def test_two_ranges_or_qualified_range_is_refused(self):
        self.assertIsNone(F.parse_range("60–350 ng/mL 10–60 ng/mL"))
        self.assertIsNone(F.parse_range("Not established"))
        self.assertIsNone(F.parse_range("20–50 ng/mL for children 6–12 y"))

    def test_level(self):
        self.assertEqual(F.parse_level("+ 2"), 2)
        self.assertIsNone(F.parse_level("5"))

    def test_drug_ids_uses_aliases_and_parenthesis_prefix(self):
        idx = F.roster_index([{"id": "clobazam", "name": "Clobazam"},
                              {"id": "ketamine", "name": "Ketamine"},
                              {"id": "esketamine", "name": "Esketamine"}])
        self.assertEqual(F.drug_ids("Ketamine/esketamine", idx), ["ketamine", "esketamine"])
        self.assertEqual(F.drug_ids("Clobazam (norclobazam)", idx), ["clobazam"])
        self.assertEqual(F.drug_ids("Ginkgo", idx), [])


class MidWordMarkupTest(unittest.TestCase):
    """Table 1's paliperidone row prints ``9-hydroxyrisperi<u>done)</u>`` (an underline
    starting mid-word). The shared fold dropped the tag as a space, splitting the word,
    so the row's quote never matched its page and paliperidone lost its CYP3A4 / UGT
    rows. A mid-word tag now vanishes; a tag between words still separates them."""

    PAGE = "Paliperidone (9-hydroxyrisperi<u>done)</u>\n\nRenal clearance, CYP3A4, UGT\n"

    def test_fold_keeps_the_word_whole(self):
        self.assertEqual(F.normalize_for_match("risperi<u>done)</u> x <u>CYP1A2</u>"),
                         "risperidone x cyp1a2")

    def test_table1_row_is_confirmed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "10.md").write_text(self.PAGE, encoding="utf-8")
            idx = F.roster_index([{"id": "paliperidone", "name": "Paliperidone"}])
            rows = [{"page": 10, "drug": "Paliperidone (9-hydroxyrisperidone)",
                     "enzymes": "Renal clearance, CYP3A4, UGT"}]
            got = F.enzyme_confirmations(rows, idx, F.PageGate({F.CORPUS: Path(d)}))
        self.assertEqual([r["enzyme"] for r in got["paliperidone"]], ["cyp3a4", "ugt"])


class GeneratorTest(unittest.TestCase):
    SRC = [{"corpus": "agnp_tdm", "page": 28, "quote": "Clozapine 12 h 350–600 ng/mL",
            "provenance": "verified", "extraction": "code"}]

    def _with(self, data):
        old = T._DATA
        T._DATA = data
        self.addCleanup(setattr, T, "_DATA", old)

    def test_range_and_alert_are_two_sourced_fields(self):
        self._with({"ranges": {"x": {"low": 350, "high": 600, "unit": "ng/mL",
                                     "tdm_level": 1, "sources": self.SRC,
                                     "alert": {"value": 1000, "unit": "ng/mL"}}}})
        out = T.drug_tdm("x", _quote_sources)
        self.assertEqual(out["therapeutic_range"],
                         {"low": 350, "high": 600, "unit": "ng/mL", "tdm_level": 1})
        self.assertEqual(out["alert_level"], {"value": 1000, "unit": "ng/mL"})
        self.assertEqual(out["alert_level_sources"][0]["page"], 28)
        self.assertEqual(T.drug_tdm("absent", _quote_sources), {})

    def test_range_without_alert_has_no_alert_node(self):
        self._with({"ranges": {"x": {"low": 1, "high": 2, "unit": "ng/mL",
                                     "sources": self.SRC}}})
        self.assertNotIn("alert_level", T.drug_tdm("x", _quote_sources))

    def test_bad_unit_raises(self):
        self._with({"ranges": {"x": {"low": 1, "high": 2, "unit": "mg/dL",
                                     "sources": self.SRC}}})
        with self.assertRaises(ValueError):
            T.drug_tdm("x", _quote_sources)

    def test_enzymes_confirm_and_add(self):
        q = [{"corpus": "agnp_tdm", "page": 7, "quote": "Agomelatine CYP1A2, CYP2C19",
              "provenance": "verified", "extraction": "code"}]
        self._with({"enzymes": {"agomelatine": [
            {"enzyme": "cyp1a2", "role": "substrate", "sources": q},
            {"enzyme": "cyp2c19", "role": "substrate", "sources": q}]}})
        merged = {"agomelatine": [{"enzyme": "cyp1a2", "role": "substrate",
                                   "sources": [{"corpus": "stahl", "page": 1}]}]}
        vocab = {"cyp1a2", "cyp2c19"}
        self.assertEqual(T.merge_enzymes(merged, vocab), (1, 1))
        rows = {r["enzyme"]: r for r in merged["agomelatine"]}
        self.assertEqual([s["corpus"] for s in rows["cyp1a2"]["sources"]],
                         ["stahl", "agnp_tdm"])
        self.assertEqual(rows["cyp2c19"]["sources"], q)   # a row of its own
        self.assertNotIn("strength", rows["cyp2c19"])
        self.assertEqual(T.merge_enzymes(merged, vocab), (0, 0))   # idempotent

    def test_enzymes_outside_vocabulary(self):
        q = [{"corpus": "agnp_tdm", "page": 9, "quote": "x", "provenance": "verified"}]
        self._with({"enzymes": {"lamotrigine": [
            {"enzyme": "ugt3b7", "role": "substrate", "sources": q}]}})
        merged: dict = {}
        self.assertEqual(T.merge_enzymes(merged, {"ugt1a4"}), (0, 0))   # NOT_ADDED
        self._with({"enzymes": {"x": [
            {"enzyme": "cyp9z9", "role": "substrate", "sources": q}]}})
        with self.assertRaises(ValueError):
            T.merge_enzymes(merged, {"ugt1a4"})

if __name__ == "__main__":
    unittest.main()
