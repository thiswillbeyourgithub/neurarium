"""Molecule images (``tools/fetch/fetch_molecules.py``): a diagram about a molecule (a
synthesis route, a reaction or metabolic scheme) is never taken as its structure, and no
vendored image already is one. Tropatepine once showed its synthesis scheme.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_molecule_images.py``
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS / "fetch"))
sys.path.insert(0, str(TOOLS))
import fetch_molecules as fm  # noqa: E402


class DiagramFilterTest(unittest.TestCase):
    def test_diagrams_refused(self):
        for name in ("Tropatepine synthesis.svg", "Codeine_metabolism.svg",
                     "Serotonin biosynthesis pathway.svg", "Aldol reaction mechanism.svg"):
            self.assertTrue(fm._is_diagram(name), name)

    def test_structures_kept(self):
        for name in ("Tropatepine.svg", "Acamprosate_structure.svg",
                     "Venlafaxine_stereoisomers_labelled.svg", "Diamorphine2DACS3.svg"):
            self.assertFalse(fm._is_diagram(name), name)

    def test_no_vendored_image_is_a_diagram(self):
        sources = json.loads(fm.SOURCES_JSON.read_text(encoding="utf-8"))
        bad = {d: s["file"] for d, s in sources.items() if fm._is_diagram(s["file"])}
        self.assertEqual(bad, {})

    def test_declared_imageless_drug_has_no_image(self):
        """A FILE_OVERRIDES None means no structure SVG: none may be vendored for it."""
        for did, file in fm.FILE_OVERRIDES.items():
            if file is None:
                self.assertFalse((fm.OUT_DIR / f"{did}.svg").exists(), did)


if __name__ == "__main__":
    unittest.main()
