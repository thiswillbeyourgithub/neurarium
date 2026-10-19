"""Tests for the shared duration applier (``tools/sourcing/apply_tmax.apply_judged``).

Built with the help of Claude Code.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_tmax  # noqa: E402
import fetch_half_life  # noqa: E402


class OwnedElsewhereTest(unittest.TestCase):
    """A pick for a drug the fetcher now skips (another pass owns the fact) is stale,
    not wrong: ``apply_half_life`` used to print "1 rejected: lithium" because Stahl had
    since sourced lithium's half-life and the fetcher no longer offered it."""

    def drugs(self):
        return [{"id": "lithium", "half_life_sources": [{"corpus": "stahl"}]},
                {"id": "ghost"}]

    def test_owned_drug_is_skipped_not_rejected(self):
        judged = {"lithium": {"index": 0, "hours": 18.0}}
        written, rejected, skipped = apply_tmax.apply_judged(
            judged, {}, self.drugs(), "half_life", 2400.0, "too long",
            owned=fetch_half_life.stahl_owned)
        self.assertEqual((written, rejected, skipped), (0, [], ["lithium"]))

    def test_unowned_drug_with_no_offer_is_still_rejected(self):
        judged = {"ghost": {"index": 0, "hours": 1.0}}
        written, rejected, skipped = apply_tmax.apply_judged(
            judged, {}, self.drugs(), "half_life", 2400.0, "too long",
            owned=fetch_half_life.stahl_owned)
        self.assertEqual(written, 0)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(skipped, [])


class StahlOwnedTest(unittest.TestCase):
    """The formulation pass moves a release-specific Stahl T½ off the molecule onto its
    ``formulations[]``; the skip must still see it, or asenapine / propranolol came back
    into the worklist for a Wikipedia molecule-level T½ next to Stahl's per-release one."""

    def test_stahl_on_a_formulation_counts(self):
        drug = {"id": "propranolol", "formulations": [
            {"release": "ir", "half_life_sources": [{"corpus": "stahl"}]}]}
        self.assertTrue(fetch_half_life.stahl_owned(drug))

    def test_non_stahl_formulation_does_not(self):
        drug = {"id": "x", "half_life_sources": [{"corpus": "wikipedia_pharm"}],
                "formulations": [{"release": "ir", "half_life_sources": [{"corpus": "bdpm"}]}]}
        self.assertFalse(fetch_half_life.stahl_owned(drug))


class PlacedOnFormulationTest(unittest.TestCase):
    """A claim ``apply_formulations`` moved onto a formulation is not re-written on the molecule."""

    def test_placed_tmax_is_skipped(self):
        drug = {"id": "x", "formulations": [{"release": "xr", "tmax": {"hours": 6.0}}]}
        written, rejected, skipped = apply_tmax.apply_judged(
            {"x": {"index": 0, "hours": 6.0}}, {}, [drug], "tmax", 24.0, "too long")
        self.assertEqual((written, rejected, skipped), (0, [], ["x"]))
        self.assertNotIn("tmax", drug)


if __name__ == "__main__":
    unittest.main()
