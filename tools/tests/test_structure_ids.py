#!/usr/bin/env python
"""Unit tests for tools/lib/structure_ids.py: the one hemisphere-suffix rule.

Regression: three copies chained ``removesuffix("_R").removesuffix("_L")`` while the
rest used a one-suffix regex, so an odd id like ``x_L_R`` had two bases depending on
which module asked.

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.structure_ids import base_id, bases_of  # noqa: E402


class StructureIdsTest(unittest.TestCase):
    def test_strips_one_hemisphere_suffix(self):
        self.assertEqual(base_id("accumbens_R"), "accumbens")
        self.assertEqual(base_id("accumbens_L"), "accumbens")
        self.assertEqual(base_id("raphe"), "raphe")
        self.assertEqual(base_id("x_L_R"), "x_L")
        self.assertEqual(base_id("frontal_RL"), "frontal_RL")

    def test_falsy_id_passes_through(self):
        self.assertIsNone(base_id(None))
        self.assertEqual(base_id(""), "")

    def test_bases_of_records(self):
        self.assertEqual(bases_of([{"id": "a_R"}, {"id": "a_L"}, {"id": "raphe"}, {}]),
                         {"a", "raphe", ""})


if __name__ == "__main__":
    unittest.main(verbosity=2)
