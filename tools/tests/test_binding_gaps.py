#!/usr/bin/env python
"""Unit tests for the binding-gap pass: the shared predicates, the fetcher, the applier.

Stdlib ``unittest`` only. Runnable directly::

    python tools/tests/test_binding_gaps.py

``PredicateTest`` pins ``tools/binding_gaps.py``, which the fetcher offers with and the
applier gates with, so one test covers both halves. ``GateTest`` drives
``apply_binding_gaps.apply`` over a hand-built worklist and a fake page store, so it runs
on a clone lacking the gitignored corpus #9 tree. ``CandidateTest`` drives the fetcher's
``candidates_for`` and is skipped without bs4 (pulled in by its prose extractor).

Built with the help of Claude Code.
"""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))

from lib import binding_gaps as bg  # noqa: E402
from lib import target_aliases as ta  # noqa: E402
import apply_binding_gaps as G  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402
from judged_fixture import fill  # noqa: E402

HAS_BS4 = importlib.util.find_spec("bs4") is not None
if HAS_BS4:
    sys.path.insert(0, str(ROOT / "tools" / "fetch"))
    import fetch_binding_gaps as F  # noqa: E402

AL = ta.aliases_by_target()

GOOD = "Testdrug acts as an agonist of the σ 1 receptor ."
BOUND = "Testdrug is an antagonist of the histamine H 1 receptor ."
PAGE = f"Pharmacology\n{GOOD} {BOUND}\n"


def drugs(**extra):
    """A one-drug dataset (plus a stereo relative): it already binds H1."""
    drug = {"id": "testdrug", "name": "Testdrug",
            "bindings": [{"target": "h1", "action": "antagonist",
                          "sources": [{"corpus": "pdsp_ki", "page": "1", "quote": "x"}]}]}
    drug.update(extra)
    return [drug, {"id": "estestdrug", "name": "Estestdrug", "bindings": []}]


def cand(target, line):
    return {"target": target, "target_name": target, "origin": "prose", "line": line}


def worklist(*cands):
    return [{"drug": "testdrug", "name": "Testdrug", "slug": "testdrug", "stahl": False,
             "candidates": list(cands)}]


def read_page(slug):
    return normalize_for_match(PAGE) if slug == "testdrug" else None


def run(cands, rows, data=None):
    data = data if data is not None else drugs()
    work = worklist(*cands)
    gate = G.apply(work, {"testdrug": fill(rows, work[0]["candidates"])}, data, read_page)
    return data[0], [line.split("]")[0][1:] for line in gate.rejected], gate


def pick(index, target, action="agonist"):
    return {"index": index, "target": target, "pick": True, "action": action}


