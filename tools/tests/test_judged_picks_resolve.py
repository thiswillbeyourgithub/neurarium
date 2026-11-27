"""Every committed judged pick still resolves onto the worklist its fetcher builds TODAY.

A judged file answers by ``{index, qid}`` into a worklist, and its applier re-builds that
worklist fresh on each run (``fetch_*.build()``) and refuses a pick whose qid no longer
matches. So when a corpus page is rewritten (the French RCP pages on 2026-11-22 split each
sub-heading off its line), the candidates shift, and the next unscoped applier run silently
drops the nodes whose picks went stale, although the committed worklist, built before the
rewrite, still agrees with the judged file. Checking the judged file against the committed
worklist therefore proves nothing: this test resolves it against a fresh ``build()``.

A failure names each stale pick; fix it by re-mapping the pick onto the new candidate that
carries the same quote (and re-judging any re-anchored citation), never by editing qids.

Author-side: skipped on a clone lacking ``data_sources/``. ``SLOW`` builds (tens of seconds)
run only with ``NEURARIUM_SLOW_TESTS=1``, as in ``test_cache_reproducible``.

Built with the help of Claude Code.
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
from lib import worklist_io  # noqa: E402
from pipeline.judged import resolve  # noqa: E402

CACHE = ROOT / "tools" / "generated_cache"

# fetcher module (tools/fetch/<name>.py, exposing build()) -> judged file of
# ``{drug: [{index, qid, ...}]}`` its applier gates against that build.
FAST = {
    "fetch_seizure_threshold": "seizure_threshold_judged.json",
    "fetch_workup": "workup_judged.json",
    "fetch_sleep": "sleep_judged.json",
}
SLOW = {
    "fetch_excretion": "excretion_judged.json",
}


def stale_picks(judged: dict, offered: dict) -> list[str]:
    """One message per pick that does not resolve onto ``offered`` (a fresh build)."""
    out = []
    for did, picks in sorted(judged.items()):
        if did.startswith("_") or not picks:
            continue
        cands = (offered.get(did) or {}).get("candidates")
        if cands is None:
            out.append(f"{did}: fetcher no longer offers this drug")
            continue
        for p in picks:
            _, why = resolve(cands, p)
            if why:
                out.append(f"{did}[{p.get('index')}]: {why}")
    return out


class StalePicksTest(unittest.TestCase):
    def test_a_shifted_candidate_is_reported(self):
        from pipeline.judged import qid
        cands = [{"index": 0, "quote": "Heading Alpha lowers it."}]
        judged = {"x": [{"index": 0, "qid": qid("Heading Alpha lowers it.")}]}
        self.assertEqual(stale_picks(judged, {"x": {"candidates": cands}}), [])
        shifted = [{"index": 0, "quote": "Other."}, {"index": 1, "quote": "Alpha lowers it."}]
        self.assertEqual(len(stale_picks(judged, {"x": {"candidates": shifted}})), 1)
        self.assertEqual(stale_picks(judged, {}), ["x: fetcher no longer offers this drug"])


@unittest.skipUnless((ROOT / "data_sources").is_dir(), "author-side: needs data_sources/")
class JudgedPicksResolveTest(unittest.TestCase):
    def check(self, table: dict) -> None:
        for script, judged_name in table.items():
            with self.subTest(script=script):
                offered = importlib.import_module(script).build()
                judged = worklist_io.read(CACHE / judged_name)
                self.assertEqual(stale_picks(judged, offered), [])

    def test_every_pick_resolves_on_a_fresh_build(self):
        self.check(FAST)

    @unittest.skipUnless(os.environ.get("NEURARIUM_SLOW_TESTS") == "1", "set NEURARIUM_SLOW_TESTS=1")
    def test_slow_passes_resolve_on_a_fresh_build(self):
        self.check(SLOW)


if __name__ == "__main__":
    unittest.main()
