#!/usr/bin/env python
"""Unit tests for the PharmFreq export reader (corpus #13) and its hash pins.

This corpus is the one whose raw table ships with the repo, and the one whose quote is
therefore proved by re-derivation rather than by finding it on a page. Two things have
to hold for that proof to be worth anything: the reader has to refuse an export it does
not understand instead of quietly dropping rows, and the committed cache has to still
describe the committed files. Both are checked here, the second against the real
`tools/data/pharmfreq/`, so a refreshed download that nobody re-ran the fetcher over
fails in the test suite as well as at generation time.

Stdlib only. Built with the help of Claude Code.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from data_generators import pharmfreq as P  # noqa: E402
from data_generators.drugs import METABOLIZER_GROUPS  # noqa: E402

ROOT = TOOLS.parent
EXPORT = ROOT / P.EXPORT_DIR
CACHE = TOOLS / "generated_cache" / "enzyme_variability.json"

HEADER = "Subgroup\tGene\tPhenotype\tFrequency\n"


def _tsv(tmp, name, body):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(HEADER + body)
    return path


class ReaderTest(unittest.TestCase):
    """What the reader accepts, and what it refuses to guess at."""

    def test_it_reads_a_gene_into_group_and_phenotype(self):
        with tempfile.TemporaryDirectory() as tmp:
            _tsv(tmp, "a.txt", "European\tCYP2D6\tPM\t0.058\n"
                               "European\tCYP2D6\tNM\t0.942\n")
            self.assertEqual(P.read_export(tmp),
                             {"CYP2D6": {"european": {"PM": 0.058, "NM": 0.942}}})

    def test_a_blank_line_is_not_a_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            _tsv(tmp, "a.txt", "European\tCYP2D6\tPM\t0.058\n\n")
            self.assertEqual(len(P.read_export(tmp)["CYP2D6"]["european"]), 1)

    def test_an_unknown_subgroup_is_a_loud_failure(self):
        # Never a silent drop: a subgroup we have no label for would otherwise vanish
        # from a profile that still reads as complete.
        with tempfile.TemporaryDirectory() as tmp:
            _tsv(tmp, "a.txt", "Atlantean\tCYP2D6\tPM\t0.058\n")
            with self.assertRaises(P.ExportError):
                P.read_export(tmp)

    def test_an_unknown_phenotype_is_a_loud_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            _tsv(tmp, "a.txt", "European\tCYP2D6\tXM\t0.058\n")
            with self.assertRaises(P.ExportError):
                P.read_export(tmp)

    def test_a_reshaped_export_is_a_loud_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            _tsv(tmp, "a.txt", "European\tCYP2D6\tPM\n")
            with self.assertRaises(P.ExportError):
                P.read_export(tmp)

    def test_an_empty_directory_is_a_loud_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ExportError):
                P.read_export(tmp)


class QuoteTest(unittest.TestCase):
    """The sentence the gate re-derives."""

    PROFILE = {"european": {"PM": 0.058, "NM": 0.942},
               "east_asian": {"PM": 0.01, "NM": 0.99}}

    def test_the_quote_carries_every_number_the_panel_shows(self):
        q = P.quote_for("CYP2D6", P.ordered_profile(self.PROFILE))
        for want in ("CYP2D6", "PM 5.8%", "NM 94.2%", "PM 1.0%", "NM 99.0%"):
            self.assertIn(want, q)

    def test_the_groups_are_listed_in_the_order_the_panel_draws_them(self):
        q = P.quote_for("CYP2D6", P.ordered_profile(self.PROFILE))
        order = [slug for slug in METABOLIZER_GROUPS if slug in self.PROFILE]
        seen = [q.index(METABOLIZER_GROUPS[slug]["en"]) for slug in order]
        self.assertEqual(seen, sorted(seen))

    def test_a_group_the_gene_misses_is_left_out_rather_than_zeroed(self):
        # CYP3A5 has no Oceanian row. Printing it as 0% would assert a measurement
        # nobody made; the profile simply has no such group.
        self.assertNotIn("oceanian", P.ordered_profile(self.PROFILE))


class CommittedExportTest(unittest.TestCase):
    """The real files, against the real cache."""

    @classmethod
    def setUpClass(cls):
        cls.cache = json.loads(CACHE.read_text(encoding="utf-8"))
        cls.raw = P.read_export(str(EXPORT))

    def test_every_committed_file_still_hashes_to_its_pin(self):
        pins = self.cache.get("export_sha256") or {}
        self.assertTrue(pins, "the cache pins nothing, so its quotes anchor to nothing")
        on_disk = set(P.export_files(str(EXPORT)))
        self.assertEqual(set(pins), on_disk,
                         "the pinned files and the committed files have parted ways; "
                         "re-run tools/fetch/fetch_pharmfreq.py")
        for name, want in sorted(pins.items()):
            self.assertEqual(P.sha256(str(EXPORT / name)), want,
                             f"{name} changed since the cache was built; re-run "
                             f"tools/fetch/fetch_pharmfreq.py")

    def test_every_cached_profile_and_quote_re_derives_exactly(self):
        for eid, entry in sorted(self.cache["enzymes"].items()):
            gene = entry["gene"]
            self.assertEqual(P.GENE_ENZYMES.get(gene), eid)
            want = P.ordered_profile(self.raw[gene])
            self.assertEqual(entry["profile"], want, f"{eid}: profile drifted")
            for src in entry["sources"]:
                self.assertEqual(src["page"], gene)
                self.assertEqual(src["quote"], P.quote_for(gene, want),
                                 f"{eid}: quote drifted")

    def test_the_frequencies_of_a_group_sum_to_one(self):
        # Not a claim about PharmFreq's arithmetic so much as a tripwire on our own
        # reading of it: a dropped phenotype row would show up here first.
        for gene, profile in sorted(self.raw.items()):
            for slug, row in sorted(profile.items()):
                self.assertAlmostEqual(sum(row.values()), 1.0, places=2,
                                       msg=f"{gene}/{slug} sums to {sum(row.values())}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