class PredicateTest(unittest.TestCase):
    def test_a_denial_is_negated(self):
        self.assertTrue(bg.negated("It has no affinity for the D 2 receptor .", AL["d2"]))

    def test_a_hedge_is_negated(self):
        self.assertTrue(bg.negated("It may act as a D 2 antagonist .", AL["d2"]))

    def test_the_denial_in_another_clause_does_not_cancel_the_claim(self):
        line = "It is a D 2 antagonist; it has no affinity for the H 1 receptor ."
        self.assertFalse(bg.negated(line, AL["d2"]))
        self.assertTrue(bg.negated(line, AL["h1"]))

    def test_a_negated_list_denies_every_member(self):
        line = "It has negligible affinity for the D 1 , D 5 and H 1 receptors ."
        for target in ("d1", "d5", "h1"):
            self.assertTrue(bg.negated(line, AL[target]), target)

    def test_a_plain_claim_is_not_negated(self):
        self.assertFalse(bg.negated("It is an antagonist of the D 2 receptor .", AL["d2"]))

    def test_a_stereo_tag_or_relative_marks_the_sentence(self):
        self.assertTrue(bg.stereo_mixed("(S)-ketamine blocks NMDA .", []))
        self.assertTrue(bg.stereo_mixed("Like esketamine, it blocks NMDA .", ["esketamine"]))
        self.assertFalse(bg.stereo_mixed("Ketamine blocks NMDA .", ["esketamine"]))
        self.assertTrue(bg.stereo_mixed("(R)-Ketamine blocks NMDA .", []))
        # A plural "(s)" is no CIP descriptor: the sentence stays offerable.
        self.assertFalse(bg.stereo_mixed("It blocks the receptor(s) at 5-HT2A .", []))

    def test_stereo_siblings_name_the_relative_never_the_drug(self):
        roster = drugs()
        self.assertEqual(bg.stereo_siblings(roster[0], roster), ["estestdrug"])
        self.assertEqual(bg.stereo_siblings(roster[1], roster), ["testdrug"])

    def test_bound_targets_cover_coarse_relatives_both_ways(self):
        self.assertIn("alpha2", bg.bound_targets({"bindings": [{"target": "alpha2a"}]}))
        self.assertIn("alpha2c", bg.bound_targets({"bindings": [{"target": "alpha2"}]}))

    def test_a_stahl_citation_anywhere_marks_the_drug(self):
        self.assertTrue(bg.is_stahl({"half_life": {"sources": [{"corpus": "stahl"}]}}))
        self.assertFalse(bg.is_stahl(drugs()[0]))

    def test_combos_and_prodrugs_are_not_offerable(self):
        self.assertFalse(bg.offerable({"id": "c", "name": "Dextromethorphan + Bupropion"}))
        self.assertFalse(bg.offerable({"id": "p", "name": "P", "prodrug": {"to": "x"}}))
        self.assertTrue(bg.offerable(drugs()[0]))


class GateTest(unittest.TestCase):
    def test_a_good_pick_adds_a_cited_binding(self):
        drug, rejected, _ = run([cand("sigma1", GOOD)], [pick(0, "sigma1")])
        self.assertEqual(rejected, [])
        new = next(b for b in drug["bindings"] if b["target"] == "sigma1")
        self.assertEqual(new["action"], "agonist")
        self.assertEqual(new["sources"], [{"corpus": "wikipedia_pharm", "page": "testdrug",
                                           "quote": GOOD, "provenance": "verified"}])
        self.assertNotIn("llm", new["sources"][0])

    def test_a_rejected_pick_writes_nothing(self):
        drug, rejected, _ = run([cand("sigma1", GOOD)],
                                [{"index": 0, "pick": False, "reason": "class-wide"}])
        self.assertEqual((len(drug["bindings"]), rejected), (1, []))

    def test_an_unjudged_candidate_is_reported(self):
        _, rejected, _ = run([cand("sigma1", GOOD), cand("sigma1", GOOD)], [pick(0, "sigma1")])
        self.assertEqual(rejected, ["unjudged candidate"])

    def test_an_already_bound_target_is_rejected(self):
        _, rejected, _ = run([cand("h1", BOUND)], [pick(0, "h1", "antagonist")])
        self.assertEqual(rejected, ["target already bound"])

    def test_a_target_swap_is_rejected(self):
        _, rejected, _ = run([cand("sigma1", GOOD)], [pick(0, "d2")])
        self.assertEqual(rejected, ["target is not the candidate's"])

    def test_an_action_outside_the_vocabulary_is_rejected(self):
        _, rejected, _ = run([cand("sigma1", GOOD)], [pick(0, "sigma1", "binds")])
        self.assertEqual(rejected, ["unknown action"])

    def test_a_negated_quote_is_rejected(self):
        line = "Testdrug has no affinity for the σ 1 receptor ."
        _, rejected, _ = run([cand("sigma1", line)], [pick(0, "sigma1")])
        self.assertEqual(rejected, ["negated or hedged clause"])

    def test_a_stereo_relative_sentence_is_rejected(self):
        line = "Estestdrug acts as an agonist of the σ 1 receptor ."
        _, rejected, _ = run([cand("sigma1", line)], [pick(0, "sigma1")])
        self.assertEqual(rejected, ["names a stereo relative"])

    def test_a_quote_off_the_page_is_rejected(self):
        line = "Testdrug acts as an agonist of the σ 1 receptor in rats ."
        _, rejected, _ = run([cand("sigma1", line)], [pick(0, "sigma1")])
        self.assertEqual(rejected, ["quote not verbatim on the cited page"])

    def test_a_stahl_drug_takes_the_gap_and_keeps_its_own_bindings(self):
        data = drugs(half_life={"sources": [{"corpus": "stahl", "page": 3}]})
        before = copy.deepcopy(data[0]["bindings"])
        drug, rejected, gate = run([cand("sigma1", GOOD)], [pick(0, "sigma1")], data)
        self.assertEqual((len(drug["bindings"]), rejected, len(gate.stahl)), (2, [], 1))
        self.assertEqual(drug["bindings"][:len(before)], before)

    def test_a_prodrug_is_rejected(self):
        data = drugs(prodrug={"to": "x"})
        _, rejected, _ = run([cand("sigma1", GOOD)], [pick(0, "sigma1")], data)
        self.assertEqual(rejected, ["combo or prodrug carries no own binding"])

    def test_a_second_run_changes_nothing(self):
        data = drugs()
        run([cand("sigma1", GOOD)], [pick(0, "sigma1")], data)
        before = copy.deepcopy(data)
        _, rejected, gate = run([cand("sigma1", GOOD)], [pick(0, "sigma1")], data)
        self.assertEqual((data, rejected), (before, []))
        self.assertEqual(gate.stats["skipped: already applied"], 1)

    def test_metadata_keys_are_ignored(self):
        data = drugs()
        work = worklist(cand("sigma1", GOOD))
        gate = G.apply(work, {"_by": {"model": "opus"},
                              "testdrug": fill([pick(0, "sigma1")], work[0]["candidates"])},
                       data, read_page)
        self.assertEqual(gate.rejected, [])


