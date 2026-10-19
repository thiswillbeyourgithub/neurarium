#!/usr/bin/env python
"""Unit tests for ``tools/sourcing/apply_metabolite_bindings.build_bindings``.

Offline; skipped when ``beautifulsoup4`` is absent (the applier reuses
``fetch_wikipedia_pharmacology``, which imports it at load time)::

    python -m unittest discover -t tools/tests -s tools/tests -p test_apply_metabolite_bindings.py

Built with the help of Claude Code.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
HAS_BS4 = importlib.util.find_spec("bs4") is not None


def _load():
    spec = importlib.util.spec_from_file_location(
        "apply_metabolite_bindings", ROOT / "tools" / "sourcing" / "apply_metabolite_bindings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(HAS_BS4, "beautifulsoup4 not installed")
class CitedCorpusGateTest(unittest.TestCase):
    """A judged pick citing another corpus (a Europe PMC abstract naming the
    transporters the parent's Wikipedia article only calls "monoamine") is gated on
    that page, so the binding keeps a source instead of shipping sourceless (3.114.0)."""

    QUOTE = ("inhibition by its potent metabolites mono-desmethylsibutramine (M1) "
             "and di-desmethylsibutramine (M2).")

    def setUp(self):
        self.m = _load()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pages = Path(tmp.name)
        self.page = pages / "19890256.md"
        self.page.write_text(f"# title\n\nIts effects are mostly attributable to SERT "
                             f"{self.QUOTE}\n", encoding="utf-8")
        # The parent's Wikipedia article never states it, so only the cited page can.
        (pages / "sibutramine.md").write_text("unrelated article text\n", encoding="utf-8")
        gate = self.m.PageGate({"europepmc": pages, "wikipedia_pharm": pages})
        for name, value in (("GATE", gate),
                            ("_pdsp_ki", lambda name, target: None)):
            patcher = mock.patch.object(self.m, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def build(self, quote):
        warnings = []
        judged = {"bindings": [{"target": "sert", "action": "reuptake_inhibitor",
                                "corpus": "europepmc", "page": "19890256", "quote": quote}]}
        out = self.m.build_bindings("Desmethylsibutramine", {"slug": "sibutramine"},
                                    judged, {"sert"}, warnings.append)
        return out, warnings

    def test_cited_page_quote_is_kept_with_its_corpus(self):
        out, warnings = self.build(self.QUOTE)
        self.assertEqual(warnings, [])
        self.assertEqual(out[0]["sources"], [{"corpus": "europepmc", "page": "19890256",
                                              "quote": self.QUOTE, "provenance": "verified"}])

    def test_quote_absent_from_the_cited_page_is_dropped(self):
        out, warnings = self.build("much greater potency as monoamine reuptake inhibitors")
        self.assertEqual(out, [])
        self.assertIn("europepmc page 19890256", warnings[0])


@unittest.skipUnless(HAS_BS4, "beautifulsoup4 not installed")
class OwnArticleStoredTest(unittest.TestCase):
    """Every ``OWN_ARTICLE`` title must be the stored, post-redirect title. The store names
    a page after the resolved title, so a redirect title ("N-Desmethylclozapine" ->
    ``desmethylclozapine.html``) is found online but silently missed by ``--no-fetch``,
    which then falls back to the parent's article and rewrites the worklist entry."""

    def test_every_own_article_resolves_offline(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools" / "fetch"))
        import fetch_metabolite_bindings as mb
        from lib.corpora import wikipedia as wikistore
        from lib.page_file import page_path
        if not Path(wikistore.RAW_DIR).is_dir():
            self.skipTest("author-side: data_sources/wikipedia/raw/ not on this clone")
        missing = {k: t for k, t in mb.OWN_ARTICLE.items()
                   if not Path(page_path(wikistore.RAW_DIR, wikistore.title_slug(t),
                                         ".html")).exists()}
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
