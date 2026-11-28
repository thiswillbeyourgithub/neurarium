#!/usr/bin/env python
"""Unit tests for the Drugs@FDA pass (corpus #18: fetcher selection + applier gates).

Stdlib ``unittest`` only; hand-built application records and a fake page store in a
temp dir, so it runs on a clone lacking the gitignored export::

    python -m unittest discover -t tools/tests -s tools/tests -p test_drugsfda.py

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_drug_history as H  # noqa: E402
import apply_drugsfda as A  # noqa: E402
import fetch_drugsfda as F  # noqa: E402
from data_generators import history  # noqa: E402
from judged_fixture import refs  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)


def app(num, ingredients, date, cls="Type 1 - New Molecular Entity", brand="BRAND"):
    sub = {"submission_type": "ORIG", "submission_status": "AP"}
    if date:
        sub["submission_status_date"] = date
    if cls:
        sub["submission_class_code_description"] = cls
    return {"application_number": num, "submissions": [sub] if date else [],
            "products": [{"brand_name": brand, "dosage_form": "TABLET",
                          "active_ingredients": [{"name": n} for n in ingredients]}]}


SERTRALINE = {"id": "sertraline", "name": "Sertraline"}


class SelectTest(unittest.TestCase):
    def test_earliest_nme_nda_wins_salt_dropped(self):
        rec = F.first_approval(SERTRALINE, [
            app("NDA020990", ["SERTRALINE HYDROCHLORIDE"], "19991207", cls="Type 3 - New Dosage Form"),
            app("NDA019839", ["SERTRALINE HYDROCHLORIDE"], "19911230", brand="ZOLOFT"),
            app("ANDA076000", ["SERTRALINE HYDROCHLORIDE"], "19800101"),
        ])
        self.assertEqual((rec["status"], rec["application"], rec["year"]),
                         ("found", "NDA019839", 1991))
        self.assertEqual(rec["quote"], "NDA019839 | ZOLOFT | SERTRALINE HYDROCHLORIDE | "
                                       "TABLET | ORIG approved 1991-12-30")

    def test_combination_product_is_another_drug(self):
        rec = F.first_approval(SERTRALINE, [
            app("NDA000001", ["SERTRALINE HYDROCHLORIDE", "OTHER"], "19700101")])
        self.assertEqual(rec["status"], "none")

    def test_undated_nda_means_no_year_rather_than_a_late_one(self):
        """A pre-1982 NDA without a dated ORIG makes the earliest dated one a lie."""
        rec = F.first_approval({"id": "haloperidol", "name": "Haloperidol"}, [
            app("NDA015921", ["HALOPERIDOL"], None),
            app("NDA020074", ["HALOPERIDOL DECANOATE"], "19940101")])
        self.assertEqual(rec["status"], "undated")

    def test_reformulation_class_means_the_original_is_missing(self):
        """Regression: OxyContin's 1995 NDA is absent from the export, so oxycodone's
        earliest listed NDA is a 1998 "new dosage form", which must not publish."""
        rec = F.first_approval({"id": "oxycodone", "name": "Oxycodone"}, [
            app("NDA020932", ["OXYCODONE HYDROCHLORIDE"], "19981026",
                cls="Type 3 - New Dosage Form")])
        self.assertEqual(rec["status"], "superseded")

    def test_us_name_and_stereo(self):
        rec = F.first_approval({"id": "pethidine", "name": "Pethidine"}, [
            app("NDA005010", ["MEPERIDINE HYDROCHLORIDE"], "19421110", cls=None)])
        self.assertEqual(rec["year"], 1942)
        # A (-)-tagged ingredient never joins a racemate we model.
        self.assertIsNone(F.ingredient_key("(-)-SERTRALINE", "sertraline"))

    def test_meglumine_salt_is_stripped(self):
        """Regression: Emend for injection lists FOSAPREPITANT DIMEGLUMINE, which never
        joined fosaprepitant while DIMEGLUMINE was missing from the salt words."""
        self.assertEqual(F.ingredient_key("FOSAPREPITANT DIMEGLUMINE", "fosaprepitant"),
                         "fosaprepitant")
        self.assertEqual(F.ingredient_key("X MEGLUMINE", "x"), "x")

    def test_roster_combination_is_skipped(self):
        self.assertEqual(F.first_approval({"id": "x", "name": "Naltrexone + Bupropion"}, [])
                         ["status"], "combo")


class ApplyTest(unittest.TestCase):
    QUOTE = "NDA019839 | ZOLOFT | SERTRALINE HYDROCHLORIDE | TABLET | ORIG approved 1991-12-30"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        (Path(self.tmp.name) / "NDA019839.md").write_text(f"# h\n\n{self.QUOTE}\n", "utf-8")
        self.pages = PageGate({"drugsfda": Path(self.tmp.name)})
        self.cache = {"sertraline": {"status": "found", "application": "NDA019839",
                                     "date": "1991-12-30", "year": 1991, "quote": self.QUOTE}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_fills_an_empty_approval_as_national(self):
        drugs = [{"id": "sertraline"}]
        filled, _, _ = A.apply(self.cache, drugs, self.pages)
        self.assertEqual(filled, ["sertraline"])
        self.assertEqual(drugs[0]["first_approval"],
                         {"year": 1991, "country": "us", "agency": "fda", "national": True})
        self.assertEqual(drugs[0]["first_approval_sources"][0]["extraction"], "code")

    def test_earlier_fda_date_replaces_a_later_wikipedia_approval(self):
        """Regression (loxapine 1978 fr vs FDA 1975): an earlier dated approval proves
        ours was not the first, so it wins, worded as a national approval."""
        drugs = [{"id": "sertraline", "first_approval": {"year": 1995, "country": "fr"},
                  "first_approval_sources": [{"corpus": "wikipedia_pharm"}]}]
        filled, _, replaced = A.apply(self.cache, drugs, self.pages)
        self.assertEqual(filled, ["sertraline"])
        self.assertEqual(drugs[0]["first_approval"],
                         {"year": 1991, "country": "us", "agency": "fda", "national": True})
        self.assertIn("FDA 1991-12-30", replaced[0])

    def test_same_or_later_fda_date_leaves_a_wikipedia_approval(self):
        for year in (1991, 1980):
            wiki = {"year": year, "country": "fr"}
            drugs = [{"id": "sertraline", "first_approval": dict(wiki),
                      "first_approval_sources": [{"corpus": "wikipedia_pharm"}]}]
            filled, _, replaced = A.apply(self.cache, drugs, self.pages)
            self.assertEqual((filled, replaced, drugs[0]["first_approval"]), ([], [], wiki))

    def test_quote_must_be_on_page(self):
        self.cache["sertraline"]["quote"] = self.QUOTE.replace("1991-12-30", "1991-12-31")
        drugs = [{"id": "sertraline"}]
        self.assertEqual(A.apply(self.cache, drugs, self.pages)[0], [])

    def test_own_stale_approval_is_cleared(self):
        drugs = [{"id": "sertraline", "first_approval": {"year": 1991},
                  "first_approval_sources": [{"corpus": "drugsfda"}]}]
        self.cache["sertraline"] = {"status": "superseded"}
        self.assertEqual(A.apply(self.cache, drugs, self.pages)[1], ["sertraline"])
        self.assertNotIn("first_approval", drugs[0])


class CoexistTest(unittest.TestCase):
    def test_history_applier_keeps_an_fda_approval(self):
        """A judged drug with no approval of its own keeps the Drugs@FDA fallback."""
        fa = {"year": 1991, "country": "us", "agency": "fda", "national": True}
        drugs = [{"id": "x", "first_approval": dict(fa),
                  "first_approval_sources": [{"corpus": "drugsfda"}]}]
        offered = {"x": {"candidates": [{"corpus": "wikipedia_pharm", "page": "x",
                                         "line": "X was approved in 1990."}]}}
        H.apply({"x": {"approval": None, "withdrawals": []}}, offered, drugs, PageGate({}))
        self.assertEqual(drugs[0]["first_approval"], fa)

    def _history(self, wiki_year):
        fa = {"year": 1991, "country": "us", "agency": "fda", "national": True}
        drugs = [{"id": "x", "first_approval": dict(fa),
                  "first_approval_sources": [{"corpus": "drugsfda"}]}]
        line = f"X was approved in {wiki_year}."
        gate = PageGate({})
        gate.on_page = lambda corpus, page, quote: True
        offered = {"x": {"candidates": [{"corpus": "wikipedia_pharm", "page": "x",
                                         "line": line}]}}
        H.apply({"x": {"approval": refs(offered["x"]["candidates"], 0)[0] | {"year": wiki_year},
                       "withdrawals": []}},
                offered, drugs, gate)
        return drugs[0]["first_approval"]

    def test_history_applier_earliest_approval_wins(self):
        """The history applier honours the same rule: a later Wikipedia year never
        displaces an earlier Drugs@FDA one; an earlier or same-year one does."""
        self.assertEqual(self._history(1995)["year"], 1991)
        self.assertEqual(self._history(1985), {"year": 1985})
        self.assertEqual(self._history(1991), {"year": 1991})  # a tie: worldwide wording

    def test_national_needs_a_country(self):
        with self.assertRaises(ValueError):
            history.drug_history({"id": "x", "first_approval": {"year": 1991,
                                                                "national": True}})
        out = history.drug_history({"id": "x", "first_approval": {
            "year": 1991, "country": "us", "national": True}})
        self.assertTrue(out["first_approval"]["national"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
