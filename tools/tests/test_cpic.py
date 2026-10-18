#!/usr/bin/env python
"""Unit tests for the CPIC guidance reader (corpus #15) and its hash pin.

This is the only corpus here whose text is a **clinical action** rather than a fact
about a molecule, so the tests are about the two ways that could go wrong: the reader
accepting an export it does not understand (a phenotype or a population it has no
business publishing), and the committed cache drifting from the committed export, which
would leave a dosing sentence nobody can trace to a guideline.

The committed-export test runs against the real `tools/data/cpic/`, so a refreshed
download nobody re-ran the fetcher over fails in the suite as well as at generation time.

Stdlib only. Built with the help of Claude Code.
"""
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from checks.common import Report  # noqa: E402
from checks.cpic_guidance import check_cpic_enzyme_coverage  # noqa: E402
from data_generators import cpic as C  # noqa: E402

ROOT = TOOLS.parent
CACHE = TOOLS / "generated_cache" / "cpic_guidance.json"

ROW = {
    "drug": "nortriptyline", "gene": "CYP2D6", "phenotype": "PM",
    "implication": "Greatly reduced metabolism.",
    "recommendation": "Consider a 50% reduction of the usual starting dose.",
    "classification": "Strong", "level": "A", "guideline": 100414,
    "population": "general", "citations": ["23486447"], "version": 1,
}
EXPORT = {
    "fetched": "2026-10-08", "api": "https://api.cpicpgx.org/v1",
    "guidelines": {"100414": {"name": "CYP2D6 and Tricyclics",
                              "url": "https://www.clinpgx.org/guideline/PA166104996",
                              "clinpgxid": "PA166104996", "version": 1}},
    "rows": [ROW],
}


def _written(data):
    """`data` through a temp file, as `read_export` will see it."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                      encoding="utf-8")
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


class ReaderTest(unittest.TestCase):
    """What the reader accepts, and what it refuses to guess at."""

    def test_it_reads_a_well_formed_export(self):
        self.assertEqual(len(C.read_export(_written(EXPORT))["rows"]), 1)

    def test_a_missing_block_is_a_loud_failure(self):
        for key in ("fetched", "guidelines", "rows"):
            data = copy.deepcopy(EXPORT)
            del data[key]
            with self.assertRaises(C.ExportError):
                C.read_export(_written(data))

    def test_a_row_missing_a_field_is_a_loud_failure(self):
        for key in ("implication", "recommendation", "classification", "population"):
            data = copy.deepcopy(EXPORT)
            del data["rows"][0][key]
            with self.assertRaises(C.ExportError):
                C.read_export(_written(data))

    def test_an_uncertainty_phenotype_cannot_reach_the_panel(self):
        # CPIC's "Likely Intermediate" and "Indeterminate" have no population
        # frequency to pair with, so a row carrying one would publish "what this
        # means" with no answer to "how likely is it".
        data = copy.deepcopy(EXPORT)
        data["rows"][0]["phenotype"] = "Indeterminate"
        with self.assertRaises(C.ExportError):
            C.read_export(_written(data))

    def test_a_gene_with_no_frequency_profile_is_a_loud_failure(self):
        # HLA-B with carbamazepine is real CPIC guidance and deliberately out of this
        # corpus: there is no metabolizer table behind it.
        data = copy.deepcopy(EXPORT)
        data["rows"][0]["gene"] = "HLA-B"
        with self.assertRaises(C.ExportError):
            C.read_export(_written(data))

    def test_an_unreadable_population_is_a_loud_failure(self):
        # `pediatrics` answers a different question than the panel asks, and averaging
        # it in with `general` would invent advice CPIC never wrote.
        data = copy.deepcopy(EXPORT)
        data["rows"][0]["population"] = "pediatrics"
        with self.assertRaises(C.ExportError):
            C.read_export(_written(data))

    def test_a_missing_file_is_a_loud_failure(self):
        with self.assertRaises(C.ExportError):
            C.read_export(str(ROOT / "tools" / "data" / "cpic" / "nope.json"))


class ShapeTest(unittest.TestCase):
    """The blocks the panel renders."""

    def test_one_node_carries_two_citations(self):
        # The implication and the recommendation are two sentences backing one claim,
        # so they are two quotes on one node, not two nodes.
        rows = C.guidance_for(EXPORT)["nortriptyline"][0]["rows"]
        self.assertEqual([s["quote"] for s in rows[0]["sources"]],
                         [ROW["implication"], ROW["recommendation"]])

    def test_a_citation_resolves_to_the_guideline(self):
        src = C.guidance_for(EXPORT)["nortriptyline"][0]["rows"][0]["sources"][0]
        self.assertEqual(src["corpus"], "cpic")
        self.assertEqual(src["page"], "PA166104996")
        # Copied by code off a machine corpus, so no judge is owed (check_data family 5).
        self.assertEqual(src["extraction"], "code")

    def test_rows_run_slowest_to_fastest(self):
        data = copy.deepcopy(EXPORT)
        for ph in ("UM", "IM"):
            row = dict(ROW, phenotype=ph)
            data["rows"].append(row)
        rows = C.guidance_for(data)["nortriptyline"][0]["rows"]
        self.assertEqual([r["phenotype"] for r in rows], ["PM", "IM", "UM"])

    def test_the_default_population_is_not_labelled(self):
        block = C.guidance_for(EXPORT)["nortriptyline"][0]
        self.assertNotIn("population", block)

    def test_a_narrower_population_says_so_in_both_languages(self):
        data = copy.deepcopy(EXPORT)
        data["rows"][0]["population"] = "PHT naive"
        block = C.guidance_for(data)["nortriptyline"][0]
        self.assertEqual(set(block["population"]), {"en", "fr"})

    def test_every_readable_population_has_a_label(self):
        self.assertTrue(set(C.POPULATIONS[1:]) <= set(C.POPULATION_LABELS))


class EnzymeClaimTest(unittest.TestCase):
    """The metabolic routes read out of CPIC's wording, and only those."""

    def _claims(self, recommendation):
        data = copy.deepcopy(EXPORT)
        data["rows"][0]["recommendation"] = recommendation
        return C.enzyme_claims_for(C.guidance_for(data))

    def test_a_sentence_naming_both_states_the_route(self):
        claims = self._claims("Consider alternative drug not metabolized by CYP2D6; "
                              "If nortriptyline is warranted, utilize monitoring.")
        self.assertEqual([(r["enzyme"], r["role"]) for r in claims["nortriptyline"]],
                         [("cyp2d6", "substrate")])

    def test_the_quote_is_the_sentence_itself(self):
        rec = ("Consider alternative drug not metabolized by CYP2D6; "
               "If nortriptyline is warranted, utilize monitoring.")
        src = self._claims(rec)["nortriptyline"][0]["sources"][0]
        self.assertEqual(src["quote"], rec)
        self.assertEqual(src["corpus"], "cpic")

    def test_a_sentence_naming_only_the_gene_states_nothing(self):
        # CPIC says the same thing about the *class* all over the guideline; without
        # this drug's own name in it, quoting it here would be us doing the inferring.
        self.assertEqual(self._claims("Consider alternative drug not metabolized by "
                                      "CYP2D6; utilize monitoring."), {})

    def test_a_pair_cpic_never_phrases_that_way_states_nothing(self):
        # The levelled pair alone is a verdict, not a sentence: no claim comes of it.
        self.assertEqual(self._claims("Initiate therapy with recommended starting "
                                      "dose."), {})


