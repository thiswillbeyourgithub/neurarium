#!/usr/bin/env python
"""The site's CSS lives in public/css/*.css, linked from each page (`PAGES`: index.html,
drugs-map.html) in cascade order.

Two ways that split rots silently: a new .css file that nobody links (its rules simply
never apply), and a linked file the service worker's precached shell (`SHELL` in
public/sw.js) does not list, so a first offline launch paints an unstyled page.

Built with the help of Claude Code.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viewer_source import INDEX, PAGES, stylesheet_hrefs  # noqa: E402

PUBLIC = INDEX.parent


class StylesheetsTest(unittest.TestCase):

    def test_every_css_file_is_linked_once(self):
        linked = set()
        for page in PAGES:
            hrefs = stylesheet_hrefs(page)
            self.assertEqual(len(hrefs), len(set(hrefs)), f"a stylesheet is linked twice in {page.name}")
            linked |= set(hrefs)
        on_disk = sorted(p.relative_to(PUBLIC).as_posix() for p in (PUBLIC / "css").glob("*.css"))
        self.assertEqual(sorted(linked), on_disk)

    def test_no_inline_style_block_left(self):
        html = INDEX.read_text(encoding="utf-8")
        head = html[:html.index("</head>")]
        self.assertNotIn("<style>", head, "page CSS belongs in public/css/")

    def test_service_worker_precaches_every_stylesheet(self):
        sw = (PUBLIC / "sw.js").read_text(encoding="utf-8")
        shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
        listed = set(re.findall(r'"([^"]+)"', shell))
        for page in PAGES:
            self.assertEqual(set(stylesheet_hrefs(page)) - listed, set(), page.name)


if __name__ == "__main__":
    unittest.main()
