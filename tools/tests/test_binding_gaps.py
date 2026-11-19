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

    def test_a_subtype_binding_covers_its_receptor_group(self):
        """The muscarinic / alpha1 / dopamine groups once counted as unbound on a drug
        binding m1 / alpha1a / d2, flooding the worklist with every class-word line."""
        self.assertIn("dopamine", bg.bound_targets({"bindings": [{"target": "d2"}]}))
        self.assertIn("m3", bg.bound_targets({"bindings": [{"target": "muscarinic"}]}))
        unmeasured = {"bindings": [{"target": "alpha1a"}]}
        self.assertIn("alpha1", bg.bound_targets(unmeasured))
        # The RCP input wants a measured subtype before a class word counts as covered.
        self.assertNotIn("alpha1", bg.bound_targets(unmeasured, group_needs_ki=True))
        measured = {"bindings": [{"target": "alpha1a", "ki": {"value": 5}}]}
        self.assertIn("alpha1", bg.bound_targets(measured, group_needs_ki=True))

    def test_the_transmitter_word_names_no_receptor_group(self):
        self.assertFalse(ta.mentions("It inhibits dopamine reuptake .", AL["dopamine"]))
        self.assertTrue(ta.mentions("It blocks dopamine receptors .", AL["dopamine"]))

    def test_a_stahl_citation_anywhere_marks_the_drug(self):
        self.assertTrue(bg.is_stahl({"half_life": {"sources": [{"corpus": "stahl"}]}}))
        self.assertFalse(bg.is_stahl(drugs()[0]))

    def test_combos_and_prodrugs_are_not_offerable(self):
        self.assertFalse(bg.offerable({"id": "c", "name": "Dextromethorphan + Bupropion"}))
        self.assertFalse(bg.offerable({"id": "p", "name": "P", "prodrug": {"to": "x"}}))
        self.assertTrue(bg.offerable(drugs()[0]))


RCP = bg.RCP_CORPUS
ALIM = ("L'alimémazine possède des propriétés : - neuroleptiques et sédatives aux doses usuelles, "
        "- antidopaminergiques - anticholinergiques (atropiniques) centrales et périphériques "
        "- adrénolytiques (risque d'hypotension orthostatique).")


def fr_claims(line, target):
    return bg.claims_target(line, target, AL.get(target, []), RCP)


class FrenchPredicateTest(unittest.TestCase):
    """The RCP section 5.1 input (corpus #24) reads French class words as targets."""

    def test_class_words_name_the_receptor_groups(self):
        for target in ("dopamine", "muscarinic", "alpha1"):
            self.assertTrue(fr_claims(ALIM, target), target)

    def test_french_words_count_on_the_rcp_input_only(self):
        self.assertFalse(bg.claims_target(ALIM, "muscarinic", AL["muscarinic"], bg.WIKI_CORPUS))

    def test_adrenolytic_needs_an_alpha_cue(self):
        line = "La molécule possède des propriétés adrénolytiques marquées."
        self.assertFalse(fr_claims(line, "alpha1"))
        self.assertTrue(fr_claims(line.replace("marquées", "alpha"), "alpha1"))

    def test_a_french_denial_or_hedge_is_negated(self):
        self.assertFalse(fr_claims("Il n'a aucune activité anticholinergique.", "muscarinic"))
        self.assertFalse(fr_claims("C'est un neuroleptique non anticholinergique.", "muscarinic"))
        self.assertFalse(fr_claims("Il semble avoir des effets anticholinergiques.", "muscarinic"))

    def test_a_semicolon_list_shares_its_denial(self):
        """A label runs one denial over a ";" list, so ";" is no clause break."""
        line = ("Il n'a pas d'affinité pour les récepteurs 5-HT2 ; récepteurs muscariniques ; "
                "récepteurs dopaminergiques.")
        self.assertFalse(fr_claims(line, "muscarinic"))
        self.assertFalse(fr_claims(line, "dopamine"))

    def test_a_denial_in_another_clause_does_not_cancel_the_claim(self):
        line = "Il est antihistaminique, mais il n'a pas d'effet antidopaminergique."
        self.assertTrue(fr_claims(line, "h1"))
        self.assertFalse(fr_claims(line, "dopamine"))


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

    def test_an_rcp_pick_cites_the_french_page(self):
        line = "Testdrug présente des propriétés anticholinergiques centrales."
        c = dict(cand("muscarinic", line), corpus=RCP, page="123", origin="rcp_5.1")
        data, work = drugs(), worklist(c)
        pages = {(RCP, "123"): normalize_for_match(f"## 5.1. Propriétés\n{line}\n")}
        gate = G.apply(work, {"testdrug": fill([pick(0, "muscarinic", "antagonist")],
                                               work[0]["candidates"])},
                       data, read_page, lambda corpus, page: pages.get((corpus, page)))
        self.assertEqual(gate.rejected, [])
        new = next(b for b in data[0]["bindings"] if b["target"] == "muscarinic")
        self.assertEqual(new["sources"][0]["corpus"], RCP)
        self.assertEqual(new["sources"][0]["page"], "123")

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

    def test_rcp_units_join_a_lead_with_its_items(self):
        page = ("# T\n## 4.4. Mises\nAutre.\n## 5.1. Propriétés\nIl possède :\n"
                "- antihistaminiques H1,\n- anticholinergiques.\nTexte seul.\n- puce isolée\n")
        self.assertEqual(F.rcp_units(page), [
            "Il possède : - antihistaminiques H1, - anticholinergiques.",
            "Texte seul.", "puce isolée"])


if __name__ == "__main__":
    unittest.main()
