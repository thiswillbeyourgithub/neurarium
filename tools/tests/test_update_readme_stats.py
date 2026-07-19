#!/usr/bin/env python
"""Test harness guarding tools/update_readme_stats.py's chart rendering.

Stdlib unittest only (no deps). Runnable directly:
``python tools/tests/test_update_readme_stats.py``, or pytest-discoverable.

The SOURCING_STATS block is a fenced, monospace per-kind coverage chart. A prior
regression left the ``chart`` rows computed but never inserted into the block, so
the fence opened, stayed empty, and was never closed (the whole table silently
vanished from the README). These tests lock the invariants that catch that: the
rendered block carries bar rows, the code fence is balanced, and each emitted node
kind appears exactly once.
"""
import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
META = REPO_ROOT / "public" / "data" / "meta.json"
TOOL = REPO_ROOT / "tools" / "update_readme_stats.py"

_spec = importlib.util.spec_from_file_location("update_readme_stats", TOOL)
_urs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_urs)


class ChartRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stats = json.loads(META.read_text(encoding="utf-8"))["provenance_stats"]
        cls.block = _urs.render_block(stats)
        cls.stats = stats

    def test_chart_bars_present(self):
        """The block must contain progress-bar rows (the regression blanked them)."""
        self.assertIn("█", self.block, "no filled bar in the rendered chart")

    def test_code_fence_balanced(self):
        """Opening and closing ``` must both be present (the bug left it unclosed)."""
        self.assertEqual(self.block.count("```"), 2,
                         "the SOURCING_STATS code fence is not balanced")

    def test_every_nonempty_kind_has_a_row(self):
        """Each labelled kind with nodes gets exactly one chart row."""
        for kind, label in _urs.KIND_LABELS.items():
            c = self.stats["by_kind"].get(kind)
            if not c or not c["total"]:
                continue
            self.assertEqual(self.block.count(f"{label}  "), 1,
                             f"kind {kind!r} ({label!r}) missing/duplicated in chart")


if __name__ == "__main__":
    unittest.main()
