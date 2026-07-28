#!/usr/bin/env python
"""Unit tests for tools/fetch/fetch_quote_headers.py's heading classification.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable
directly::

    python tools/tests/test_quote_headers.py

pytest-discoverable. ``classify`` is the whole pass: it decides whether a heading
line is one of Stahl's ALL-CAPS sections, a Title Case subsection, a monograph
title, or extraction noise. Every case below is a real heading line from the
author-side page tree, kept because it sits on an edge that cost a wrong answer
while the resolver was being written. The tests need no page tree of their own:
they classify strings.

Built with the help of Claude Code.
"""

import json
import sys
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


class EmittedHeadingsTest(unittest.TestCase):
    """The emitted quote table, which is committed, so these run on any clone."""

    @classmethod
    def setUpClass(cls):
        path = REPO_ROOT / "public" / "data" / "quotes.jsonl"
        cls.quotes = [json.loads(line) for line in
                      path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_every_heading_is_a_non_empty_subset_of_the_three_keys(self):
        seen = 0
        for q in self.quotes:
            h = q.get("heading")
            if h is None:
                continue
            seen += 1
            self.assertTrue(h, f"{q['id']} carries an empty heading object")
            self.assertLessEqual(set(h), {"drug", "section", "subsection"})
            for key, value in h.items():
                self.assertTrue(str(value).strip(), f"{q['id']} blank {key}")
        self.assertGreater(seen, 0, "no quote carries a heading")

    def test_only_page_structured_corpora_carry_one(self):
        """A Ki CSV row has no heading to resolve; storing one would be a fiction."""
        for q in self.quotes:
            if q.get("heading"):
                self.assertNotEqual(q["corpus"], "pdsp_ki", q["id"])

    def test_the_same_subsection_always_reports_the_same_section(self):
        """Stahl's subsection vocabulary is closed and stable across the 158
        monographs; a subsection reporting two different parents means the derived
        map lost to a positional fallback somewhere."""
        parent = {}
        for q in self.quotes:
            h = q.get("heading") or {}
            if h.get("section") and h.get("subsection"):
                prev = parent.setdefault(h["subsection"], h["section"])
                self.assertEqual(prev, h["section"],
                                 f"{h['subsection']!r} reported under two sections")


if __name__ == "__main__":
    unittest.main(verbosity=2)
