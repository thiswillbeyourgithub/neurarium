"""Every page loading a banner script carries the element that script writes into.

js/error-banner.js returns silently when `#banners` is missing, and js/dev-notice.js
when `#dev-modal` is, so a page loading them without the markup (drugs-map.html once did)
shows neither the WIP notice nor any error, with nothing in the console to say so.
"""

import re
import unittest
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "public"
# script -> the element ids it needs on the page
# A module importing dev-notice.js counts as its page loading it (see _loads).
NEEDS = {"js/dev-notice.js": ["dev-modal", "dev-title", "dev-body", "dev-close"],
         "js/error-banner.js": ["banners"]}
# module entry -> the dev-notice import that makes its page show the popup
ENTRIES = {"js/main.js": "js/boot/launch.js", "js/drugs-map-main.js": "js/drugs-map-main.js"}


def _loads(html, script):
    """The page names `script` directly, or its module entry (via the file that calls
    the popup) imports it."""
    if f'src="{script}"' in html:
        return True
    name = script.rsplit("/", 1)[-1]
    return any(f'src="{entry}"' in html and name in (PUBLIC / caller).read_text(encoding="utf-8")
               for entry, caller in ENTRIES.items())


class BannerHostTest(unittest.TestCase):
    def test_pages_loading_a_banner_script_have_its_host(self):
        pages = sorted(PUBLIC.glob("*.html"))
        self.assertTrue(pages)
        # Both pages show the WIP popup: guard the guard against a renamed caller.
        self.assertEqual(sum(_loads(p.read_text(encoding="utf-8"), "js/dev-notice.js")
                             for p in pages), 2)
        for page in pages:
            html = page.read_text(encoding="utf-8")
            for script, ids in NEEDS.items():
                if not _loads(html, script):
                    continue
                for el_id in ids:
                    with self.subTest(page=page.name, script=script, id=el_id):
                        self.assertRegex(html, rf'id="{re.escape(el_id)}"')


if __name__ == "__main__":
    unittest.main()
