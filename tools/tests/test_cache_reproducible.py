"""An offline fetcher re-run against the current ``data_sources/`` must reproduce its
committed ``tools/generated_cache/`` file byte for byte.

Three ways a committed cache stopped reproducing slipped past every test: a proposals file
whose fetcher filtered on a state its own applier consumes (it re-ran to ``{}``), a
``--no-fetch`` lookup keyed by a redirect title instead of the stored one, and a worklist
never rebuilt after its matching rule changed. Each is caught here the same way: rebuild into
a scratch path, compare with the committed bytes.

Author-side: skipped on a clone without ``data_sources/``. ``FAST`` always runs there;
``SLOW`` (tens of seconds each) runs only with ``NEURARIUM_SLOW_TESTS=1``.

Not listed, because their committed caches are stale today (a rebuild is new data that wants
its own judge pass, not a test edit): ``projection_worklist``, ``receptor_effects``
and ``fetch_metabolite_bindings``.
Add one here once its cache has been refreshed.

Built with the help of Claude Code.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "tools" / "generated_cache"

# fetcher script (tools/fetch/<name>.py) -> the committed cache its default --out writes.
FAST = {
    "fetch_category_worklist": "category_worklist.json",
    "fetch_drug_history": "drug_history_worklist.json",
    "fetch_half_life": "half_life_worklist.json",
    "fetch_originator": "originator_worklist.json",
    "fetch_pharmacokinetics": "pk_worklist.json",
}
SLOW = {
    "fetch_cyp_worklist": "cyp_worklist.json",
    "fetch_formulation_worklist": "formulation_worklist.json",
    "fetch_prodrug_worklist": "prodrug_worklist.json",
    "fetch_classification_worklist": "classification_worklist.json",
    "fetch_binding_direction_tables": "binding_directions_tables.json",
    "fetch_tmax": "tmax_worklist.json",
}


def rebuilt(script: str, out_dir: Path) -> bytes:
    """Run ``script`` offline with ``--out`` in ``out_dir`` and return what it wrote."""
    out = out_dir / f"{script}.json"
    subprocess.run([sys.executable, str(ROOT / "tools" / "fetch" / f"{script}.py"),
                    "--out", str(out)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return out.read_bytes()


@unittest.skipUnless((ROOT / "data_sources").is_dir(), "author-side: needs data_sources/")
class CacheReproducibleTest(unittest.TestCase):

    def check(self, table: dict[str, str]) -> None:
        # Inside the repo: some fetchers print their --out relative to it.
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".repro_") as tmp:
            for script, cache in table.items():
                with self.subTest(script=script):
                    self.assertEqual(rebuilt(script, Path(tmp)), (CACHE / cache).read_bytes(),
                                     f"{script} no longer reproduces {cache}")

    def test_fast_fetchers_reproduce_their_cache(self):
        self.check(FAST)

    @unittest.skipUnless(os.environ.get("NEURARIUM_SLOW_TESTS") == "1",
                         "slow: set NEURARIUM_SLOW_TESTS=1")
    @unittest.skipUnless(importlib.util.find_spec("bs4"), "the table fetcher needs bs4")
    def test_slow_fetchers_reproduce_their_cache(self):
        self.check(SLOW)


if __name__ == "__main__":
    unittest.main()
