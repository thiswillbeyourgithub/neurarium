#!/usr/bin/env python
"""Unit tests for tools/fetch/fetch_quote_headers.py's heading classification.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable
directly::

    python tools/tests/test_quote_headers.py

pytest-discoverable. Two resolvers are covered. ``classify`` is the whole Stahl
pass: it decides whether a heading line is one of the book's ALL-CAPS sections, a
Title Case subsection, a monograph title, or extraction noise. Every case below is
a real heading line from the author-side page tree, kept because it sits on an edge
that cost a wrong answer while the resolver was being written. ``OutlineIndex`` is
the other four books: it reads their generated ``INDEX.md`` outline, so those tests
write a small outline of their own. Neither needs a page tree.

Built with the help of Claude Code.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tools" / "fetch"))
import fetch_quote_headers as H  # noqa: E402

DRUGS = {"clozapine", "amphetamine d l"}   # already folded, as StahlPages holds them


def classify(line):
    return H.classify(H._clean(line), DRUGS)


class ClassifyTest(unittest.TestCase):

    def test_a_section_is_read_through_its_ocr_prefix(self):
        """"## LEE **DOSING AND USE**": the extraction spills a fragment of the page
        furniture in front of the heading on ~10 pages."""
        self.assertEqual(classify("LEE **DOSING AND USE**"),
                         ("section", "DOSING AND USE", None))
        self.assertEqual(classify("[oT **DOSING AND USE**"),
                         ("section", "DOSING AND USE", None))
        self.assertEqual(classify("~~Co~~ **THERAPEUTICS**"),
                         ("section", "THERAPEUTICS", None))

    def test_a_subsection_naming_a_section_is_not_that_section(self):
        """The bug this whole classifier is shaped around: a case-blind substring
        test reads "How Drug Causes Side Effects" as the SIDE EFFECTS section, which
        then swallows the four subsections that follow it in every monograph."""
        self.assertEqual(classify("**How Drug Causes Side Effects**"),
                         ("sub", "How Drug Causes Side Effects", None))
        self.assertEqual(classify("**Notable Side Effects**"),
                         ("sub", "Notable Side Effects", None))
        self.assertEqual(classify("**What to Do About Side Effects**"),
                         ("sub", "What to Do About Side Effects", None))

    def test_a_merged_line_splits_into_section_plus_subsection(self):
        self.assertEqual(classify("**DOSING AND USE Usual Dosage Range**"),
                         ("section", "DOSING AND USE", "Usual Dosage Range"))
        self.assertEqual(classify("**THERAPEUTICS Brands** • Ingrezza ~~po~~"),
                         ("section", "THERAPEUTICS", "Brands"))
        self.assertEqual(
            classify("**SIDE EFFECTS How Drug Causes Side Effects** ~~es~~ • "
                     "Anticholinergic activity may explain sedative effects"),
            ("section", "SIDE EFFECTS", "How Drug Causes Side Effects"))

    def test_a_monograph_title_is_its_own_kind(self):
        """It has to end the previous drug's headings, or a section leaks across the
        monograph boundary and a quote gets the wrong drug's breadcrumb."""
        self.assertEqual(classify("**CLOZAPINE**"), ("drug", "CLOZAPINE", None))
        self.assertEqual(classify("**AMPHETAMINE (D,L)**"),
                         ("drug", "AMPHETAMINE (D,L)", None))

    def test_a_stray_all_caps_line_is_noise_not_a_heading(self):
        self.assertEqual(classify("**684**"), ("noise", None, None))
        self.assertEqual(classify("~~SS~~"), ("noise", None, None))

    def test_a_subsection_keeps_only_its_own_name(self):
        self.assertEqual(classify("**Brands** • Topamax"), ("sub", "Brands", None))
        self.assertEqual(classify("**Generic?** Yes"), ("sub", "Generic? Yes", None))


