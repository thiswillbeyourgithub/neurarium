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

    def test_every_EMITTED_kind_has_a_row(self):
        """One row per kind the DATA carries, labelled or not.

        The test above could only ever check the label table against itself, which is
        how three emitted kinds (both density profiles + the enzyme variability) went
        missing from the chart unnoticed: the renderer walked the labels, so a kind with
        no entry was silently dropped while the headline kept counting its nodes. The
        bars then no longer added up to the figure above them.
        """
        emitted = [k for k, c in self.stats["by_kind"].items() if c and c["total"]]
        n_rows = sum(1 for line in self.block.splitlines() if "█" in line or "░" in line)
        self.assertEqual(n_rows, len(emitted),
                         f"{len(emitted)} emitted kind(s) but {n_rows} chart row(s): "
                         f"a kind is missing from (or duplicated in) the chart")

    def test_an_unlabelled_kind_titlecases_rather_than_vanishing(self):
        """A brand-new node kind renders as an ugly row, never as no row at all."""
        stats = {"nodes": {"total": 4, "backed": 2, "pct_backed": 50},
                 "by_kind": {"future_node_kind": {
                     "total": 4, "verified": 2, "uncertain": 0, "sourced": 0,
                     "llm": 0, "nosource": 2, "missing": 2}}}
        self.assertIn("Future node kind", _urs.render_block(stats))


class UncertainCountsAsBackedTest(unittest.TestCase):
    """An ``uncertain`` node is backed: the badge doubts the *attribution* of a
    quote that really was checked, so dropping it from the bar would understate
    the corpus and, worse, make the README disagree with the in-app tally."""

    def _row(self, kind, **counts):
        c = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
             "llm": 0, "nosource": 0, "missing": 0, **counts}
        backed = c["verified"] + c["uncertain"] + c["sourced"]
        nodes = dict(c, backed=backed,
                     pct_backed=round(100 * backed / c["total"]) if c["total"] else 0)
        return {"nodes": nodes, "by_kind": {kind: c}}

    def test_uncertain_fills_the_bar_like_verified(self):
        kind = next(iter(_urs.KIND_LABELS))
        with_unc = _urs.render_block(self._row(kind, total=10, verified=5, uncertain=5))
        all_ver = _urs.render_block(self._row(kind, total=10, verified=10))
        self.assertIn("100%", with_unc)
        self.assertEqual(with_unc.count("░"), all_ver.count("░"))

    def test_a_missing_uncertain_key_is_tolerated(self):
        """Older meta.json snapshots predate the bucket; the tool must not KeyError."""
        kind = next(iter(_urs.KIND_LABELS))
        stats = self._row(kind, total=4, verified=2, missing=2)
        del stats["by_kind"][kind]["uncertain"]
        self.assertIn("50%", _urs.render_block(stats))


if __name__ == "__main__":
    unittest.main()
