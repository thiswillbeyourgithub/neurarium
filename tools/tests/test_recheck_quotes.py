#!/usr/bin/env python
"""Unit tests for tools/sourcing/recheck_quotes.py's corpus -> page-dir map.

Stdlib ``unittest`` only (no deps). Runnable directly::

    python tools/tests/test_recheck_quotes.py

pytest-discoverable. The regression guarded here: the map used to be hardcoded in
the script and covered only the six corpora that existed when it was written, so
``build`` died with a ``KeyError`` on the first quote from corpus #9-#12. It now
reads ``meta.source_corpora``, which the generator already emits, and this test
holds the two halves together as new corpora are added.

Built with the help of Claude Code.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "sourcing"))
import recheck_quotes as R  # noqa: E402

CORPORA = json.loads(
    (REPO_ROOT / "public" / "data" / "meta.json").read_text(encoding="utf-8")
)["source_corpora"]


class PageDirTest(unittest.TestCase):

    def test_every_paged_corpus_is_covered(self):
        paged = {name for name, entry in CORPORA.items() if entry.get("pages_dir")}
        self.assertEqual(set(R.PAGE_DIR), paged)
        self.assertGreater(len(paged), 6, "the stale hardcoded map had six entries")

    def test_a_csv_corpus_is_absent_rather_than_pointing_nowhere(self):
        for name, entry in CORPORA.items():
            if entry.get("csv") and not entry.get("pages_dir"):
                self.assertNotIn(name, R.PAGE_DIR)

    def test_each_path_is_the_one_the_registry_states(self):
        for name, path in R.PAGE_DIR.items():
            self.assertEqual(path, CORPORA[name]["pages_dir"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
