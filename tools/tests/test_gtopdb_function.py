"""GtoPdb function corpus (#23): flattening, the species offer rule, the effect candidates.

``fetch_gtopdb_function.py`` turns four GtoPdb target endpoints into one quote-gate page;
``fetch_receptor_effects.gtopdb_candidates`` offers its lines; ``prose_gate`` carries the
recorded species onto the source. Offline: a payload is built by hand.

Built with the help of Claude Code.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "fetch"))
sys.path.insert(0, str(TOOLS))
import fetch_gtopdb_function as gf  # noqa: E402
import fetch_receptor_effects as fre  # noqa: E402
from judged_fixture import refs  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)

PAYLOAD = {
    "owner": "beta3", "gene": "ADRB3", "target_id": 30, "target_name": "β3-adrenoceptor",
    "fetched": "2026-10-15",
    "function": [
        {"property": "Bladder relaxation.", "tissue": "Urinary bladder.", "species": "Human"},
        {"property": "Bladder relaxation.", "tissue": "Urinary bladder.", "species": "Human"},
        {"property": "Lipolysis.", "tissue": "<i>In vivo</i>.", "species": "Rat"},
    ],
    "pathophysiology": [{"disease": {"name": "Obesity"}, "role": "", "use": "Weight loss",
                         "mutations": [{"description": "Trp64Arg"}]}],
    "altered": [{"property": "Knockout mice are obese.", "species": "Mouse"}],
    "comments": {"functionComments": "First point <Reference id=1/> .<br>Second point"},
}


class FlattenTest(unittest.TestCase):
    def setUp(self):
        self.lines = gf.flatten(PAYLOAD)
        self.by_text = {x["line"].split(" | ", 1)[1]: x for x in self.lines}

    def test_one_line_per_statement_with_section_and_species(self):
        subj = "β3-adrenoceptor (ADRB3), GtoPdb target 30"
        self.assertTrue(all(x["line"].startswith(subj + " | ") for x in self.lines))
        self.assertIn("physiological function (Human): Bladder relaxation. | tissue: "
                      "Urinary bladder.", self.by_text)
        self.assertIn("physiological function (Rat): Lipolysis. | tissue: In vivo.",
                      self.by_text)
        self.assertIn("altered gene expression (Mouse): Knockout mice are obese.",
                      self.by_text)

    def test_duplicates_dropped(self):
        self.assertEqual(sum("Bladder relaxation" in x["line"] for x in self.lines), 1)

    def test_pathophysiology_fields_and_mutations_species_less(self):
        use = self.by_text["pathophysiology: Obesity | use: Weight loss"]
        self.assertIsNone(use["species"])
        self.assertIn("pathophysiology: Obesity | mutation: Trp64Arg", self.by_text)

    def test_comments_split_on_br_and_reference_gap_closed(self):
        self.assertIn("function comment: First point.", self.by_text)
        self.assertIn("function comment: Second point", self.by_text)

    def test_page_has_header_then_lines(self):
        page = gf.page_text(PAYLOAD, self.lines).splitlines()
        self.assertEqual(page[0], "source: " + gf.PAGE_URL.format(30))
        self.assertEqual(page[1], "fetched: 2026-10-15")
        self.assertEqual(page[2:], [x["line"] for x in self.lines])


class OfferTest(unittest.TestCase):
    def test_species_rule(self):
        self.assertTrue(gf.offerable({"species": "Human"}))
        self.assertFalse(gf.offerable({"species": "Monkey"}))  # non-human: never offered
        self.assertTrue(gf.offerable({"species": None}))
        self.assertFalse(gf.offerable({"species": "Rat"}))
        self.assertFalse(gf.offerable({"species": "Mouse"}))
        self.assertFalse(gf.offerable({"species": "Martian"}))  # unnamed label stays out

    def test_no_data_answer_folds_to_empty(self):
        msg = {"GtoPdb Web Services": "No function data for target ID:4 "}
        self.assertEqual(gf.rows(msg), [])
        self.assertEqual(gf.rows(msg, comments=True), {})
        self.assertEqual(gf.rows([{"a": 1}, "junk"]), [{"a": 1}])

    def test_group_target_sharing_a_receptor_gene_skipped(self):
        owners = gf.owners()
        self.assertIn("m1", owners)
        self.assertNotIn("muscarinic", owners)  # CHRM1 belongs to m1
        self.assertIn("sert", owners)


class GeneRemapTest(unittest.TestCase):
    """A raw payload cached for another gene is never reused under the owner."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        for name, path in (("RAW", d / "raw"), ("PAGES", d / "pages")):
            path.mkdir()
            p = mock.patch.object(gf, name, path)
            p.start()
            self.addCleanup(p.stop)
        (d / "raw" / "x.json").write_text(json.dumps(
            {"owner": "x", "kind": "receptor", "gene": "OLD", "target_id": 1, "target_name": "X",
             "fetched": "2026-01-01"}), encoding="utf-8")

    def test_same_gene_reuses_the_cache_offline(self):
        self.assertEqual(gf.fetch_one("x", "OLD", "receptor", False, True)["gene"], "OLD")

    def test_remapped_gene_is_refetched_not_reused(self):
        with mock.patch("sys.stderr"):
            self.assertIsNone(gf.fetch_one("x", "NEW", "receptor", False, True))
            with mock.patch.object(gf, "target_id", return_value=None) as tid:
                self.assertIsNone(gf.fetch_one("x", "NEW", "receptor", False, False))
        tid.assert_called_once_with("x", "NEW")


class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        payload = {**PAYLOAD, "lines": gf.flatten(PAYLOAD)}
        (self.tmp / "beta3.json").write_text(json.dumps(payload), encoding="utf-8")
        (self.tmp / "30.md").write_text(gf.page_text(payload, payload["lines"]), "utf-8")
        self.patch = mock.patch.object(gf, "RAW", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_only_offerable_keyword_lines_offered_with_species(self):
        cands = fre.gtopdb_candidates("beta3", fre.effect_hits, "effects")
        # The rodent "obese" knockout line hits a cue but is never offered; the clinical
        # "Obesity" pathophysiology lines (no species stated) are.
        self.assertFalse(any("Mouse" in c["line"] or "Rat" in c["line"] for c in cands))
        self.assertTrue(all(c["line"].count("Obesity") for c in cands[1:]))
        c = cands[0]
        self.assertEqual((c["corpus"], c["page"], c["species"]), ("gtopdb_function", 30, "Human"))
        self.assertEqual(c["effects"], ["bladder_relaxation"])
        self.assertNotIn("species", cands[1])
        self.assertEqual(fre.gtopdb_candidates("nope", fre.effect_hits, "effects"), [])

    def test_gate_carries_species_onto_the_source(self):
        cands = fre.gtopdb_candidates("beta3", fre.effect_hits, "effects")
        misses = []
        srcs = PageGate({"gtopdb_function": self.tmp}).sources(cands, refs(cands, 0), "beta3", misses)
        self.assertEqual(misses, [])
        self.assertEqual(srcs[0]["species"], "Human")
        self.assertEqual(srcs[0]["quote"], cands[0]["line"])


if __name__ == "__main__":
    unittest.main()