@unittest.skipUnless(HAS_BS4, "the fetcher's prose extractor needs bs4")
class CandidateTest(unittest.TestCase):
    def offered(self, text):
        names = ta.target_names()
        roster = drugs()
        return [(c["target"], c["line"]) for c in F.candidates_for(
            roster[0], text, AL, names, bg.stereo_siblings(roster[0], roster))]

    def test_it_offers_an_unbound_target_and_skips_a_bound_one(self):
        self.assertEqual(self.offered(PAGE), [("sigma1", GOOD)])

    def test_it_skips_a_negated_and_a_stereo_relative_sentence(self):
        text = ("Pharmacology\nTestdrug does not act as an agonist of the σ 1 receptor . "
                "Estestdrug is an antagonist of the D 2 receptor .\n")
        self.assertEqual(self.offered(text), [])

    def test_a_drugbox_target_cell_is_offered_verbatim(self):
        cells = F.drugbox_cells("Biomolecular targets | VMAT2 | x\n")
        self.assertEqual(cells, ["Biomolecular targets | VMAT2"])

    def test_an_only_build_keeps_every_other_drug(self):
        """``--only`` once overwrote the whole worklist, orphaning every other drug's
        committed judged picks (the applier then rejected them all)."""
        def rec(drug, n):
            return {"drug": drug, "candidates": [n]}
        existing = [rec("a", 1), rec("b", 2), rec("c", 3)]
        out = F.scoped(existing, [rec("b", 9), rec("d", 4)], {"b", "c", "d"})
        self.assertEqual(out, [rec("a", 1), rec("b", 9), rec("d", 4)])
        self.assertEqual(F.scoped(existing, [rec("b", 9)], None), [rec("b", 9)])


if __name__ == "__main__":
    unittest.main()
