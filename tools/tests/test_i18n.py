#!/usr/bin/env python
"""The viewer's message catalogue: EN and FR must describe the same UI.

`js/i18n.js` holds both catalogues, English first. A key added to one and forgotten
in the other does not crash: `pick` falls back to the English string, so the French
site quietly turns English one label at a time, which is exactly the kind of rot
nobody notices until it is everywhere. And a `{placeholder}` dropped in translation
prints a literal `{n}` at a reader.

The scan is a regex over one-line `"key": "value"` entries rather than a JS parse. It
is applied identically to both halves, so an entry it cannot see is invisible on both
sides and parity still means what it says.

Built with the help of Claude Code.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
I18N = ROOT / "public" / "js" / "i18n.js"
ENTRY = re.compile(r'^\s*"([A-Za-z0-9_.]+)":\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)
PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def catalogues():
    """``(en, fr)`` as ``key -> string``, split where the keys start repeating."""
    en, fr = {}, {}
    for key, value in ENTRY.findall(I18N.read_text(encoding="utf-8")):
        (fr if key in en else en)[key] = value
    return en, fr


class CatalogueParityTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.en, cls.fr = catalogues()

    def test_both_catalogues_were_actually_found(self):
        # A guard on the guard: if the regex ever stops matching, every assertion
        # below would pass over two empty dicts.
        self.assertGreater(len(self.en), 300)

    def test_no_key_is_missing_its_translation(self):
        self.assertEqual(sorted(set(self.en) - set(self.fr)), [],
                         "these render in English on the French site")

    def test_no_translation_is_left_over(self):
        self.assertEqual(sorted(set(self.fr) - set(self.en)), [],
                         "these translate a key the UI no longer asks for")

    def test_a_translation_fills_the_same_placeholders(self):
        bad = []
        for key, text in self.en.items():
            want = set(PLACEHOLDER.findall(text))
            got = set(PLACEHOLDER.findall(self.fr.get(key, "")))
            if want != got:
                bad.append((key, sorted(want), sorted(got)))
        self.assertEqual(bad, [], "a dropped placeholder prints as literal braces, an "
                                  "added one never gets filled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
