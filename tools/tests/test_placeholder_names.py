#!/usr/bin/env python
"""A placeholder word ("Other", "TODO", "N/A", ...) never ships as a brand, holder or
originator name, whatever corpus wrote it.

Stahl closes some "Brands" lists with a literal "Other" bullet; the word is on the page,
so the verbatim-quote gate confirmed it and six drugs shipped a brand called "Other".

    python -m unittest discover -t tools/tests -s tools/tests -p test_placeholder_names.py

Built with the help of Claude Code.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib.placeholder import is_placeholder  # noqa: E402
from lib import drugs_io  # noqa: E402
from data_generators.provenance import _drug_brands  # noqa: E402
from data_generators import origin  # noqa: E402
import apply_brand_sources as ABS  # noqa: E402
import apply_brand_names as ABN  # noqa: E402

BAD = ["Other", "Others", "Generic", "TODO", "N/A", "None", "Unknown", "", "   ", " other. "]


class PlaceholderTest(unittest.TestCase):
    def test_is_placeholder(self):
        for bad in BAD + [None, 3]:
            self.assertTrue(is_placeholder(bad), bad)
        for good in ("Valium", "Otherex", "Nonexa", "Diastat"):
            self.assertFalse(is_placeholder(good), good)

    def test_generator_rejects_a_placeholder_brand_in_any_region(self):
        for region in ("na", "eu", "fr", ["na", "fr"]):
            for bad in BAD:
                with self.assertRaises(ValueError, msg=(region, bad)):
                    _drug_brands("x", [{"name": bad, "region": region}])
        self.assertEqual(_drug_brands("x", [{"name": "Valium", "region": "na"}])[0]["name"],
                         "Valium")

    def test_generator_rejects_a_placeholder_holder_or_originator(self):
        for bad in BAD:
            with self.assertRaises(ValueError, msg=bad):
                origin.drug_origin({"id": "x", "holders": [{"market": "us", "names": [bad]}]})
            with self.assertRaises(ValueError, msg=bad):
                origin.drug_origin({"id": "x", "originator": {"name": bad}})

    def test_stahl_parser_drops_the_other_bullet(self):
        answer = "<b>•</b><b> </b>Valium<br/>• Diastat<br/>• Other<br/>"
        self.assertEqual(ABS.parse_brands(answer), ["Valium", "Diastat"])

    def test_fr_applier_refuses_a_placeholder(self):
        existing, seen = [], set()
        self.assertFalse(ABN.add_brand(existing, seen, "Other", "fr", {}))
        self.assertEqual(existing, [])

    def test_committed_data_has_no_placeholder_name(self):
        bad = []
        for d in drugs_io.load_drugs():
            for holder in (d, *(d.get("formulations") or [])):
                bad += [(d["id"], "brand", b.get("name")) for b in holder.get("brands") or []
                        if is_placeholder(b.get("name"))]
            for h in d.get("holders") or []:
                bad += [(d["id"], "holder", n) for n in h.get("names") or [] if is_placeholder(n)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
