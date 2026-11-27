#!/usr/bin/env python
"""Every `button.collapse-header` (section toggle) in index.html holds exactly two children: one label span,
then the chevron.

The header is a flex row with `justify-content: space-between`, so each direct child
becomes its own flex item. A "beta" tag dropped straight into the button (instead of
inside the label span, next to the word) becomes a third item and floats to the middle
of the row, which is how the Functional areas heading once rendered. Nothing crashes,
so only a markup check sees it.

Stdlib only, no browser. Built with the help of Claude Code.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_search_controls import HTML_TEXT, _Tree  # noqa: E402  the one index.html tree


class CollapseHeaderTest(unittest.TestCase):
    def test_header_is_label_then_chevron(self):
        tree = _Tree()
        tree.feed(HTML_TEXT)
        # A <button>: the panel's own #controls-header shares the class but is a
        # toolbar row of several buttons, not a section toggle.
        headers = [n for n in tree.walk() if n.tag == "button"
                   and "collapse-header" in (n.attrs.get("class") or "").split()]
        self.assertTrue(headers, "no .collapse-header found, the selector drifted")
        for h in headers:
            kids = h.kids
            name = h.attrs.get("id") or h.attrs.get("class")
            with self.subTest(header=name):
                self.assertEqual(len(kids), 2,
                                 f"{name}: wrap the label (and any beta tag) in one <span>, "
                                 f"then the chevron; got {[k.tag for k in kids]}")
                self.assertIn("chevron", (kids[1].attrs.get("class") or "").split(),
                              f"{name}: the chevron must be the last child")


if __name__ == "__main__":
    unittest.main()
