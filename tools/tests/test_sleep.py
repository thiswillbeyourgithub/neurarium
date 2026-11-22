"""``drug_sleep``: the vocabulary gate, the fetcher's drug-name rule and the generator's
animal-evidence flag and exclusive pairs (shared ``DrugEffectKind``).

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_sleep.py``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "fetch"))
from data_generators import sleep as S  # noqa: E402
from data_generators.drug_effect_kinds import KINDS  # noqa: E402
import fetch_sleep as F  # noqa: E402


class VocabularyTest(unittest.TestCase):
    def test_monti_rems_spelling_counts_as_rem(self):
        line = "buspirone administration increased W, prolonged REMS latency, and reduced REMS time"
        self.assertTrue(S.KIND.says("rem_suppression", line))
        self.assertTrue(S.KIND.says("rem_latency_increase", line))

    def test_an_effect_needs_its_own_words(self):
        self.assertTrue(S.KIND.says("sws_increase", "ketanserin induced an increase of SWS"))
        self.assertFalse(S.KIND.says("sws_increase", "ketanserin reduced REM sleep"))
        self.assertTrue(S.KIND.says("restless_legs", "may induce restless legs syndrome"))
        self.assertFalse(S.KIND.says("nightmares", "may induce restless legs syndrome"))

    def test_registry_order_puts_sleep_before_seizure(self):
        self.assertEqual([k.field for k in KINDS], ["sleep", "seizure_threshold"])


class FetcherTest(unittest.TestCase):
    DRUGS = [{"id": "mirtazapine", "name": "Mirtazapine"},
             {"id": "paroxetine", "name": "Paroxetine"}]
    SENTENCES = [(4, "Mirtazapine induces somnolence in 54% of patients."),
                 (4, "SSRIs strongly suppress REM sleep and lengthen REM latency."),
                 (5, "Paroxetine is a potent inhibitor of CYP2D6."),
                 (5, "Paroxetine 20 mg suppresses REM sleep.")]

    def build(self):
        return F.build(self.DRUGS, sentences=lambda key: self.SENTENCES, paper_keys=["p"])

    def test_only_sleep_sentences_naming_the_drug_are_offered(self):
        wl = self.build()
        self.assertEqual(sorted(wl), ["mirtazapine", "paroxetine"])
        self.assertEqual([c["quote"] for c in wl["paroxetine"]["candidates"]],
                         ["Paroxetine 20 mg suppresses REM sleep."])
        c = wl["mirtazapine"]["candidates"][0]
        self.assertEqual((c["index"], c["corpus"], c["page"], c["pdf_page"]),
                         (0, "papers", "p", 4))

    def test_a_class_sentence_reaches_no_drug(self):
        quotes = [c["quote"] for v in self.build().values() for c in v["candidates"]]
        self.assertNotIn(self.SENTENCES[1][1], quotes)


def _src(species=None):
    s = {"corpus": "papers", "page": "monti2011", "quote": "q", "provenance": "verified"}
    if species:
        s["species"] = species
    return s


class GeneratorTest(unittest.TestCase):
    @staticmethod
    def nodes(rows):
        return S.KIND.drug_nodes("d", lambda srcs, what: srcs, {"drugs": {"d": rows}})

    def test_rat_only_node_carries_the_animal_flag(self):
        out = self.nodes([{"effect": "sws_increase", "sources": [_src("rat")]}])["sleep"]
        self.assertEqual(out[0]["uncertainty"][0]["kind"], "animal_evidence")

    def test_one_human_source_clears_the_flag(self):
        out = self.nodes([{"effect": "sws_increase",
                           "sources": [_src("rat"), dict(_src(), quote="q2")]}])["sleep"]
        self.assertNotIn("uncertainty", out[0])

    def test_opposite_rem_effects_are_refused(self):
        with self.assertRaises(ValueError):
            self.nodes([{"effect": "rem_suppression", "sources": [_src()]},
                        {"effect": "rem_increase", "sources": [_src()]}])


if __name__ == "__main__":
    unittest.main()
