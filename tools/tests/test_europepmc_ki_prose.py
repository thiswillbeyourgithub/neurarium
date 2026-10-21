#!/usr/bin/env python
"""Unit tests for fetch_europepmc's ``--ki-prose`` citation follower (stdlib, offline).

    python -m unittest discover -t tools/tests -s tools/tests -p test_europepmc_ki_prose.py

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fetch"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sourcing"))
import fetch_europepmc as E  # noqa: E402
import apply_ki_prose as A  # noqa: E402

# A trimmed MediaWiki render: the note ids come HTML-escaped on the <li> and plain on the
# link, the shape that once made every citation miss.
HTML = """
<p>In 2020, viloxazine was reported to have affinity for the serotonin 5-HT<sub>2B</sub>
receptor (K<sub>i</sub> = 3,900&#160;nM).<sup class="reference"><a href="#cite_note-Yu_2020-23">[23]</a></sup></p>
<p>Viloxazine is a morpholine derivative.<sup class="reference"><a href="#cite_note-Old-2">[2]</a></sup></p>
<p>It inhibits CYP1A2 with an IC<sub>50</sub> of 40&#160;nM.<sup class="reference"><a href="#cite_note-Old-2">[2]</a></sup></p>
<ol class="references">
<li id="cite&#95;note-Old-2"><cite>Old. <a href="https://pubmed.ncbi.nlm.nih.gov/111">111</a></cite></li>
<li id="cite&#95;note-Yu&#95;2020-23"><cite>Yu C. <a href="https://pubmed.ncbi.nlm.nih.gov/32943948">32943948</a></cite></li>
</ol>
"""


class CitedAffinityTest(unittest.TestCase):
    def test_follows_escaped_note_ids_to_the_pmid(self):
        got = E.cited_affinity_pmids(HTML)
        self.assertEqual([pm for _, pm in got], [["32943948"]])
        self.assertIn("K i = 3,900 nM", got[0][0])

    def test_a_functional_potency_is_not_an_affinity(self):
        self.assertFalse(E.states_affinity("an IC 50 of 40 nM"))
        self.assertTrue(E.states_affinity("trazodone (KD = 324 microM)"))
        self.assertTrue(E.states_affinity("5-HT1A (pKi = 7.72)"))


# A trimmed JATS full text: a paragraph with inline math, a table nested in a section.
JATS = """<?xml version="1.0"?>
<article><front><abstract><p>Not repeated.</p></abstract></front><body>
<sec><title>Results</title>
<p>Viloxazine bound <italic>NET</italic> (<inline-formula><tex-math>\\alpha</tex-math></inline-formula>).</p>
<table-wrap><label>Table 3</label><caption><p>Ki Values of 3900 and 6400 nM</p></caption>
<table><thead><tr><th>Dose</th><th>5-HT2B</th></tr></thead>
<tbody><tr><td>100</td><td>81.4</td></tr></tbody></table>
<table-wrap-foot><p>Values in nM.</p></table-wrap-foot></table-wrap>
</sec></body><back><ref-list><ref>Ref.</ref></ref-list></back></article>"""


class FullTextTest(unittest.TestCase):
    def test_flattens_body_and_tables_like_the_wikipedia_pages(self):
        self.assertEqual(E.full_text_lines(JATS), [
            "### Results", "Viloxazine bound NET ().", "",
            "Table 3: Ki Values of 3900 and 6400 nM",
            "Dose | 5-HT2B", "100 | 81.4", "Notes: Values in nM."])

    def test_only_an_open_access_record_has_a_licence(self):
        self.assertEqual(E.licence_of({"isOpenAccess": "Y", "pmcid": "PMC1",
                                       "license": "cc by-nc"}), "CC BY-NC")
        self.assertIsNone(E.licence_of({"isOpenAccess": "N", "license": "cc by"}))

    def test_full_text_goes_after_the_abstract(self):
        # An abstract quote gated before the full text existed must still gate after.
        rec = {"title": "T", "pmid": "1", "pmcid": "PMC1", "isOpenAccess": "Y",
               "license": "cc by", "abstractText": "First. Second."}
        page = E.page_text(rec, ["Body."])
        self.assertLess(page.index("Second."), page.index(E.FULL_TEXT_MARKER))
        self.assertIn("licence: CC BY", page)

    def test_table_rows_are_offered_with_their_caption(self):
        page = "# T\n\nAbstract.\n\n" + E.FULL_TEXT_MARKER + "\n\n" + \
            "\n".join(E.full_text_lines(JATS))
        got = E.affinity_candidates(page)
        self.assertIn({"line": "Table 3: Ki Values of 3900 and 6400 nM"}, got)
        self.assertIn("100 | 81.4", [c["line"] for c in got])


class KiProseGateTest(unittest.TestCase):
    CAND = {"page": "1", "line": "Table 3: Ki Values of 630, 3900 and 6400 nM for NET"}
    PAGE = "# T\n\n" + CAND["line"] + "\n"

    def pick(self, **kw):
        return {"target": "5ht2b", "candidate": 0, "param": "Ki", "value_nm": 3900,
                "quote": "Ki Values of 630, 3900 and 6400 nM", **kw}

    def test_a_correct_pick_passes(self):
        self.assertIsNone(A.check_pick(self.pick(), self.CAND, self.PAGE, {"5ht2b"}))

    def test_a_value_not_written_in_the_quote_fails(self):
        self.assertIn("not written", A.check_pick(self.pick(value_nm=3800), self.CAND,
                                                   self.PAGE, {"5ht2b"}))

    def test_a_micromolar_value_converts_to_nm(self):
        cand = {"page": "1", "line": "Ki values at NMDA receptors were 0.97±0.1 μM"}
        page = "# T\n\n" + cand["line"] + "\n"
        ok = self.pick(quote=cand["line"], value_nm=970, unit="μM", stated_value=0.97)
        self.assertIsNone(A.check_pick(ok, cand, page, {"5ht2b"}))
        self.assertIn("does not convert", A.check_pick({**ok, "value_nm": 0.97}, cand, page,
                                                       {"5ht2b"}))
        self.assertIn("unit", A.check_pick({**ok, "unit": "mM"}, cand, page, {"5ht2b"}))
        self.assertIn("unit pM is not written", A.check_pick(
            {**ok, "unit": "pM", "value_nm": 0.00097}, cand, page, {"5ht2b"}))

    def test_a_potency_is_not_an_affinity(self):
        self.assertIn("not an affinity", A.check_pick(self.pick(param="IC50"), self.CAND,
                                                       self.PAGE, {"5ht2b"}))

    def test_a_binding_that_already_has_a_ki_is_never_overwritten(self):
        self.assertIn("Ki-less", A.check_pick(self.pick(), self.CAND, self.PAGE, set()))

    def test_a_quote_off_the_page_fails(self):
        self.assertIn("not found", A.check_pick(self.pick(), self.CAND, "# T\n", {"5ht2b"}))

    def test_a_full_text_quote_carries_the_licence(self):
        page = "# T\nlicence: CC BY-NC\n\nAbstract.\n\n## Full text\n\n" + \
            self.CAND["line"] + "\n"
        ki = A.ki_object(self.pick(), self.CAND, page)
        self.assertEqual(ki["source"]["licence"], "CC BY-NC")
        self.assertEqual(ki["source"]["extraction"], "llm")


class MetaboliteSectionTest(unittest.TestCase):
    """The pass reaches active metabolites too: a metabolite binding left Ki-less by
    PDSP / GtoPdb / Wikipedia (norketamine at NMDA) is offered from its OWN article and
    written into the metabolite store, under the same gates as a drug's."""

    def test_ki_less_keeps_this_pass_own_ki_as_missing(self):
        self.assertEqual(E.ki_less([
            {"target": "nmda"},
            {"target": "d2", "ki": {"source": {"corpus": "pdsp_ki"}}},
            {"target": "m1", "ki": {"source": {"corpus": "europepmc"}}}]), ["m1", "nmda"])

    def test_apply_section_writes_a_gated_metabolite_ki(self):
        from pipeline.judged import qid, text_of
        line = "The Ki values of norketamine at NMDA receptors were 0.97 μM."
        cand = {"corpus": "europepmc", "page": "1", "line": line}
        records = [{"id": "norketamine",
                    "bindings": [{"target": "nmda"}, {"target": "nachr_a7"}]}]
        work = {"norketamine": {"missing": {"nmda": "NMDA"}, "candidates": [cand]}}

        def pick(target, value, **kw):
            return {"target": target, "candidate": 0, "qid": qid(text_of(cand)),
                    "quote": line, "value_nm": value, "param": "Ki", **kw}

        old = A.page_of
        A.page_of = lambda c: "# T\n\n" + line + "\n"
        self.addCleanup(setattr, A, "page_of", old)
        # 970 is not written in "0.97 μM" without its unit; nachr_a7 was never missing.
        self.assertEqual(A.apply_section(records, work, {"norketamine": [
            pick("nmda", 970), pick("nachr_a7", 970, unit="μM", stated_value=0.97)]}), (0, 2))
        self.assertEqual(A.apply_section(records, work, {"norketamine": [
            pick("nmda", 970, unit="μM", stated_value=0.97)]}), (1, 0))
        self.assertEqual(records[0]["bindings"][0]["ki"]["median"], 970.0)
        self.assertEqual(records[0]["bindings"][0]["ki"]["source"]["corpus"], "europepmc")
        self.assertNotIn("ki", records[0]["bindings"][1])


class PageOfTest(unittest.TestCase):
    """A judged pick's page id is untrusted: a path-like one reads nothing."""

    def test_path_like_page_reads_nothing(self):
        import tempfile
        old = A.PAGES_DIR
        with tempfile.TemporaryDirectory() as tmp:
            pages = Path(tmp) / "pages"
            pages.mkdir()
            (pages / "123.md").write_text("abstract", "utf-8")
            (Path(tmp) / "SECRET.md").write_text("outside the corpus", "utf-8")
            try:
                A.PAGES_DIR = pages
                self.assertEqual(A.page_of({"page": "123"}), "abstract")
                self.assertEqual(A.page_of({"page": "../SECRET"}), "")
                self.assertEqual(A.page_of(None), "")
            finally:
                A.PAGES_DIR = old


if __name__ == "__main__":
    unittest.main()
