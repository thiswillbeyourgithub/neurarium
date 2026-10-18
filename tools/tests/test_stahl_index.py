#!/usr/bin/env python
"""Unit tests for ``tools/stahl_index.py``, the one reader of Stahl's ``INDEX.md``.

Stdlib ``unittest`` only. Drives the parser and the span search over a hand-built index
and page tree in a temp dir, so it runs on a clone that lacks the gitignored book::

    python tools/tests/test_stahl_index.py

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import stahl_index  # noqa: E402
from lib.drugs_io import ascii_key  # noqa: E402

# The shape tools/fetch/build_index.py writes: a header, then one row per monograph,
# a one-page monograph spelled without a dash.
INDEX_MD = """# Stahl Prescriber's Guide: drug page index

| # | Drug | Pages |
|---|------|-------|
| 1 | Amitriptyline | [39-46](pages/39.md) |
| 2 | Amphetamine (D,L) | [47-52](pages/47.md) |
| 3 | Zaleplon | [60](pages/60.md) |
| 4 | Élan | [61-62](pages/61.md) |
"""


class StahlIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.index = root / "INDEX.md"
        self.index.write_text(INDEX_MD, encoding="utf-8")
        self.pages = root / "pages"
        self.pages.mkdir()
        (self.pages / "40.md").write_text("Brands\n- **Elavil**\n", encoding="utf-8")
        (self.pages / "42.md").write_text("It is a tri-\ncyclic antidepressant.\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_in_book_order_with_one_page_spans(self):
        self.assertEqual(stahl_index.rows(self.index), [
            ("Amitriptyline", 39, 46), ("Amphetamine (D,L)", 47, 52),
            ("Zaleplon", 60, 60), ("Élan", 61, 62)])

    def test_missing_index_raises_unless_missing_ok(self):
        gone = self.index.with_name("nope.md")
        self.assertEqual(stahl_index.rows(gone, missing_ok=True), [])
        with self.assertRaises(FileNotFoundError):
            stahl_index.rows(gone)

    def test_ranges_fold_is_the_callers(self):
        # Default alnum_key keeps the accented letter, ascii_key drops it, str.lower
        # keeps the punctuation: each caller looks names up with its own fold.
        self.assertIn("amphetaminedl", stahl_index.ranges(path=self.index))
        self.assertIn("élan", stahl_index.ranges(path=self.index))
        self.assertIn("lan", stahl_index.ranges(ascii_key, path=self.index))
        self.assertEqual(stahl_index.ranges(str.lower, path=self.index)["amphetamine (d,l)"],
                         (47, 52))

    def test_find_page_uses_the_quote_gate_normalization(self):
        # Emphasis and a hyphenated line break fold away, as in check_data.
        self.assertEqual(stahl_index.find_page(39, 46, "Elavil", pages=self.pages), 40)
        self.assertEqual(stahl_index.find_page(39, 46, "tricyclic antidepressant",
                                               pages=self.pages), 42)
        self.assertIsNone(stahl_index.find_page(39, 41, "tricyclic antidepressant",
                                                pages=self.pages))

    def test_find_page_min_chars_refuses_a_short_needle(self):
        self.assertIsNone(stahl_index.find_page(39, 46, "", pages=self.pages))
        self.assertEqual(stahl_index.find_page(39, 46, "Elavil", pages=self.pages), 40)
        self.assertIsNone(stahl_index.find_page(39, 46, "Elavil", min_chars=12,
                                                pages=self.pages))


if __name__ == "__main__":
    unittest.main()
