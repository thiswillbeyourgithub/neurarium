"""check_data family 5's coverage sweeps (``checks/sources/sweep.py``) gate EVERY corpus.

Every corpus ``SOURCE_CORPORA`` gives a ``pages_dir`` is enumerated off the registry
(no hand list), handed a synthetic page tree, and fed one true and one corrupted quote,
both through the quote table and through a committed cache: each corrupted quote must
be one error naming its corpus. So a corpus added later is covered with no edit here,
and a quote no node walk visits (the stale Allen cache entries this guard was written
for) cannot pass unseen.

Built with the help of Claude Code.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks.common import Report  # noqa: E402
from checks.sources.gate import QuoteGate  # noqa: E402
from checks.sources.sweep import sweep_committed_caches, sweep_quote_table  # noqa: E402
from data_generators.corpora import SOURCE_CORPORA  # noqa: E402

PAGED = sorted(c for c, e in SOURCE_CORPORA.items() if e.get("pages_dir"))
TRUE = "The receptor is expressed in the human frontal cortex."
FALSE = "The receptor is expressed in the human cerebellum only."


class SweepEveryCorpusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for corpus in PAGED:
            tree = self.root / SOURCE_CORPORA[corpus]["pages_dir"]
            tree.mkdir(parents=True, exist_ok=True)
            (tree / "p1.md").write_text(f"# Header\n{TRUE}\n", encoding="utf-8")
        self.meta = {"source_corpora": {c: dict(e) for c, e in SOURCE_CORPORA.items()}}

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self):
        return QuoteGate(Report(), self.meta, root=self.root)

    def run_sweep(self, fn, *args):
        gate = self.gate()
        out = io.StringIO()
        with redirect_stdout(out):
            found = fn(gate, *args)
        return gate, found, out.getvalue()

    def errors_per_corpus(self, text):
        return {c: sum(f"verbatim on {c} p." in ln for ln in text.splitlines())
                for c in PAGED}

    def test_registry_has_paged_corpora(self):
        self.assertGreater(len(PAGED), 10)

    def test_quote_table_corrupted_quote_fails_in_every_corpus(self):
        table = {}
        for c in PAGED:
            table[f"q_ok_{c}"] = {"corpus": c, "page": "p1", "quote": TRUE}
            table[f"q_bad_{c}"] = {"corpus": c, "page": "p1", "quote": FALSE}
        gate, found, text = self.run_sweep(sweep_quote_table, table)
        self.assertEqual(found, len(PAGED))
        self.assertEqual(gate.report.errors, len(PAGED))
        self.assertEqual(self.errors_per_corpus(text), {c: 1 for c in PAGED})

    def test_cache_corrupted_quote_fails_in_every_corpus(self):
        cache = self.root / "tools" / "generated_cache"
        cache.mkdir(parents=True)
        payload = {"targets": {c: {"frontal": [{"corpus": c, "page": "p1", "quote": TRUE},
                                               {"corpus": c, "page": "p1", "quote": FALSE}]}
                               for c in PAGED}}
        (cache / "location_sources.json").write_text(json.dumps(payload), "utf-8")
        gate, found, text = self.run_sweep(sweep_committed_caches)
        self.assertEqual(found, len(PAGED))
        self.assertEqual(self.errors_per_corpus(text), {c: 1 for c in PAGED})

    def test_missing_page_on_present_tree_is_an_error(self):
        c = PAGED[0]
        for page in ("p2", "../../README"):
            gate, _, text = self.run_sweep(
                sweep_quote_table, {"q": {"corpus": c, "page": page, "quote": TRUE}})
            self.assertEqual(gate.report.errors, 1, page)
            self.assertIn("page file missing", text)

    def test_absent_tree_is_skipped_and_warned_not_failed(self):
        c = PAGED[0]
        self.meta["source_corpora"][c]["pages_dir"] = "nowhere/pages"
        gate, found, _ = self.run_sweep(
            sweep_quote_table, {"q": {"corpus": c, "page": "p1", "quote": FALSE}})
        self.assertEqual((gate.report.errors, found), (0, 0))
        self.assertIn(c, gate.skipped_corpora)


if __name__ == "__main__":
    unittest.main()
