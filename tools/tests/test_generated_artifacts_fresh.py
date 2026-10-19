#!/usr/bin/env python
"""Every committed GENERATED artifact matches what its generator writes today.

One test file for the whole inventory, so a new generated file has one obvious place
to join. Each is re-derived offline (stdlib, no network) and diffed against the
committed copy:

* ``public/data/**`` (meta, every ``*.jsonl``, ``quotes.jsonl``, ``changelog.json``,
  ``translations.fr.json``, ``search_names.fr.json``, ``shapes/``) and
  ``public/llms.txt``: one ``generate_data.py --root <tmp>`` run, byte-compared;
* the README.md / README.fr.md generated blocks: ``update_readme_stats.py --check``;
* the baked meshes: ``public/data/meshes/index.json`` records each shape file's
  SHA-256 (re-meshing needs Node), re-hashed by check_data family 11.

Not here, because re-deriving them needs the author-side ``data_sources/`` trees or
the network: ``public/data/molecules/`` (fetched), and the ``tools/generated_cache``
ledgers (``quote_headers.json``, ``fetch_dates.json``, ``page_links.json``, the
worklists). Their quotes are still gated against the pages by check_data family 5.

Also run unskippably by ``tools/git-hooks/pre-push``. Built with the help of Claude Code.
"""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS = REPO_ROOT / "tools"
PUBLIC = REPO_ROOT / "public"
DATA_DIR = PUBLIC / "data"
sys.path.insert(0, str(TOOLS))

from checks.baked_meshes import check_baked_meshes  # noqa: E402
from checks.common import Report, load_jsonl  # noqa: E402


def _rel_files(base):
    """Every regular file under ``base``, as paths relative to ``base``."""
    return {p.relative_to(base) for p in base.rglob("*") if p.is_file()}


def _run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True,
                          text=True, cwd=REPO_ROOT)


class GeneratedArtifactsFreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.proc = _run(TOOLS / "generate_data.py", "--root", cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"generator failed:\n{self.proc.stdout}\n{self.proc.stderr}")

    def test_public_data_byte_identical(self):
        gen_dir = self.root / "data"
        generated = _rel_files(gen_dir)
        # public/data also holds non-generated assets (molecules/, meshes/), so only
        # what the generator emits is compared, but it must emit nothing new.
        missing = generated - _rel_files(DATA_DIR)
        self.assertFalse(missing, f"generator emitted files absent from public/data: "
                                  f"{sorted(map(str, missing))}")
        stale = [str(rel) for rel in sorted(generated)
                 if (gen_dir / rel).read_bytes() != (DATA_DIR / rel).read_bytes()]
        self.assertFalse(stale, f"public/data is stale (run python tools/generate_data.py): "
                                f"{stale}")

    def test_llms_txt(self):
        self.assertEqual((PUBLIC / "llms.txt").read_bytes(),
                         (self.root / "llms.txt").read_bytes(),
                         "public/llms.txt is stale: run python tools/generate_data.py")

    def test_readme_generated_blocks(self):
        proc = _run(TOOLS / "update_readme_stats.py", "--check")
        self.assertEqual(proc.returncode, 0, f"{proc.stderr}run python "
                                             f"tools/update_readme_stats.py")

    def test_baked_meshes_match_their_shapes(self):
        report = Report()
        with redirect_stdout(io.StringIO()) as out:
            check_baked_meshes(report, load_jsonl(report, "structures"))
        self.assertEqual(report.errors, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
