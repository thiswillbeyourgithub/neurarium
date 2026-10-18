#!/usr/bin/env python
"""Unit tests for a drug's origin nodes: current holders (code-read applier), originator
+ its country (four-step pass gates), and the emitter's shape checks.

Stdlib ``unittest`` only; fake page stores in a temp dir, so it runs on a clone that
lacks the gitignored corpus trees::

    python -m unittest discover -t tools/tests -s tools/tests -p test_drug_origin.py

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_drug_holders as AH  # noqa: E402
import apply_originator as AO  # noqa: E402
from judged_fixture import fill_tree  # noqa: E402
from data_generators import origin  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)

FDA_PAGE = ("# Drugs@FDA application NDA020639 (CHEPLAPHARM)\n"
            "application: NDA020639\n\n"
            "NDA020639 | SEROQUEL | QUETIAPINE FUMARATE | TABLET | ORIG approved 1997-09-26\n")
BDPM_PAGE = ("# XEROQUEL 25 mg, comprimé pelliculé\ncis: {cis}\nform: comprimé\n"
             "holder: {holder}\nsource: https://example.org\n\nLe pic est atteint en 1,5 h.\n"
             "holder: NOT A HEADER\n")


class HolderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.dirs = {"drugsfda": base / "fda", "bdpm": base / "bdpm"}
        for d in self.dirs.values():
            d.mkdir()
        (self.dirs["drugsfda"] / "NDA020639.md").write_text(FDA_PAGE, "utf-8")
        (self.dirs["drugsfda"] / "NDA000001.md").write_text(
            "# Drugs@FDA application NDA000001 (sponsor not stated)\n", "utf-8")
        for cis, holder in (("1", "UPJOHN (PAYS-BAS)"), ("2", "ETHYPHARM"), ("3", "ETHYPHARM")):
            (self.dirs["bdpm"] / f"{cis}.md").write_text(
                BDPM_PAGE.format(cis=cis, holder=holder), "utf-8")
        self.pages = PageGate(self.dirs)

    def run_apply(self, fda_rec=None, bdpm_rec=None):
        drugs = [{"id": "x", "holders": [{"market": "us", "names": ["STALE"]}]}]
        AH.apply({"x": fda_rec} if fda_rec else {}, {"x": bdpm_rec} if bdpm_rec else {},
                 drugs, self.pages, self.dirs)
        return drugs[0].get("holders")

    def test_us_sponsor_from_the_title_line(self):
        rows = self.run_apply({"status": "found", "application": "NDA020639"})
        self.assertEqual(rows, [{"market": "us", "names": ["CHEPLAPHARM"], "sources": [{
            "corpus": "drugsfda", "page": "NDA020639",
            "quote": "Drugs@FDA application NDA020639 (CHEPLAPHARM)",
            "provenance": "verified", "extraction": "code"}]}])

    def test_us_needs_a_found_record_and_a_stated_sponsor(self):
        """A superseded record, a missing page and "sponsor not stated" publish nothing,
        and a rebuild drops a stale holder."""
        self.assertIsNone(self.run_apply({"status": "superseded", "application": "NDA020639"}))
        self.assertIsNone(self.run_apply({"status": "found", "application": "NDA000001"}))
        self.assertIsNone(self.run_apply({"status": "found", "application": "NDA999999"}))

    def test_fr_holders_fold_into_one_node_per_market(self):
        rows = self.run_apply(bdpm_rec={"brands": [{"cis": "1"}, {"cis": "2"}, {"cis": "3"}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["names"], ["UPJOHN (PAYS-BAS)", "ETHYPHARM"])
        self.assertEqual([s["quote"] for s in rows[0]["sources"]],
                         ["holder: UPJOHN (PAYS-BAS)", "holder: ETHYPHARM"])

    def test_fr_reads_only_the_header_block(self):
        """A `holder:` line below the header's blank line is body text, never read."""
        (self.dirs["bdpm"] / "4.md").write_text("# X\ncis: 4\n\nholder: BODY\n", "utf-8")
        self.assertIsNone(self.run_apply(bdpm_rec={"brands": [{"cis": "4"}]}))

    def test_gate_drops_a_name_its_quote_does_not_carry(self):
        found = [("UPJOHN", "holder: PFIZER", "1"), ("ETHYPHARM", "holder: ETHYPHARM", "2")]
        row = AH.gate("fr", found, self.pages)
        self.assertEqual(row["names"], ["ETHYPHARM"])
        self.assertIsNone(AH.gate("fr", [("X", "holder: X", "1")], self.pages))  # not on page


DRUG_LINE = "Citalopram was first synthesized in 1972 at the company Lundbeck."
CO_LINES = ["Headquarters | Valby, Copenhagen, Denmark",
            "Lundbeck was acquired by Novartis in 2030.",
            "Lundbeck was founded in Copenhagen.",
            "Novartis merged with Lundbeck in 2031."]


