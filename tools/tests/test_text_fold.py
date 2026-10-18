"""The shared folding helpers (tools/text_fold.py) and brand-region normalizer that
replaced per-script copies: pin the behaviour every former copy relied on."""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from data_generators.provenance import brand_regions  # noqa: E402
from lib.text_fold import alnum_key, ascii_key, strip_accents  # noqa: E402


class TextFoldTest(unittest.TestCase):
    def test_strip_accents_keeps_case_and_punctuation(self):
        self.assertEqual(strip_accents("Théralène, ÉTÉ"), "Theralene, ETE")
        self.assertEqual(strip_accents(None), "")

    def test_alnum_key_reconciles_index_headings(self):
        self.assertEqual(alnum_key("Amphetamine (D)"), alnum_key("Amphetamine D"))
        self.assertEqual(alnum_key("Naltrexone-Bupropion"), "naltrexonebupropion")

    def test_ascii_key_is_the_shared_name_join_key(self):
        self.assertEqual(ascii_key("Carbamazepine-10,11-epoxide"), "carbamazepine1011epoxide")
        self.assertEqual(ascii_key(None), "")
        # ASCII only: an accented letter is dropped (alnum_key keeps it).
        self.assertEqual(ascii_key("Tranxène"), "tranxne")

    def test_brand_regions(self):
        self.assertEqual(brand_regions("fr"), ["fr"])
        self.assertEqual(brand_regions(["na", "fr"]), ["na", "fr"])


if __name__ == "__main__":
    unittest.main()