class OutlineIndexTest(unittest.TestCase):
    """The other four books resolve off their PDF outline, not their page text."""

    def _index(self, body):
        path = Path(self.tmp) / "INDEX.md"
        path.write_text(body, encoding="utf-8")
        return H.OutlineIndex(str(path))

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = self._dir.name
        self.addCleanup(self._dir.cleanup)

    def test_a_page_takes_the_deepest_entry_that_starts_at_or_before_it(self):
        idx = self._index(
            "- [Part III](pages/300.md) — p300\n"
            "  - [14 Modulation](pages/360.md) — p360\n"
            "    - [Highlights](pages/368.md) — p368\n"
            "- [Part IV](pages/400.md) — p400\n")
        self.assertEqual(idx.locate(369),
                         ["Part III", "14 Modulation", "Highlights"])
        self.assertEqual(idx.locate(361), ["Part III", "14 Modulation"])
        self.assertEqual(idx.locate(310), ["Part III"])
        self.assertEqual(idx.locate(401), ["Part IV"])

    def test_a_page_before_the_first_entry_gets_nothing(self):
        """Better an absent breadcrumb than the book's cover page as a location."""
        idx = self._index("- [Introduction](pages/10.md) — p10\n")
        self.assertEqual(idx.locate(3), [])

    def test_a_trail_keeps_only_its_deepest_levels(self):
        """Kandel nests book > part > chapter > section: the book title is not a
        location, and a four-part breadcrumb is a wall of text in a tooltip."""
        idx = self._index(
            "- [The whole book](pages/2.md) — p2\n"
            "  - [Part I](pages/20.md) — p20\n"
            "    - [1 The Brain](pages/50.md) — p50\n"
            "      - [Distinct Regions](pages/59.md) — p59\n")
        self.assertEqual(idx.locate(59),
                         ["Part I", "1 The Brain", "Distinct Regions"])

    def test_a_chapter_pdf_filename_reads_as_a_chapter(self):
        """Nieuwenhuys' outline is the list of per-chapter PDFs it was assembled
        from, so the extension and the missing space are extraction artifacts."""
        idx = self._index("- [15.Telencephalon Neocortex.pdf](pages/617.md) (p617)\n")
        self.assertEqual(idx.locate(617), ["15. Telencephalon Neocortex"])

    def test_a_missing_index_resolves_nothing_rather_than_raising(self):
        idx = H.OutlineIndex(str(Path(self.tmp) / "absent.md"))
        self.assertFalse(idx.ok)
        self.assertEqual(idx.locate(1), [])


class EmittedHeadingsTest(unittest.TestCase):
    """The emitted quote table, which is committed, so these run on any clone."""

    @classmethod
    def setUpClass(cls):
        path = REPO_ROOT / "public" / "data" / "quotes.jsonl"
        cls.quotes = [json.loads(line) for line in
                      path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_every_heading_is_a_non_empty_list_of_non_blank_strings(self):
        seen = 0
        for q in self.quotes:
            trail = q.get("heading")
            if trail is None:
                continue
            seen += 1
            self.assertIsInstance(trail, list, q["id"])
            self.assertTrue(trail, f"{q['id']} carries an empty trail")
            self.assertLessEqual(len(trail), H.MAX_TRAIL, q["id"])
            for part in trail:
                self.assertTrue(str(part).strip(), f"{q['id']} blank crumb")
        self.assertGreater(seen, 0, "no quote carries a heading")

    def test_only_book_corpora_carry_one(self):
        """A Ki CSV row and a GtoPdb tissue line have no chapter to sit in; storing
        a heading for them would be a fiction."""
        for q in self.quotes:
            if q.get("heading"):
                self.assertNotIn(q["corpus"], {"pdsp_ki", "gtopdb", "gtopdb_ki",
                                               "gtopdb_class", "allen_ahba",
                                               "wikipedia_pharm", "wikipedia_fr"},
                                 q["id"])

    def test_a_full_stahl_trail_names_a_real_section_in_the_middle(self):
        """The shape check_data.py cannot make: a full Stahl trail is drug >
        section > subsection, so its middle level is one of the book's own
        sections. A shorter trail is a level the resolver could not pin down and
        deliberately omitted, so only the full ones are checkable here."""
        sections = {s.capitalize() for s in H.SECTIONS}
        full = 0
        for q in self.quotes:
            trail = q.get("heading")
            if q["corpus"] != "stahl" or not trail or len(trail) < 3:
                continue
            full += 1
            self.assertIn(trail[1], sections, f"{q['id']} {trail!r}")
        self.assertGreater(full, 0, "no full Stahl trail emitted")

    def test_the_same_subsection_always_reports_the_same_section(self):
        """Stahl's subsection vocabulary is closed and stable across the 158
        monographs; a subsection reporting two different parents means the derived
        map lost to a positional fallback somewhere."""
        parent = {}
        for q in self.quotes:
            trail = q.get("heading") or []
            if q["corpus"] != "stahl" or len(trail) < 3:
                continue
            prev = parent.setdefault(trail[2], trail[1])
            self.assertEqual(prev, trail[1],
                             f"{trail[2]!r} reported under two sections")


if __name__ == "__main__":
    unittest.main(verbosity=2)
