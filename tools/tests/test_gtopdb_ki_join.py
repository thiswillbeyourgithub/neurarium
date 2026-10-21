#!/usr/bin/env python
"""Unit tests for tools/fetch/fetch_gtopdb_ki.py's ligand-name join.

Stdlib ``unittest`` only, runnable directly::

    python tools/tests/test_gtopdb_ki_join.py

GtoPdb release 2026.3.1 renamed ligand 63 from "(-)-propranolol" to plain
"propranolol", the racemate's own name (ligand 564). A name-only join then pooled
the S-enantiomer's curated rows (5-HT1A, 5-HT5A, beta1) into racemic propranolol,
the enantiomer leak tools/chirality.py exists to stop. ``LIGAND_ID_STEREO`` gives
the lost tag back by the stable ligand id.

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fetch"))
import fetch_gtopdb_ki as gk  # noqa: E402


def _row(ligand, ligand_id, target):
    return {"Ligand": ligand, "Ligand ID": ligand_id, "Target": target}


class LigandIdStereoTest(unittest.TestCase):
    ROWS = [
        _row("propranolol", "564", "beta2"),          # the racemate
        _row("propranolol", "63", "5-HT1A"),          # (-)-propranolol, tag dropped upstream
        _row("(+)-propranolol", "7596", "beta1"),     # the antipode, still tagged
    ]

    def test_untagged_enantiomer_does_not_pool_into_the_racemate(self):
        by_ligand = gk.index_by_ligand(self.ROWS)
        got = gk.ligand_rows(by_ligand, "Propranolol", "propranolol")
        self.assertEqual([r["Ligand ID"] for r in got], ["564"])

    def test_pinned_id_still_joins_as_its_own_enantiomer(self):
        by_ligand = gk.index_by_ligand(self.ROWS)
        got = gk.ligand_rows(by_ligand, "(-)-Propranolol", "propranolol")
        self.assertEqual([r["Ligand ID"] for r in got], ["63"])


class AliasEnantiomerTest(unittest.TestCase):
    """No alias may map a name onto its single-enantiomer form (the header rule)."""
    PREFIXES = ("es", "dex", "lev", "ar", "(s)-", "(r)-", "(+)-", "(-)-")

    def test_no_alias_onto_an_enantiomer(self):
        bad = [(ours, theirs) for ours, theirs in gk._RAW_ALIASES.items()
               for p in self.PREFIXES
               if theirs.lower() == p + ours.lower()]
        self.assertFalse(bad, "aliasing a racemate onto one enantiomer leaks its assays")


if __name__ == "__main__":
    unittest.main()
