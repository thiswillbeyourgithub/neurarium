"""Every committed ``tools/generated_cache/*.json`` is in its one registered format.

``lib/cache_io.FORMATS`` names each cache's serialization once, and every writer goes
through it. This test holds the committed bytes to it: a writer that drifts (rewrites a
cache in another indent, drops its trailing newline), or a cache nobody registered, fails
here instead of turning a later re-run into a whole-file diff. Plus the regression that
motivated it: a no-op ``demote_quotes`` run must leave every cache byte-identical.

Built with the help of Claude Code.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))

from lib import cache_io  # noqa: E402
import demote_quotes  # noqa: E402

COMMITTED = sorted(cache_io.CACHE_DIR.glob("*.json"))


class CacheFormatTest(unittest.TestCase):

    def test_every_cache_is_registered(self):
        missing = [p.name for p in COMMITTED if p.name not in cache_io.FORMATS]
        self.assertEqual(missing, [], "register these in lib/cache_io.FORMATS")

    def test_no_stale_registration(self):
        names = {p.name for p in COMMITTED}
        self.assertEqual(sorted(set(cache_io.FORMATS) - names), [])

    def test_committed_bytes_equal_registered_writer(self):
        for path in COMMITTED:
            if path.name not in cache_io.FORMATS:
                continue
            with self.subTest(cache=path.name):
                text = path.read_text("utf-8")
                self.assertTrue(cache_io.dumps(path.name, json.loads(text)) == text,
                                f"{path.name} is not in its registered format")

    def test_unregistered_name_raises(self):
        with self.assertRaises(KeyError):
            cache_io.dumps("nope.json", {})

    def test_name_overrides_path_for_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scratch.json"
            cache_io.write(out, {"b": 1, "a": 2}, name="location_sources.json")
            self.assertEqual(out.read_text("utf-8"), '{\n "a": 2,\n "b": 1\n}')


class DemoteNoOpTest(unittest.TestCase):
    """``demote_quotes`` rewrites every quote-bearing cache: with nothing to demote, it
    must write each back byte for byte (it once dropped seven caches' trailing newline)."""

    def test_noop_demote_keeps_every_cache_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "generated_cache"
            cache.mkdir()
            for name in demote_quotes.CACHE_FILES:
                if (cache_io.CACHE_DIR / name).exists():
                    shutil.copy(cache_io.CACHE_DIR / name, cache / name)
            before = {p.name: p.read_bytes() for p in cache.iterdir()}
            self.assertTrue(before)
            argv = ["demote_quotes.py", "--ids", "q-does-not-exist"]
            with mock.patch.object(demote_quotes, "CACHE", str(cache)), \
                    mock.patch.object(demote_quotes, "DRUGS", str(Path(tmp) / "none.jsonl")), \
                    mock.patch.object(demote_quotes, "METABOLITES", str(Path(tmp) / "no.jsonl")), \
                    mock.patch.object(demote_quotes, "emitted_page_dirs", lambda: {}), \
                    mock.patch.object(sys, "argv", argv):
                try:
                    demote_quotes.main()
                except SystemExit:
                    pass
            after = {p.name: p.read_bytes() for p in cache.iterdir()}
            changed = sorted(n for n in before if before[n] != after.get(n))
            self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
