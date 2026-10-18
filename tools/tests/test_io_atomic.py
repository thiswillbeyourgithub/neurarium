#!/usr/bin/env python
"""Unit tests for tools/io_atomic.py: a failed write never truncates the target.

Regression: ``drugs_io.save_drugs`` used ``Path.write_text``, which truncates first,
so an interrupt mid-write left a half-written ``drugs_data.jsonl``.

Built with the help of Claude Code.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import io_atomic  # noqa: E402


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.target = self.dir / "drugs_data.jsonl"
        self.target.write_text("original\n", encoding="utf-8")

    def test_writes_and_leaves_no_temp(self):
        io_atomic.atomic_write_text(self.target, "new\n")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "new\n")
        self.assertEqual([p.name for p in self.dir.iterdir()], ["drugs_data.jsonl"])

    def test_failed_replace_keeps_original(self):
        # The interrupt lands after the temp file is written, before the swap.
        with mock.patch.object(io_atomic.os, "replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                io_atomic.atomic_write_text(self.target, "half")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "original\n")
        self.assertEqual([p.name for p in self.dir.iterdir()], ["drugs_data.jsonl"])

    def test_json_keeps_accents_and_ends_with_newline(self):
        path = self.dir / "sub" / "cache.json"
        io_atomic.atomic_write_json(path, {"fr": "écart"}, indent=1)
        text = path.read_text(encoding="utf-8")
        self.assertIn("écart", text)
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(json.loads(text), {"fr": "écart"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
