#!/usr/bin/env python
"""Unit tests for the transposed *compound* Ki table read (``extract_compound_table``).

Sibutramine's article states its metabolites' Ki in a table with one ROW per compound
and one COLUMN per target, the unit given once in a full-width note row. The read must:
quote the header row down to the compound's row (so the quote names the targets), keep
that quote verbatim on the stored page text (the quote gate), refuse a table whose note
does not say Ki, and never join an enantiomer row onto the racemate's metabolite.

Skipped when ``bs4`` is absent (the fetcher imports it at module level).
Built with the help of Claude Code.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

from lib import drugs_io  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402

HAS_BS4 = importlib.util.find_spec("bs4") is not None
if HAS_BS4:
    from bs4 import BeautifulSoup  # noqa: E402
    import fetch_wikipedia_pharmacology as W  # noqa: E402

TARGETS = {"sert", "net", "dat"}


def _table(note: str) -> str:
    return f"""<div class="mw-parser-output"><table>
<tr><th>Compound</th><th>SERT</th><th>NET</th><th>DAT</th></tr>
<tr><td>Sibutramine</td><td>298–2,800</td><td>350–5,451</td><td>943–1,200</td></tr>
<tr><td>Desmethylsibutramine</td><td>15</td><td>20</td><td>49</td></tr>
<tr><td>(R)-Desmethylsibutramine</td><td>44</td><td>4</td><td>12</td></tr>
<tr><td colspan="4">{note}</td></tr>
</table></div>"""


@unittest.skipUnless(HAS_BS4, "bs4 not installed")
class CompoundTableTest(unittest.TestCase):
    def read(self, note="Values are K<sub>i</sub> (nM)."):
        soup = BeautifulSoup(_table(note), "html.parser")
        return soup, W.extract_compound_table(soup.find("table"), TARGETS)

    def test_reads_each_compound_row(self):
        _, out = self.read()
        rows = {b["target"]: b["ki"]["median"] for b in out["Desmethylsibutramine"]}
        self.assertEqual(rows, {"sert": 15, "net": 20, "dat": 49})

    def test_quote_spans_header_to_row_and_sits_on_the_page(self):
        soup, out = self.read()
        quote = out["Desmethylsibutramine"][0]["quote"]
        self.assertTrue(quote.startswith("Compound | SERT | NET | DAT"))
        self.assertTrue(quote.endswith("Desmethylsibutramine | 15 | 20 | 49"))
        page = W.render_page_text(soup)
        self.assertIn(normalize_for_match(quote), normalize_for_match(page))

    def test_table_without_ki_note_reads_nothing(self):
        self.assertEqual(self.read("Values are IC50 (nM).")[1], {})

    def test_enantiomer_row_never_joins_the_racemate(self):
        _, out = self.read()
        want = set(drugs_io.names_of("Desmethylsibutramine"))
        joined = [name for name in out if set(drugs_io.names_of(name)) & want]
        self.assertEqual(joined, ["Desmethylsibutramine"])


if __name__ == "__main__":
    unittest.main()
