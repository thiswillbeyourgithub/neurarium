#!/usr/bin/env python
"""Unit tests for the pre-prescription workup pass (corpus #24 ``bdpm_rcp``, kind
``drug_workup``): the RCP page builder, the copy dating rule (justelesRCP manifest vs
file mtime, empty copies skipped), the worklist line reader, the vocabulary patterns,
the applier's gates and the generator's validation.

Stdlib ``unittest`` only, hand-built inputs in a temporary directory, so it runs on a
clone lacking the gitignored ``data_sources/``::

    python -m unittest discover -t tools/tests -s tools/tests -p test_workup.py

Built with the help of Claude Code.
"""

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib.corpora import bdpm  # noqa: E402
import fetch_bdpm_rcp as R  # noqa: E402
import fetch_workup as FW  # noqa: E402
import apply_workup as A  # noqa: E402
from judged_fixture import fill  # noqa: E402
from data_generators import workup as W  # noqa: E402
from data_generators.provenance import _quote_sources  # noqa: E402

RCP = ('<html><a name="RcpPosoAdmin"></a><p class="AmmAnnexeTitre2">4.2. Posologie</p>'
       '<p class="AmmCorpsTexte">Une lithiémie est contrôlée chaque semaine.</p>'
       '<a name="RcpMisesEnGarde"></a><p class="AmmAnnexeTitre2">4.4. Mises en garde</p>'
       '<p class="AmmAnnexeTitre3">Examens à pratiquer avant le traitement :</p>'
       '<p class="AmmListePuces1">· Ionogramme sanguin, numération et formule sanguine.</p>'
       '<a name="RcpInteractions"></a><p class="AmmAnnexeTitre2">4.5. Interactions</p>'
       '<p class="AmmCorpsTexte">Hors sujet.</p></html>')


class PageBuilderTest(unittest.TestCase):
    def test_sections_subheadings_and_items(self):
        secs = R.rcp_sections(RCP)
        self.assertEqual(sorted(secs), ["4.2", "4.4"])  # no 4.3 in this page, 4.5 not read
        self.assertIn("### Examens à pratiquer avant le traitement :", secs["4.4"])
        self.assertIn("- Ionogramme sanguin, numération et formule sanguine.", secs["4.4"])
        self.assertFalse(any("Hors sujet" in ln for ln in secs["4.4"]))

    def test_page_text_header_cites_the_official_page(self):
        copy = {"fetched": "2026-10-01", "date_source": "file mtime",
                "copied_from": "x", "sections": R.rcp_sections(RCP)}
        text = R.page_text({"denomination": "TERALITHE"}, "62124478", copy)
        self.assertIn("source: https://base-donnees-publique.medicaments.gouv.fr/"
                      "medicament/62124478/extrait", text)
        self.assertIn("fetched: 2026-10-01", text)
        self.assertIn("## 4.4. Mises en garde spéciales et précautions d'emploi", text)

    def test_page_lines_round_trip(self):
        copy = {"fetched": "d", "date_source": "s", "copied_from": "c",
                "sections": R.rcp_sections(RCP)}
        lines = FW.page_lines(R.page_text({}, "1", copy))
        item = [ln for ln in lines if ln["line"].startswith("Ionogramme")][0]
        self.assertEqual(item["section"], "4.4")
        self.assertEqual(item["under"], "Examens à pratiquer avant le traitement :")


class CopyDatingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.raw, self.repo = base / "raw", base / "justelesRCP"
        self.raw.mkdir()
        (self.repo / "data" / "rcp").mkdir(parents=True)
        self._raw_dir, bdpm.RAW_DIR = bdpm.RAW_DIR, self.raw

    def tearDown(self):
        bdpm.RAW_DIR = self._raw_dir
        self.tmp.cleanup()

    def _gz(self, cis, html, mtime):
        path = self.repo / "data" / "rcp" / f"{cis}.html.gz"
        path.write_bytes(gzip.compress(html.encode()))
        os.utime(path, (mtime, mtime))

    def test_manifest_date_wins_when_ok(self):
        self._gz("1", RCP, 1_700_000_000)
        out = R.copies("1", self.repo, {"1": {"status": "ok",
                                               "last_fetch": "2026-10-05T10:00:00"}})
        self.assertEqual(out[0]["fetched"], "2026-10-05")
        self.assertIn("manifest", out[0]["date_source"])

    def test_mtime_fallback_without_manifest(self):
        self._gz("1", RCP, 1_700_000_000)  # 2023-11-14
        out = R.copies("1", self.repo, {})
        self.assertEqual(out[0]["fetched"], "2023-11-14")
        self.assertEqual(out[0]["date_source"], "file mtime")

    def test_empty_copies_are_skipped(self):
        (self.repo / "data" / "rcp" / "2.html.gz").write_bytes(b"")
        self._gz("3", RCP, 1_700_000_000)
        self.assertEqual(R.copies("2", self.repo, {}), [])
        self.assertEqual(R.copies("3", self.repo, {"3": {"status": "empty"}}), [])

    def test_freshest_copy_with_a_44_wins(self):
        local = self.raw / "1.html"
        local.write_text(RCP, encoding="utf-8")
        os.utime(local, (1_700_000_000, 1_700_000_000))
        self._gz("1", RCP, 1_700_000_000)
        best = R.freshest(R.copies("1", self.repo, {"1": {
            "status": "ok", "last_fetch": "2026-10-05"}}))
        self.assertTrue(best["copied_from"].startswith("justelesRCP"))
        self.assertIsNone(R.freshest([{"html": "<p>no sections</p>", "fetched": "9"}]))


SMPC = ('<div id="textDocument" data-ema-fetched="2026-09-30" data-ema-pdf="https://ema/x.pdf">'
        '<h2 class="AmmAnnexeTitre1">4. DONNÉES CLINIQUES</h2>'
        '<h3 class="AmmAnnexeTitre2">4.3 Contre-indications</h3><p>Hypersensibilité.</p>'
        '<h3 class="AmmAnnexeTitre2">4.4 Mises en garde</h3><p>Surveiller la natrémie.</p>'
        '<h3 class="AmmAnnexeTitre2">4.5 Interactions</h3><p>Hors sujet.</p></div>')


