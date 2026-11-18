#!/usr/bin/env python
"""The `hidden` attribute must beat any class `display` rule.

A control hidden from JS (`el.hidden = true`) stayed visible because its class set
`display: flex` (the Data browser's "Show both hemispheres" checkbox, shown even while
only drug half-lives were listed). One global `[hidden] { display: none !important; }`
in css/base.css (loaded by every page) fixes the whole class of bug; this pins it.

Built with the help of Claude Code.
"""
import re
import unittest
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "public"


class HiddenAttrTest(unittest.TestCase):
    def test_global_hidden_rule(self):
        css = (PUBLIC / "css" / "base.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"(?m)^\[hidden\]\s*\{\s*display:\s*none\s*!important;\s*\}")

    def test_every_page_loads_base_css(self):
        for page in ("index.html", "drugs-map.html"):
            html = (PUBLIC / page).read_text(encoding="utf-8")
            self.assertTrue(re.search(r'href="css/base\.css"', html), page)


if __name__ == "__main__":
    unittest.main()
