#!/usr/bin/env python
"""Unit tests for ``tools/worklist_io.read``, the appliers' one judged / worklist reader.

Stdlib ``unittest`` only, over files in a temp dir::

    python tools/tests/test_worklist_io.py

(The scoped-merge helpers of the same module are tested in ``test_category_sources.py``.)

Built with the help of Claude Code.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import worklist_io  # noqa: E402


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parses_a_present_file_from_str_or_path(self):
        path = self.dir / "judged.json"
        path.write_text(json.dumps({"drugs": {"x": [0]}, "name": "é"}), encoding="utf-8")
        want = {"drugs": {"x": [0]}, "name": "é"}
        self.assertEqual(worklist_io.read(path), want)
        self.assertEqual(worklist_io.read(str(path)), want)
        # A present file ignores the default even when not required.
        self.assertEqual(worklist_io.read(path, required=False, default={}), want)

    def test_missing_required_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            worklist_io.read(self.dir / "absent.json")

    def test_missing_optional_file_returns_the_default(self):
        absent = self.dir / "absent.json"
        self.assertIsNone(worklist_io.read(absent, required=False))
        self.assertEqual(worklist_io.read(absent, required=False, default={}), {})

    def test_corrupt_file_always_raises(self):
        # A truncated judged file must never read as "no picks".
        path = self.dir / "judged.json"
        path.write_text('{"drugs": {"x": [0', encoding="utf-8")
        for required in (True, False):
            with self.assertRaises(json.JSONDecodeError):
                worklist_io.read(path, required=required, default={})


if __name__ == "__main__":
    unittest.main()
