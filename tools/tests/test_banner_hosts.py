"""Every page loading a banner script carries the element that script writes into.

js/dev-banner.js and js/error-banner.js return silently when `#dev-banner` / `#banners`
is missing, so a page loading them without the markup (drugs-map.html once did) shows
neither the WIP banner nor any error, with nothing in the console to say so.
"""

import re
import unittest
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "public"
# script -> the element ids it needs on the page
NEEDS = {"js/dev-banner.js": ["banners", "dev-banner"], "js/error-banner.js": ["banners"]}


class BannerHostTest(unittest.TestCase):
    def test_pages_loading_a_banner_script_have_its_host(self):
        pages = sorted(PUBLIC.glob("*.html"))
        self.assertTrue(pages)
        for page in pages:
            html = page.read_text(encoding="utf-8")
            for script, ids in NEEDS.items():
                if f'src="{script}"' not in html:
                    continue
                for el_id in ids:
                    with self.subTest(page=page.name, script=script, id=el_id):
                        self.assertRegex(html, rf'id="{re.escape(el_id)}"')


if __name__ == "__main__":
    unittest.main()
