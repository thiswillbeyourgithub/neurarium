"""pdf_to_pages falls back to the plain text layer on a page whose Markdown lost
its body (pymupdf4llm drops rotated text, so a landscape table page came back as
its running header only: the AGNP TDM Table 5 pages)."""

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "fetch"))
sys.path.insert(0, str(TOOLS))

from pdf_to_pages import pick_page_text  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402


class PickPageTextTest(unittest.TestCase):
    HEADER = "**Pharmacopsychiatry**\n\nHart XM et al. 2026 185\n"
    LAYER = ("Pharmacopsychiatry\nAmitriptyline 12 h\n80–200 ng/mL \n(amitriptyline \n"
             "plus \nnortriptyline)\nDepression\n4–9 d\n300 ng/mL\n1\nCyamema-\nzine\n")

    def test_header_only_markdown_falls_back_to_text_layer(self):
        self.assertEqual(pick_page_text(self.HEADER, self.LAYER), self.LAYER)

    def test_full_markdown_is_kept(self):
        md = "**Amitriptyline** 12 h 80-200 ng/mL plus nortriptyline Depression"
        self.assertIs(pick_page_text(md, "Amitriptyline 12 h 80-200 ng/mL plus "
                                         "nortriptyline Depression"), md)

    def test_fallback_row_is_quotable_as_running_text(self):
        """A table row quoted on one line matches the cell-per-line layer."""
        page = normalize_for_match(pick_page_text(self.HEADER, self.LAYER))
        quote = ("Amitriptyline 12 h 80–200 ng/mL (amitriptyline plus "
                 "nortriptyline) Depression 4–9 d 300 ng/mL 1")
        self.assertIn(normalize_for_match(quote), page)
        self.assertIn("cyamemazine", page)


if __name__ == "__main__":
    unittest.main()
