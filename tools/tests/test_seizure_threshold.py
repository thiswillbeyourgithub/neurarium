"""``drug_seizure_threshold``: the vocabulary gate, the fetcher's withdrawal run and name
matching, the applier's gate and the generator's validation.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_seizure_threshold.py``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "fetch"))
sys.path.insert(0, str(TOOLS / "sourcing"))
from data_generators import seizure_threshold as S  # noqa: E402
import fetch_seizure_threshold as F  # noqa: E402
import apply_seizure_threshold as A  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402
from pipeline.judged import qid  # noqa: E402


class VocabularyTest(unittest.TestCase):
    def test_lowers_needs_a_seizure_word(self):
        self.assertTrue(S.says("lowers", "Le méthylphénidate peut abaisser le seuil épileptogène."))
        self.assertTrue(S.says("lowers", "bupropion IR was associated with higher seizure incidence"))
        self.assertFalse(S.says("lowers", "Des crises hypertensives ont été rapportées."))

    def test_withdrawal_needs_seizures_and_stopping(self):
        self.assertTrue(S.says("withdrawal", "L'arrêt brutal peut précipiter les crises convulsives."))
        self.assertFalse(S.says("withdrawal", "Des convulsions ont été rapportées."))
        self.assertFalse(S.says("withdrawal", "Le traitement doit être arrêté progressivement."))

    def test_raises_needs_an_anticonvulsant_word(self):
        self.assertTrue(S.says("raises", "L'effet antiépileptique du clonazépam peut diminuer."))
        self.assertFalse(S.says("raises", "Des convulsions ont été rapportées."))
        self.assertFalse(S.says("nonsense", "convulsions"))


class FetcherTest(unittest.TestCase):
    LINES = [{"line": "Cet état peut entraîner à l'arrêt du traitement un phénomène de sevrage.",
              "item": False, "section": "4.4", "under": ""},
             {"line": "Certains symptômes sont fréquents : insomnie, céphalées.",
              "item": False, "section": "4.4", "under": ""},
             {"line": "D'autres symptômes sont plus rares : hallucinations, convulsions.",
              "item": False, "section": "4.4", "under": ""}]

    def page(self, lines):
        return normalize_for_match("\n".join(ln["line"] for ln in lines))

    def test_withdrawal_line_quotes_its_context(self):
        run = F._with_stopping_context(self.LINES, 2, self.page(self.LINES))
        self.assertTrue(run.startswith("Cet état"))
        self.assertTrue(S.says("withdrawal", run))

    def test_no_run_off_the_page_or_through_an_item(self):
        # Not verbatim on the page (a heading sat between): the bare line.
        self.assertEqual(F._with_stopping_context(self.LINES, 2, "unrelated text"),
                         self.LINES[2]["line"])
        items = [dict(ln, item=(i == 1)) for i, ln in enumerate(self.LINES)]
        self.assertEqual(F._with_stopping_context(items, 2, self.page(items)), items[2]["line"])

    def test_a_shared_name_is_never_matched(self):
        pats = F._name_patterns([{"id": "methylphenidate_dl", "name": "Methylphenidate (D,L)"},
                                 {"id": "methylphenidate_d", "name": "Methylphenidate (D)"},
                                 {"id": "clozapine", "name": "Clozapine"}])
        self.assertEqual(set(pats), {"clozapine"})
        self.assertTrue(pats["clozapine"].search("chlorpromazine and clozapine among"))


class _Pages:
    def __init__(self, ok=True):
        self.ok = ok

    def on_page(self, corpus, page, line):
        return self.ok


class GateTest(unittest.TestCase):
    LINE = "Des convulsions ont été rapportées chez des patients recevant de la loxapine."

    def offered(self):
        return {"loxapine": {"candidates": [{"index": 0, "corpus": "bdpm_rcp", "page": "1",
                                             "quote": self.LINE, "qid": qid(self.LINE)}]}}

    def test_accepts_a_matching_pick(self):
        out, rej = A.gate({"loxapine": [{"index": 0, "qid": qid(self.LINE), "effect": "lowers"}]},
                          self.offered(), {"loxapine"}, _Pages())
        self.assertEqual(rej, [])
        self.assertEqual(out["loxapine"][0]["effect"], "lowers")

    def test_refuses_what_the_line_does_not_say(self):
        for effect in ("withdrawal", "raises", "made_up"):
            out, rej = A.gate({"loxapine": [{"index": 0, "qid": qid(self.LINE), "effect": effect}]},
                              self.offered(), {"loxapine"}, _Pages())
            self.assertEqual(out, {})
            self.assertEqual(len(rej), 1, effect)

    def test_refuses_a_stale_qid_and_an_off_page_quote(self):
        _, rej = A.gate({"loxapine": [{"index": 0, "qid": "deadbeef", "effect": "lowers"}]},
                        self.offered(), {"loxapine"}, _Pages())
        self.assertIn("qid mismatch", rej[0])
        _, rej = A.gate({"loxapine": [{"index": 0, "qid": qid(self.LINE), "effect": "lowers"}]},
                        self.offered(), {"loxapine"}, _Pages(ok=False))
        self.assertIn("not found", rej[0])


class GeneratorTest(unittest.TestCase):
    def emit(self, rows):
        return S.drug_seizure_threshold("x", lambda s, what: s, {"drugs": {"x": rows}})

    def test_orders_by_vocabulary(self):
        src = [{"quote": "q"}]
        out = self.emit([{"effect": "withdrawal", "sources": src}, {"effect": "lowers", "sources": src}])
        self.assertEqual([r["effect"] for r in out["seizure_threshold"]], ["lowers", "withdrawal"])
        self.assertEqual(self.emit([]), {})

    def test_refuses_a_bad_cache(self):
        with self.assertRaises(KeyError):
            self.emit([{"effect": "worsens", "sources": [{"quote": "q"}]}])
        with self.assertRaises(ValueError):
            self.emit([{"effect": "lowers", "sources": []}])
        with self.assertRaises(ValueError):
            self.emit([{"effect": "lowers", "sources": [{"quote": "q"}]}] * 2)


if __name__ == "__main__":
    unittest.main()
