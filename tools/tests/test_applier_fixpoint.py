"""Re-running an applier on the committed data must change nothing (the pipeline is a fixpoint).

``apply_formulations.py`` moves a release-specific claim (a brand, a Tmax, a T½) off the
molecule onto ``formulations[]``. Every molecule-level applier of that claim once re-added it
on a re-run (``apply_tmax.py`` put 78 per-release Tmax back, the brand appliers 94 brands),
because each looked only at the molecule. Others clobbered what a later pass wrote
(``apply_metabolite_bindings`` the later directions + GtoPdb Ki, ``apply_pharmacokinetics``
12 drugs' later T½), or only reformatted (a popped key moved to the end, a cache written in
another writer's indent). This test re-runs every offline applier for real, in place, and
requires every byte under ``tools/data/`` and ``tools/generated_cache/`` unchanged; the
snapshot is restored whatever happens. Not here: ``apply_source_quotes`` and
``apply_category_sources`` without ``--wikipedia`` (each needs a results file nothing
commits). ``apply_gtopdb_ki`` only fills what PDSP left empty, so after adding a binding run
``fetch_ki.py --apply --only <drugs>`` first, then it, or this test sees it fill the new row.

Author-side: skipped on a clone without ``data_sources/``. Slow (each applier re-derives its
worklist), so it runs only with ``NEURARIUM_SLOW_TESTS=1``. It rewrites committed files for
the length of one applier run, so do not run it while another session edits them.

Built with the help of Claude Code.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lib import drugs_io  # noqa: E402
from data_generators import formulations as F  # noqa: E402

WATCHED = (ROOT / "tools" / "data", ROOT / "tools" / "generated_cache")

# (applier module, argv) pairs that must leave the committed data byte-identical.
STRICT = [
    ("apply_formulations", []),
    ("apply_tmax", []),
    ("apply_half_life", []),
    ("apply_brand_sources", []),
    ("apply_brand_names", []),
    ("apply_brand_names", ["--bdpm"]),
    ("apply_metabolite_bindings", []),
    ("apply_pharmacokinetics", []),
    ("apply_binding_directions", []),
    ("apply_binding_directions", ["--tables"]),
    ("apply_binding_gaps", []),
    ("apply_binding_sources", []),
    ("apply_category_sources", ["--wikipedia"]),
    ("apply_classification_sources", []),
    ("apply_cyp_sources", []),
    ("apply_demographics", []),
    ("apply_drug_history", []),
    ("apply_drug_holders", []),
    ("apply_drugsfda", []),
    ("apply_expression_density", []),
    ("apply_gtopdb_ki", []),
    ("apply_ki_prose", []),
    ("apply_location_sources", ["--corpus", "allen"]),
    ("apply_location_sources", ["--judged", "data_sources/gtopdb/judged.json"]),
    ("apply_nbn_sources", []),
    ("apply_originator", []),
    ("apply_prodrug", []),
    ("apply_projection_sources", []),
    ("apply_receptor_effects", []),
    ("apply_release_modulation", []),
    ("apply_workup", []),
]


def snapshot() -> dict[Path, bytes]:
    return {p: p.read_bytes() for d in WATCHED for p in d.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


def rerun(module: str, argv: list[str]) -> tuple[int, str, list[str], list[dict]]:
    """Run ``tools/sourcing/<module>.py argv`` in place, then restore every watched file.

    Returns (exit code, output tail, the watched files it changed, the drugs it left)."""
    before = snapshot()
    try:
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "sourcing" / f"{module}.py"),
                            *argv], cwd=ROOT, capture_output=True, text=True, timeout=1800)
        drugs = drugs_io.load_drugs()
        after = snapshot()
    finally:
        for p in set(snapshot()) - set(before):
            p.unlink()
        for p, data in before.items():
            if not p.is_file() or p.read_bytes() != data:
                p.write_bytes(data)
    changed = sorted(str(p.relative_to(ROOT)) for p in set(before) | set(after)
                     if before.get(p) != after.get(p))
    return r.returncode, (r.stdout + r.stderr)[-800:], changed, drugs


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

    def test_strict_appliers_change_nothing(self):
        for module, argv in STRICT:
            with self.subTest(applier=" ".join([module, *argv])):
                code, tail, changed, drugs = rerun(module, argv)
                self.assertEqual(code, 0, f"{module} {argv} failed:\n{tail}")
                self.assertEqual(relocated_on_molecule(drugs), [])
                self.assertEqual(changed, [], f"{module} {argv} rewrote these on a re-run")


if __name__ == "__main__":
    unittest.main()
