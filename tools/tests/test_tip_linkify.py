"""A tooltip string must stay linkified once wrapped into a fragment.

`attachTip` (public/js/panel/tooltip.js) linkifies string content but appends a Node as
is, so a helper that turns a source line into ``createTextNode(extra)`` (or drops it into
``el(..., text)``) silently shows the corpus URL as dead text. Every such wrap goes
through ``linkifiedText`` instead.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PANEL = Path(__file__).resolve().parents[2] / "public" / "js" / "panel"
# A tip-content variable wrapped as plain text: the names the pill helpers use for it.
BAD = re.compile(r"createTextNode\((extra|src|tip|content)\)|el\([^)]*,\s*(src|tip)\)")


class TipLinkifyTest(unittest.TestCase):
    def test_no_plain_text_tip_wrap(self):
        found = [(p.name, n, line.strip())
                 for p in sorted(PANEL.rglob("*.js"))
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if BAD.search(line)]
        self.assertFalse(found, "wrap tooltip text with linkifiedText(), not a text node")


if __name__ == "__main__":
    unittest.main()