class CommittedExportTest(unittest.TestCase):
    """The real export, against the real cache."""

    @classmethod
    def setUpClass(cls):
        cls.cache = json.loads(CACHE.read_text(encoding="utf-8"))
        cls.data = C.read_export(C.export_path(str(ROOT)))

    def test_the_committed_export_still_hashes_to_its_pin(self):
        pins = self.cache.get("export_sha256") or {}
        self.assertTrue(pins, "the cache pins nothing, so its quotes anchor to nothing")
        for name, want in sorted(pins.items()):
            path = ROOT / Path(C.EXPORT_DIR) / name
            self.assertEqual(C.sha256(str(path)), want,
                             f"{name} changed since the cache was built; re-run "
                             f"tools/fetch/fetch_cpic.py")

    def test_every_cached_block_re_derives_exactly(self):
        self.assertEqual(self.cache["guidance"], C.guidance_for(self.data))

    def test_a_two_gene_row_records_the_assumption_it_rests_on(self):
        # Amitriptyline is dosed on CYP2D6 *and* CYP2C19, so a row filed under one of
        # them only says anything with the other pinned to normal.
        rows = [r for r in self.data["rows"] if r["drug"] == "amitriptyline"]
        self.assertTrue(rows, "amitriptyline carries no CPIC rows any more")
        for row in rows:
            other = "CYP2C19" if row["gene"] == "CYP2D6" else "CYP2D6"
            self.assertEqual((row.get("assumes") or {}).get(other), "NM",
                             f"{row['gene']} {row['phenotype']}: no assumption recorded")

    def test_clomipramine_gets_the_cyp2c19_route_nothing_else_states(self):
        # The gap the import surfaced: CPIC dosed clomipramine on CYP2C19 while the
        # enzyme list had no CYP2C19 row at all, Stahl attributing the demethylation to
        # CYP1A2 and the English article naming only CYP2D6. CPIC's own faster-
        # metabolizer sentence names both, so it states the route.
        claims = C.enzyme_claims_for(C.guidance_for(self.data))
        rows = claims.get("clomipramine") or []
        self.assertIn(("cyp2c19", "substrate"),
                      [(r["enzyme"], r["role"]) for r in rows])

    def test_the_emitted_drug_carries_that_route(self):
        # End to end, since the merge keeps whatever an earlier corpus already said
        # about a pair: a reader opening clomipramine must find the CYP2C19 the CPIC
        # guidance under it is about.
        path = ROOT / "public" / "data" / "drugs.jsonl"
        drug = next(json.loads(line) for line in path.read_text(encoding="utf-8")
                    .splitlines() if json.loads(line)["id"] == "clomipramine")
        self.assertIn("cyp2c19", [e["enzyme"] for e in drug["enzymes"]])



class CoverageWarningTest(unittest.TestCase):
    """The standing gate for "CPIC doses this gene, the drug has no row for it"."""

    def _warnings(self, enzymes):
        guidance = C.guidance_for(EXPORT)
        drugs = [{"id": "nortriptyline", "enzymes": enzymes}]
        report = Report()
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_cpic_enzyme_coverage(report, guidance, drugs)
        return [ln.split("[warn]", 1)[1].strip()
                for ln in buf.getvalue().splitlines() if "[warn]" in ln]

    def test_a_dosed_gene_with_no_enzyme_row_is_reported(self):
        # The clomipramine shape: guidance about a gene the Enzymes section never names.
        warns = self._warnings([{"enzyme": "cyp1a2", "role": "substrate"}])
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("CYP2D6", warns[0])

    def test_a_dosed_gene_the_drug_carries_is_silent(self):
        self.assertEqual(self._warnings([{"enzyme": "cyp2d6", "role": "substrate"}]), [])

    def test_the_role_does_not_matter(self):
        # Inhibitor-only would be odd, but the gate is about the gene being named at
        # all: whether the row is the right one is check_cpic_enzyme_claims' business.
        self.assertEqual(self._warnings([{"enzyme": "cyp2d6", "role": "inhibitor"}]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
