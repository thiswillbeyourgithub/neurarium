#!/usr/bin/env python
"""Detail-panel headings stay selectable, so a reader can copy a section title.

The panel's collapsible section titles once inherited `user-select: none` from the
shared caret rule (`.disclosure > summary`), which made every heading and subtitle
impossible to select. A click that ends a selection no longer toggles the section
(panel/dom.js keepSelectionOnSummaries), so the heading has no reason to opt out.

Built with the help of Claude Code.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viewer_source import viewer_css  # noqa: E402

# Selector fragments of panel content a reader may want to copy.
CONTENT = ("summary", ".panel-sec", ".section-sub", ".panel-subsec", "#info-body")


class PanelHeadingsSelectableTest(unittest.TestCase):

    def test_no_panel_heading_rule_disables_selection(self):
        css = re.sub(r"/\*.*?\*/", "", viewer_css(), flags=re.S)
        offenders = [sel.strip() for sel, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                     if re.search(r"user-select:\s*none", decls)
                     and any(frag in sel for frag in CONTENT)]
        self.assertEqual(offenders, [], "panel text a reader may want to copy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
