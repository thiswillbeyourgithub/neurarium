#!/usr/bin/env python
"""Unit tests for tools/page_file.py: a citation's page never escapes its corpus.

Regression: the applier page gate (``pipeline/gate.PageGate``) and
``provenance.corpus_page_path`` built ``<pages_dir>/<page>.md`` from an LLM-judged
``page`` unchecked, so ``../../README`` resolved outside the corpus tree.

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from lib import page_file  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402
from data_generators.provenance import corpus_page_path  # noqa: E402


class PageFileTest(unittest.TestCase):
    def test_bare_tokens_pass(self):
        for page in (982, "lithium_medication", "EMEA-H-C-123", "69071035", "a.b"):
            self.assertEqual(page_file.page_name(page), str(page))

    def test_path_like_pages_refused(self):
        for page in ("../x", "a/b", "..", ".hidden", "a\\b", "", None, "a b"):
            self.assertIsNone(page_file.page_name(page), page)

    def test_gate_and_registry_refuse_traversal(self):
        gate = PageGate(pages={"stahl": TOOLS})
        self.assertIsNone(gate.text("stahl", "../README"))
        self.assertIsNone(corpus_page_path("bdpm", "../../README"))
        self.assertTrue(str(corpus_page_path("bdpm", "69071035")).endswith(
            "bdpm/pages/69071035.md"))

    def test_read_page_is_raw_and_refuses_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "7.md").write_text("Raw  TEXT, kept.\n", "utf-8")
            self.assertEqual(page_file.read_page(d, 7), "Raw  TEXT, kept.\n")
            self.assertIsNone(page_file.read_page(d, 8))
            self.assertIsNone(page_file.read_page(d, "../7"))
            self.assertIsNone(page_file.read_page(None, 7))

    def test_empty_quote_is_never_on_a_page(self):
        # Regression: "" is a substring of every page, so an empty quote passed.
        gate = PageGate(read=lambda corpus, page: "some page text")
        self.assertFalse(gate.on_page("stahl", 1, ""))
        self.assertFalse(gate.on_page("stahl", 1, "  "))
        self.assertTrue(gate.on_page("stahl", 1, "Page text"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
