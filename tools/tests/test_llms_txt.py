"""``public/llms.txt``: generated from the emitted data, never hand-edited.

Run: ``python -m unittest tools.tests.test_llms_txt``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data_generators"))
import llms_txt  # noqa: E402


class RenderTest(unittest.TestCase):
    def test_lists_every_collection_with_count_and_fields(self):
        text = llms_txt.render("1.2.3", {"drugs": [{"id": "a"}, {"id": "b", "tmax": 1}]},
                               ["drug_targets"], 7)
        self.assertIn("Version 1.2.3.", text)
        self.assertIn("drugs.jsonl): 2 ", text)
        self.assertIn("`id`, `tmax`", text)
        self.assertIn("7 source quotes", text)
        self.assertIn(llms_txt.CONTACT_URL, text)
        self.assertIn(llms_txt.REPO_URL, text)

    def test_undescribed_collection_raises(self):
        with self.assertRaises(KeyError):
            llms_txt.render("1.2.3", {"brand_new": []}, [], 0)


if __name__ == "__main__":
    unittest.main()
