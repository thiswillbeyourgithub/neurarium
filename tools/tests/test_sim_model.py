"""Run the simulation-model JS unit tests (tools/tests/sim_model.test.mjs) from the
Python suite, so `python -m unittest discover tools/tests` covers the maths behind
the Simulation tab (public/js/sim-model.js) without a JS test runner of its own.
Skipped when `node` is not on PATH (the site has no JS toolchain requirement).
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SimModelJsTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_node_suite_passes(self):
        proc = subprocess.run(
            ["node", "--test", str(ROOT / "tools/tests/sim_model.test.mjs")],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
