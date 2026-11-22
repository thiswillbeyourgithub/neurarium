"""A Wikipedia Ki cell that reports percent inhibition is not a Ki, and a row measuring no
activity hands out no direction (brexpiprazole's "NET | 0% at 10 μM | Blocker" once
became a 0 nM NET Ki and a NET reuptake-inhibitor binding). Plus the class-wide guard:
no stored Ki is zero or negative.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_wiki_ki_cell.py``
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "fetch"))

try:
    import fetch_wikipedia_pharmacology as wiki  # noqa: E402 (needs beautifulsoup4)
    import fetch_binding_direction_tables as tables  # noqa: E402
except ModuleNotFoundError:  # bs4 is author-side
    wiki = tables = None


@unittest.skipIf(wiki is None, "beautifulsoup4 not installed")
class KiCellTest(unittest.TestCase):
    def test_percent_inhibition_is_not_a_ki(self):
        self.assertIsNone(wiki.parse_ki_cell("0% at 10 μM"))
        # "66% at 1 μM" was read as a 1000 nM Ki (the 66 000 dropped as a ceiling).
        self.assertIsNone(wiki.parse_ki_cell("66% at 1 μM"))

    def test_a_ki_is_never_zero(self):
        self.assertIsNone(wiki.parse_ki_cell("0"))
        self.assertEqual(wiki.parse_ki_cell("0.20–9.8 nM")["median"], 5.0)

    def test_a_labelled_ki_beside_an_efficacy_percent_survives(self):
        self.assertEqual(wiki.parse_ki_cell("12 (Ki) 86% (Emax)")["median"], 12.0)

    def test_only_a_zero_activity_row_is_refused_a_direction(self):
        self.assertTrue(tables.NO_ACTIVITY_RE.search("0% at 10 μM"))
        for cell in ("65% 10 μM", "100%", "10% at 1 μM", ">10,000", "0.5"):
            self.assertFalse(tables.NO_ACTIVITY_RE.search(cell), cell)


class StoredKiTest(unittest.TestCase):
    def test_no_stored_ki_is_zero_or_negative(self):
        root = TOOLS / "data"
        bad = []
        for name in ("drugs_data.jsonl", "metabolites_data.jsonl"):
            for line in (root / name).read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                for b in rec.get("bindings") or []:
                    ki = b.get("ki") or {}
                    for k in ("median", "min", "max"):
                        if ki.get(k) is not None and ki[k] <= 0:
                            bad.append(f"{rec['id']} {b.get('target')} ki.{k}={ki[k]}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
