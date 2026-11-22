"""check_data's expected-by-design allowlist (tools/checks/expected.py): an allowlisted
item is a review line, anything else still a warning.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_expected_warnings.py``
"""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checks.common import Report  # noqa: E402
from checks.connectivity import check_connectivity  # noqa: E402
from checks.innervation import check_innervation  # noqa: E402


def run(fn, *args):
    r = Report()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        fn(r, *args)
    return r, out.getvalue()


class ExpectedTest(unittest.TestCase):
    def test_one_way_source_nucleus_is_reviewed_not_warned(self):
        structures = [{"id": "nucleus_basalis_R"}, {"id": "frontal_R"}, {"id": "medulla"}]
        projections = [{"from": "nucleus_basalis_R", "to": "frontal_R"},
                       {"from": "frontal_R", "to": "medulla"}]
        r, out = run(check_connectivity, structures, projections)
        self.assertEqual((r.warnings, r.reviews), (1, 1))
        self.assertIn("medulla", out)   # a real gap still warns

    def test_local_interneurons_and_local_systems_are_reviewed(self):
        meta = {"system_flow_kinds": {"cholinergic": "cholinergic"}}
        structures = [{"id": b} for b in ("caudate", "hypothalamus", "frontal")]
        receptors = [{"id": "m1", "family": "cholinergic", "locations": ["caudate", "hypothalamus"]},
                     {"id": "mu", "family": "opioidergic", "locations": ["caudate"]}]
        projections = [{"kind": "cholinergic", "from": "frontal", "to": "frontal"}]
        r, out = run(check_innervation, meta, structures, projections, receptors)
        self.assertEqual(r.reviews, 2)            # caudate interneurons + opioid system
        self.assertIn("hypothalamus", out)        # still a warning
        self.assertNotIn("opioidergic (", out)


if __name__ == "__main__":
    unittest.main()