class OriginatorTest(unittest.TestCase):
    """The applier's gates: index, verbatim name, company names, attested country."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        (d / "citalopram.md").write_text("# Citalopram\n\n" + DRUG_LINE + "\n", "utf-8")
        (d / "lundbeck.md").write_text("# Lundbeck\n\n" + "\n".join(CO_LINES) + "\n", "utf-8")
        self.pages = PageGate({"wikipedia_pharm": d})
        cand = lambda page, line: {"corpus": "wikipedia_pharm", "page": page, "line": line}
        self.wl = {"drugs": {"x": {"candidates": [cand("citalopram", DRUG_LINE)]}},
                   "companies": {"lundbeck": {"candidates": [
                       cand("lundbeck", ln) for ln in CO_LINES]}}}

    def run_apply(self, drug_pick, company_pick=None):
        drugs = [{"id": "x", "originator": {"name": "STALE"}}]
        company_pick = dict(company_pick or {})
        now = company_pick.get("now")
        if now and isinstance(now.get("index"), list):  # a chain: one ref per sentence
            company_pick["now"] = {"picks": [{"index": i} for i in now["index"]],
                                   "name": now["name"]}
        judged = {"drugs": {"x": fill_tree(drug_pick, self.wl["drugs"]["x"]["candidates"])},
                  "companies": {"lundbeck": fill_tree(
                      company_pick, self.wl["companies"]["lundbeck"]["candidates"])}}
        AO.apply(self.wl, judged, drugs, self.pages, {"lundbeck": ["Lundbeck"]})
        return drugs[0]

    def test_full_pick(self):
        d = self.run_apply({"index": 0, "name": "Lundbeck", "company": "lundbeck"},
                           {"country": {"index": 0, "country": "dk"},
                            "now": {"index": 1, "name": "Novartis"}})
        self.assertEqual(d["originator"], {"name": "Lundbeck", "now": "Novartis"})
        self.assertEqual(d["originator_country"], "dk")
        self.assertEqual(d["originator_country_sources"][0]["quote"], CO_LINES[0])
        self.assertEqual(d["originator_now_sources"][0]["quote"], CO_LINES[1])

    def test_gates_drop_what_the_quotes_do_not_say(self):
        """A name absent from its quote, a bad index, an unattested country, a `now`
        from a sentence with no successor verb all publish nothing (stale fields go)."""
        self.assertNotIn("originator", self.run_apply({"index": 0, "name": "Pfizer"}))
        self.assertNotIn("originator", self.run_apply({"index": 3, "name": "Lundbeck"}))
        d = self.run_apply({"index": 0, "name": "Lundbeck", "company": "lundbeck"},
                           {"country": {"index": 0, "country": "se"},
                            "now": {"index": 2, "name": "Copenhagen"}})
        self.assertEqual(d["originator"], {"name": "Lundbeck"})
        self.assertNotIn("originator_country", d)

    def test_now_chain_cites_every_sentence(self):
        """A two-sentence chain cites both, and every link must be a successor one."""
        d = self.run_apply({"index": 0, "name": "Lundbeck", "company": "lundbeck"},
                           {"now": {"index": [1, 3], "name": "Novartis"}})
        self.assertEqual([s["quote"] for s in d["originator_now_sources"]],
                         [CO_LINES[1], CO_LINES[3]])
        d = self.run_apply({"index": 0, "name": "Lundbeck", "company": "lundbeck"},
                           {"now": {"index": [1, 2], "name": "Novartis"}})
        self.assertNotIn("now", d["originator"])

    def test_a_bool_is_never_an_index(self):
        """``True == 1`` in Python: a judge writing ``"index": true`` must not land on
        candidate 1, even with that candidate's own qid."""
        from pipeline.judged import ref
        cands = self.wl["companies"]["lundbeck"]["candidates"]
        good = self.run_apply({"index": 0, "name": "Lundbeck", "company": "lundbeck"},
                              {"now": {"index": 1, "name": "Novartis"}})
        self.assertEqual(good["originator"]["now"], "Novartis")
        drugs = [{"id": "x"}]
        judged = {"drugs": {"x": fill_tree({"index": 0, "name": "Lundbeck",
                                            "company": "lundbeck"},
                                           self.wl["drugs"]["x"]["candidates"])},
                  "companies": {"lundbeck": {"now": {**ref(cands, 1), "index": True,
                                                     "name": "Novartis"}}}}
        AO.apply(self.wl, judged, drugs, self.pages, {"lundbeck": ["Lundbeck"]})
        self.assertEqual(drugs[0]["originator"], {"name": "Lundbeck"})

    def test_company_must_list_the_picked_name(self):
        """A drug naming another lab never borrows the company's country."""
        d = self.run_apply({"index": 0, "name": "company", "company": "lundbeck"},
                           {"country": {"index": 0, "country": "dk"}})
        self.assertEqual(d["originator"], {"name": "company"})
        self.assertNotIn("originator_country", d)


class EmitTest(unittest.TestCase):
    def test_holders_validate_market_and_order(self):
        out = origin.drug_origin({"id": "x", "holders": [
            {"market": "fr", "names": ["B"]}, {"market": "us", "names": ["A"]}]})
        self.assertEqual([h["market"] for h in out["holders"]], ["us", "fr"])
        with self.assertRaises(KeyError):
            origin.drug_origin({"id": "x", "holders": [{"market": "de", "names": ["A"]}]})
        with self.assertRaises(ValueError):
            origin.drug_origin({"id": "x", "holders": [{"market": "us", "names": []}]})

    def test_originator_now_needs_its_own_source(self):
        with self.assertRaises(ValueError):
            origin.drug_origin({"id": "x", "originator": {"name": "A", "now": "B"}})
        with self.assertRaises(ValueError):  # a country with no originator
            origin.drug_origin({"id": "x", "originator_country": "dk"})
        with self.assertRaises(KeyError):  # a market scope is not a country
            origin.drug_origin({"id": "x", "originator": {"name": "A"},
                                "originator_country": "worldwide"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
