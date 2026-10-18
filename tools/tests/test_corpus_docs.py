#!/usr/bin/env python
"""Doc-drift guard: every SOURCE_CORPORA key is named in CLAUDE.md and docs/PROVENANCE.md.

A corpus added to ``data_generators/corpora.py`` without a mention in the two
docs that list the corpora would leave readers with a stale map. Each key must
appear in backticks (``\\`key\\```) in both files.

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from data_generators.corpora import SOURCE_CORPORA  # noqa: E402

DOCS = ("CLAUDE.md", "docs/PROVENANCE.md")


class CorpusDocsTest(unittest.TestCase):
    def test_every_corpus_key_documented(self):
        for doc in DOCS:
            text = (REPO / doc).read_text(encoding="utf-8")
            missing = [k for k in SOURCE_CORPORA if f"`{k}`" not in text]
            with self.subTest(doc=doc):
                self.assertEqual(missing, [], f"{doc} never names these corpora in backticks")


if __name__ == "__main__":
    unittest.main()