class EmaCopyTest(unittest.TestCase):
    """A centrally authorised product's RCP is EMA's SmPC under justelesRCP data/eu/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "data" / "eu").mkdir(parents=True)
        (self.repo / "data" / "eu" / "9.html.gz").write_bytes(gzip.compress(SMPC.encode()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_smpc_sections_read_by_heading_text(self):
        secs = R.rcp_sections(SMPC)
        self.assertEqual(secs["4.4"], ["Surveiller la natrémie."])
        self.assertEqual(secs["4.3"], ["Hypersensibilité."])

    def test_dated_by_manifest_else_page_and_cited_at_the_pdf(self):
        out = R.ema_copies("9", self.repo, {})
        self.assertEqual((out[0]["fetched"], out[0]["date_source"]), ("2026-09-30", "data-ema-fetched"))
        out = R.ema_copies("9", self.repo, {"9": {"status": "ok", "last_fetch": "2026-10-02T01:00",
                                                  "ema_pdf": "https://ema/y.pdf"}})
        self.assertEqual(out[0]["fetched"], "2026-10-02")
        self.assertEqual(out[0]["source"], "https://ema/y.pdf")
        out[0]["sections"] = R.rcp_sections(out[0]["html"])
        text = R.page_text({}, "9", out[0])
        self.assertIn("source: https://ema/y.pdf", text)
        self.assertIn("licence: European Medicines Agency", text)
        self.assertEqual(R.ema_copies("8", self.repo, {}), [])


class VocabularyTest(unittest.TestCase):
    def test_tests_named(self):
        self.assertEqual(W.tests_named("Ionogramme sanguin, numération et formule sanguine."),
                         ["blood_count", "electrolytes"])
        self.assertIn("renal_function",
                      W.tests_named("les fonctions hépatique et rénale doivent être contrôlées"))
        self.assertIn("renal_function", W.tests_named("contrôles réguliers de la créatinémie"))
        # "insuffisance hépatique" names an organ, not a liver test.
        self.assertNotIn("liver_function", W.tests_named("chez l'insuffisant hépatique"))

    def test_timing_reads_the_heading_too(self):
        self.assertTrue(W.attests(W.TIMINGS, "before", "Ionogramme.", "Examens avant le traitement"))
        self.assertTrue(W.attests(W.TIMINGS, "before", "ne doit pas être instauré sans test"))
        self.assertFalse(W.attests(W.TIMINGS, "before", "Ionogramme.", ""))
        self.assertFalse(W.attests(W.TIMINGS, "nightly", "avant"))

    def test_excipient_notice_is_not_offered(self):
        ln = {"line": "Ce médicament contient du lactose. Malabsorption du glucose.",
              "section": "4.4", "under": ""}
        self.assertFalse(FW.offered(ln))
        self.assertTrue(FW.offered({"line": "Un ECG doit être réalisé avant le traitement.",
                                    "section": "4.4", "under": ""}))


class ApplierGateTest(unittest.TestCase):
    OFFERED = {"lithium": {"page": "62124478", "candidates": [
        {"index": 0, "section": "4.4", "under": "Examens à pratiquer avant le traitement :",
         "quote": "Ionogramme sanguin, numération et formule sanguine."},
        {"index": 1, "section": "4.2", "under": "",
         "quote": "Une lithiémie est contrôlée chaque semaine."}]}}

    def gate(self, judged, page=None):
        text = A.normalize_for_match(page if page is not None else
                                     "Ionogramme sanguin, numération et formule sanguine.\n"
                                     "Une lithiémie est contrôlée chaque semaine.")
        judged = {d: [fill(dict(p), self.OFFERED.get(d, {}).get("candidates", [])) for p in ps]
                  for d, ps in judged.items()}
        return A.gate(judged, self.OFFERED, {"lithium", "clozapine"}, lambda cis: text)

    def test_accepts_and_merges_one_node_per_test_timing(self):
        out, rej = self.gate({"lithium": [
            {"index": 0, "test": "blood_count", "timing": "before"},
            {"index": 0, "test": "electrolytes", "timing": "before"},
            {"index": 1, "test": "drug_level", "timing": "during"}]})
        self.assertEqual(rej, [])
        self.assertEqual([(n["test"], n["timing"]) for n in out["lithium"]],
                         [("blood_count", "before"), ("electrolytes", "before"),
                          ("drug_level", "during")])
        self.assertEqual(out["lithium"][0]["sources"][0]["corpus"], "bdpm_rcp")

    def test_rejections(self):
        out, rej = self.gate({
            "nosuch": [{"index": 0, "test": "ecg", "timing": "before"}],
            "clozapine": [{"index": 0, "test": "blood_count", "timing": "before"}],
            "lithium": [{"index": 9, "test": "ecg", "timing": "before"},
                        {"index": "x", "test": "ecg", "timing": "before"},
                        {"index": 0, "test": "ecg", "timing": "before"},
                        {"index": 1, "test": "drug_level", "timing": "before"},
                        {"index": 0, "test": "blood_count", "timing": "soon"}]})
        self.assertEqual(out, {})
        self.assertEqual(len(rej), 7)
        joined = "\n".join(rej)
        for why in ("not a dataset drug", "offers no candidate", "out of range",
                    "does not name this test", "timing"):
            self.assertIn(why, joined)

    def test_quote_must_be_on_the_page(self):
        out, rej = self.gate({"lithium": [{"index": 0, "test": "blood_count",
                                           "timing": "before"}]}, page="autre texte")
        self.assertEqual(out, {})
        self.assertIn("not verbatim", rej[0])


    def test_conditional_pick_keeps_its_span_and_loses_to_a_plain_one(self):
        """A condition must be a span of its quote; an unconditional ask for the same
        (test, timing) wins, else the node carries each condition once."""
        out, rej = self.gate({"lithium": [
            {"index": 0, "test": "blood_count", "timing": "before",
             "condition": "numération et formule"},
            {"index": 1, "test": "drug_level", "timing": "during",
             "condition": "chaque semaine"},
            {"index": 1, "test": "drug_level", "timing": "during"},
            {"index": 0, "test": "electrolytes", "timing": "before",
             "condition": "chez le sujet âgé"}]})
        self.assertEqual(len(rej), 1)
        self.assertIn("condition is not a span", rej[0])
        nodes = {n["test"]: n for n in out["lithium"]}
        self.assertEqual(nodes["blood_count"]["conditions"], ["numération et formule"])
        self.assertNotIn("conditions", nodes["drug_level"])
        self.assertEqual(len(nodes["drug_level"]["sources"]), 1)

    def test_undecided_lists_offered_drugs_with_no_key(self):
        self.assertEqual(A.undecided({}, self.OFFERED), ["lithium"])
        self.assertEqual(A.undecided({"lithium": []}, self.OFFERED), [])


class JudgedCoverageTest(unittest.TestCase):
    """Every drug the committed worklist offers has an explicit decision in the
    committed judged file (``[]`` = judged, nothing), so an absent key can only mean
    a new candidate nobody has read yet, and this fails until someone does."""

    def test_every_offered_drug_is_judged(self):
        cache = ROOT / "tools" / "generated_cache"
        worklist = json.loads((cache / "workup_worklist.json").read_text(encoding="utf-8"))
        judged = json.loads((cache / "workup_judged.json").read_text(encoding="utf-8"))
        self.assertEqual(A.undecided(judged, worklist), [])


class GeneratorTest(unittest.TestCase):
    SRC = [{"corpus": "bdpm_rcp", "page": "1", "quote": "Un ECG avant.", "provenance": "verified"}]

    def test_sorted_before_then_during_in_vocab_order(self):
        data = {"drugs": {"x": [{"test": "weight", "timing": "during", "sources": self.SRC},
                                {"test": "weight", "timing": "before", "sources": self.SRC},
                                {"test": "ecg", "timing": "before", "sources": self.SRC}]}}
        rows = W.drug_workup("x", _quote_sources, data)["workup"]
        self.assertEqual([(r["test"], r["timing"]) for r in rows],
                         [("ecg", "before"), ("weight", "before"), ("weight", "during")])
        self.assertEqual(W.drug_workup("y", _quote_sources, data), {})

    def test_validation(self):
        for bad, err in (({"test": "mri", "timing": "before"}, KeyError),
                         ({"test": "ecg", "timing": "after"}, KeyError),
                         ({"test": "ecg", "timing": "before"}, ValueError)):
            rows = [dict(bad, sources=[] if err is ValueError else self.SRC)]
            with self.assertRaises(err):
                W.drug_workup("x", _quote_sources, {"drugs": {"x": rows}})
        dup = [{"test": "ecg", "timing": "before", "sources": self.SRC}] * 2
        with self.assertRaises(ValueError):
            W.drug_workup("x", _quote_sources, {"drugs": {"x": dup}})

    def test_condition_must_be_a_span_of_its_quotes(self):
        row = {"test": "ecg", "timing": "before", "sources": self.SRC}
        ok = W.drug_workup("x", _quote_sources, {"drugs": {"x": [dict(row, conditions=["ecg  AVANT"])]}})
        self.assertEqual(ok["workup"][0]["conditions"], ["ecg  AVANT"])
        with self.assertRaises(ValueError):
            W.drug_workup("x", _quote_sources, {"drugs": {"x": [dict(row, conditions=["chez l'âgé"])]}})

    def test_cache_is_valid(self):
        data = json.loads(W.CACHE.read_text(encoding="utf-8"))
        for did in data["drugs"]:
            W.drug_workup(did, _quote_sources, data)


if __name__ == "__main__":
    unittest.main()
