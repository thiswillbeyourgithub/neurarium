"""Re-running an applier on the committed data must change nothing (the pipeline is a fixpoint).

``apply_formulations.py`` moves a release-specific claim (a brand, a Tmax, a T½) off the
molecule onto ``formulations[]``. Every molecule-level applier of that claim once re-added it
on a re-run (``apply_tmax.py`` put 78 per-release Tmax back, the brand appliers 94 brands),
because each looked only at the molecule. They now all ask
``data_generators.formulations.placed``; this test re-runs each one for real against a scratch
copy of ``drugs_data.jsonl`` + ``metabolites_data.jsonl`` and requires the bytes unchanged.

``apply_pharmacokinetics.py`` is checked more weakly: its Stahl judged file predates later
passes that re-picked some drugs' T½ (its ``--only`` help says a full re-run is not a no-op),
so it must only never re-add a claim a formulation holds.

Author-side: skipped on a clone without ``data_sources/``. Slow (each applier re-derives its
worklist), so it runs only with ``NEURARIUM_SLOW_TESTS=1``.

Built with the help of Claude Code.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for sub in ("tools", "tools/fetch", "tools/sourcing"):
    sys.path.insert(0, str(ROOT / sub))

from lib import drugs_io  # noqa: E402
from data_generators import formulations as F  # noqa: E402

# (applier module, argv) pairs that must leave the committed data byte-identical.
STRICT = [
    ("apply_formulations", []),
    ("apply_tmax", []),
    ("apply_half_life", []),
    ("apply_brand_sources", []),
    ("apply_brand_names", []),
    ("apply_brand_names", ["--bdpm"]),
    ("apply_metabolite_bindings", []),
]
# Appliers that may legitimately rewrite other drugs but must never re-add a placed claim.
NO_RELOCATED_CLAIM = [("apply_pharmacokinetics", [])]


def rerun(module: str, argv: list[str], tmp: Path) -> tuple[bytes, list[dict]]:
    """Run ``module.main()`` with ``argv`` against scratch copies.

    Returns (drugs + metabolites bytes, drugs)."""
    drugs, mets = tmp / "drugs_data.jsonl", tmp / "metabolites_data.jsonl"
    shutil.copy(drugs_io.DRUGS_PATH, drugs)
    shutil.copy(drugs_io.METABOLITES_PATH, mets)
    saved = drugs_io.DRUGS_PATH, drugs_io.METABOLITES_PATH, sys.argv
    drugs_io.DRUGS_PATH, drugs_io.METABOLITES_PATH = drugs, mets
    sys.argv = [module, *argv]
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with contextlib.suppress(SystemExit):
                importlib.import_module(module).main()
    finally:
        drugs_io.DRUGS_PATH, drugs_io.METABOLITES_PATH, sys.argv = saved
    return drugs.read_bytes() + mets.read_bytes(), drugs_io.load_drugs(drugs)


def relocated_on_molecule(drugs: list[dict]) -> list[str]:
    """``drug: field`` for every molecule-level claim a formulation of that drug also holds."""
    out = []
    for d in drugs:
        names = {b.get("name") for b in F.placed(d, "brands")}
        if names & {b.get("name") for b in d.get("brands") or []}:
            out.append(f"{d['id']}: brands")
        for field in ("tmax", "half_life"):
            if d.get(field) and F.placed(d, field):
                out.append(f"{d['id']}: {field}")
    return out


@unittest.skipUnless((ROOT / "data_sources").is_dir(), "author-side: needs data_sources/")
@unittest.skipUnless(os.environ.get("NEURARIUM_SLOW_TESTS") == "1",
                     "slow: set NEURARIUM_SLOW_TESTS=1")
class ApplierFixpointTest(unittest.TestCase):

    def setUp(self):
        # Inside the repo: some appliers print the path they wrote relative to it.
        self._tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".fixpoint_")
        self.tmp = Path(self._tmp.name)
        self.committed = (drugs_io.DRUGS_PATH.read_bytes()
                          + drugs_io.METABOLITES_PATH.read_bytes())

    def tearDown(self):
        self._tmp.cleanup()

    def test_strict_appliers_change_nothing(self):
        for module, argv in STRICT:
            with self.subTest(applier=" ".join([module, *argv])):
                got, drugs = rerun(module, argv, self.tmp)
                self.assertEqual(relocated_on_molecule(drugs), [])
                self.assertTrue(got == self.committed,
                                f"{module} {argv} rewrote drugs_data.jsonl or "
                                f"metabolites_data.jsonl on a re-run")

    def test_no_applier_re_adds_a_placed_claim(self):
        for module, argv in NO_RELOCATED_CLAIM:
            with self.subTest(applier=module):
                self.assertEqual(relocated_on_molecule(rerun(module, argv, self.tmp)[1]), [])


if __name__ == "__main__":
    unittest.main()
