#!/usr/bin/env python
"""Unit tests for the ``drug_enzymes`` pipeline's gates and for the data they let through.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable directly::

    python tools/tests/test_cyp_pipeline.py

pytest-discoverable.

Two halves, because the pipeline has two kinds of failure. ``GateTest`` drives
``apply_cyp_sources.apply`` over a hand-built worklist with a fake page store, so it runs
on a clone that lacks the gitignored corpora. ``ShippedRowsTest`` reads the committed
caches instead: the rows the old regex passes got wrong are judgements, not code paths,
so the only place to pin them is the data itself.

Built with the help of Claude Code.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_cyp_sources as A  # noqa: E402
from judged_fixture import fill  # noqa: E402

CACHE = ROOT / "tools" / "generated_cache"

# One page per corpus, holding every quote the fixtures cite. `StubGate` below serves it
# for any (corpus, page), normalized, exactly as the real `PageGate.text` does.
PAGE = ("Fluoxetine and paroxetine are both potent inhibitors of CYP2D6 and CYP2C19. "
        "Diazepam undergoes oxidative metabolism by demethylation ( CYP2C9 , 2C19 ). "
        "Inhibits CYP2C9/2C19 . Metabolism | Mainly CYP3A4 / 5 . "
        "It is metabolized by CYP2D6 . It is mainly metabolized by CYP2D6 . "
        "It is metabolized by CYP3A4 and to a lesser extent by CYP2C9 .")


def worklist(*quotes):
    """A one-drug worklist whose candidates are `quotes`, in the given order."""
    return {
        "vocabulary": {
            "enzymes": ["cyp2c9", "cyp2c19", "cyp2d6", "cyp3a4", "cyp3a5"],
            "roles": ["substrate", "inhibitor", "inducer"],
            "strengths": {"substrate": ["major", "minor"],
                          "inhibitor": ["strong", "moderate", "weak"],
                          "inducer": ["strong", "moderate", "weak"]},
        },
        "drugs": {"testdrug": {"name": "Testdrug", "candidates": [
            {"n": i, "corpus": "stahl", "page": 1, "quote": q, "heading": None}
            for i, q in enumerate(quotes)]}},
    }


class StubGate(A.PageGate):
    def __init__(self):
        super().__init__({})

    def text(self, corpus, page):
        return A.normalize_for_match(PAGE)


def judge(work, judged):
    """``judged`` with each row echoing its candidate's qid (rows name it by ``n``)."""
    for drug, rows in judged.items():
        fill(rows, (work["drugs"].get(drug) or {}).get("candidates", []), key="n")
    return judged


def run(work, judged):
    """The gates' verdict: the emitted rows for the one drug, plus the rejection reasons."""
    out, _stats, rejected = A.apply(work, judge(work, judged), StubGate())
    rows = out["stahl"].get("testdrug", [])
    return rows, [line.split("]")[0][1:] for line in rejected]


class GateTest(unittest.TestCase):
    """The five gates between a model's answer and the cache."""

    def test_a_drug_the_worklist_never_offered_is_rejected(self):
        _rows, why = run(worklist("Inhibits CYP2C9/2C19 ."),
                         {"nosuchdrug": [{"n": 0, "enzyme": "cyp2c9", "role": "inhibitor"}]})
        self.assertEqual(why, ["drug not in the worklist"])

    def test_an_index_past_the_end_is_rejected_not_silently_dropped(self):
        _rows, why = run(worklist("Inhibits CYP2C9/2C19 ."),
                         {"testdrug": [{"n": 7, "enzyme": "cyp2c9", "role": "inhibitor"}]})
        self.assertEqual(why, ["candidate index out of range"])

    def test_a_strength_the_role_cannot_take_is_rejected(self):
        # "major"/"minor" rank a substrate; an inhibitor is strong/moderate/weak.
        _rows, why = run(worklist("Inhibits CYP2C9/2C19 ."),
                         {"testdrug": [{"n": 0, "enzyme": "cyp2c9", "role": "inhibitor",
                                        "strength": "major"}]})
        self.assertEqual(why, ["strength not available to this role"])

    def test_the_quote_must_name_the_isoform_the_row_claims(self):
        # The judge answers with an index and an enzyme separately, so this is the only
        # check that stops the two being paired wrongly. Here the sentence writes the
        # second isoform as a bare continuation ("2C19"), which names no enzyme.
        quote = "Diazepam undergoes oxidative metabolism by demethylation ( CYP2C9 , 2C19 ) ."
        rows, why = run(worklist(quote),
                        {"testdrug": [{"n": 0, "enzyme": "cyp2c9", "role": "substrate"},
                                      {"n": 0, "enzyme": "cyp2c19", "role": "substrate"}]})
        self.assertEqual([r["enzyme"] for r in rows], ["cyp2c9"])
        self.assertEqual(why, ["quote does not name the claimed isoform"])

    def test_the_two_shorthands_for_a_pair_do_name_both_isoforms(self):
        # "CYP2C9/2C19" spells the second out and "CYP3A4 / 5" gives only its digit;
        # both are the source naming two enzymes, so neither may be gated away.
        rows, why = run(worklist("Inhibits CYP2C9/2C19 .", "Metabolism | Mainly CYP3A4 / 5 ."),
                        {"testdrug": [{"n": 0, "enzyme": "cyp2c9", "role": "inhibitor"},
                                      {"n": 0, "enzyme": "cyp2c19", "role": "inhibitor"},
                                      {"n": 1, "enzyme": "cyp3a4", "role": "substrate"},
                                      {"n": 1, "enzyme": "cyp3a5", "role": "substrate"}]})
        self.assertEqual(why, [])
        self.assertEqual(len(rows), 4)

    def test_a_quote_the_judge_edited_fails_the_verbatim_gate(self):
        work = worklist("Fluoxetine and paroxetine are potent inhibitors of CYP2D6 .")
        _rows, why = run(work, {"testdrug": [{"n": 0, "enzyme": "cyp2d6",
                                              "role": "inhibitor"}]})
        self.assertEqual(why, ["quote not verbatim on the cited page"])

    def test_the_more_specific_of_two_readings_of_one_pair_wins(self):
        # An article often states a pair twice, plainly and then with a tier. That is one
        # fact at two resolutions, so reading order is no reason to keep the weaker one.
        work = worklist("It is metabolized by CYP2D6 .", "It is mainly metabolized by CYP2D6 .")
        rows, why = run(work, {"testdrug": [
            {"n": 0, "enzyme": "cyp2d6", "role": "substrate"},
            {"n": 1, "enzyme": "cyp2d6", "role": "substrate", "strength": "major"}]})
        self.assertEqual(why, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["strength"], "major")
        self.assertIn("mainly", rows[0]["sources"][0]["quote"])


class StrengthPassTest(unittest.TestCase):
    """The tier pass: a second sentence may back a kept row's strength, never change it."""

    WORK = ("It is metabolized by CYP2D6 .", "It is mainly metabolized by CYP2D6 .",
            "It is metabolized by CYP3A4 and to a lesser extent by CYP2C9 .")
    ROLE = {"testdrug": [{"n": 0, "enzyme": "cyp2d6", "role": "substrate",
                          "strength": "major"}]}

    def tier(self, picks):
        work = worklist(*self.WORK)
        out, _stats, rejected = A.apply(work, judge(work, self.ROLE), StubGate(),
                                        strength_judged=judge(work, {"testdrug": picks}))
        rows = out["stahl"]["testdrug"]
        return rows, [line.split("]")[0][1:] for line in rejected]

    def test_a_tier_sentence_rides_the_kept_row_as_an_extra_source(self):
        rows, why = self.tier([{"n": 1, "enzyme": "cyp2d6", "role": "substrate",
                                "strength": "major"}])
        self.assertEqual(why, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual([s["quote"] for s in rows[0]["sources"]],
                         ["It is metabolized by CYP2D6 .",
                          "It is mainly metabolized by CYP2D6 ."])
        # Unstamped: the recheck has to judge it before it can ship.
        self.assertNotIn("llm", rows[0]["sources"][1])

    def test_a_tier_pick_never_changes_the_stored_strength(self):
        rows, why = self.tier([{"n": 2, "enzyme": "cyp2c9", "role": "substrate",
                                "strength": "minor"},
                               {"n": 1, "enzyme": "cyp2d6", "role": "substrate",
                                "strength": "minor"}])
        self.assertEqual(why, ["tier pick restates no kept pair",
                               "tier pick contradicts the stored strength"])
        self.assertEqual(rows[0]["strength"], "major")
        self.assertEqual(len(rows[0]["sources"]), 1)

    def test_a_tier_sentence_must_carry_the_tier_word(self):
        _rows, why = self.tier([{"n": 0, "enzyme": "cyp2d6", "role": "substrate",
                                 "strength": "major"}])
        self.assertEqual(why, ["quote states no tier word"])


def shipped():
    """Every (drug, enzyme, role) triple in the two committed caches."""
    out = set()
    for name in ("drug_enzymes.json", "drug_enzymes_wikipedia.json"):
        for drug, rows in json.loads((CACHE / name).read_text(encoding="utf-8")).items():
            for row in rows:
                out.add((drug, row["enzyme"], row["role"]))
    return out


class ShippedRowsTest(unittest.TestCase):
    """Rows a pattern match got wrong, and rows only a reader can get right."""

    @classmethod
    def setUpClass(cls):
        cls.rows = shipped()

    def test_a_denial_is_not_a_substrate_claim(self):
        # desvenlafaxine's drugbox reads "CYP2C19 , CYP3A4 , ( CYP2D6 is not involved)".
        self.assertNotIn(("desvenlafaxine", "cyp2d6", "substrate"), self.rows)
        self.assertIn(("desvenlafaxine", "cyp2c19", "substrate"), self.rows)

    def test_somebody_elses_inhibitors_are_not_this_drugs_role(self):
        # doxepin's article warns against "taking potent CYP2D6 inhibitors such as
        # fluoxetine": the inhibitor is the co-prescribed drug, not doxepin.
        self.assertNotIn(("doxepin", "cyp2d6", "inhibitor"), self.rows)
        self.assertIn(("doxepin", "cyp2d6", "substrate"), self.rows)

    def test_induction_is_not_inhibition(self):
        # Stahl's topiramate line is "Inhibits CYP2C19 and induces CYP3A4": one verb each.
        self.assertNotIn(("topiramate", "cyp3a4", "inhibitor"), self.rows)
        self.assertIn(("topiramate", "cyp3a4", "inducer"), self.rows)
        self.assertIn(("topiramate", "cyp2c19", "inhibitor"), self.rows)

    def test_a_plural_subject_still_names_this_drug(self):
        # "Bupropion and its metabolites are inhibitors of CYP2D6" and "Both are potent
        # inhibitors of CYP2D6 ... and CYP2C19" (fluoxetine with paroxetine): the claim is
        # about this drug however many subjects the sentence carries.
        self.assertIn(("bupropion", "cyp2d6", "inhibitor"), self.rows)
        self.assertIn(("fluoxetine", "cyp2c19", "inhibitor"), self.rows)

    def test_a_class_that_includes_this_drug_still_names_it(self):
        # "Nitrobenzodiazepines such as nitrazepam ... are metabolically activated by
        # CYP3A4".
        self.assertIn(("nitrazepam", "cyp3a4", "substrate"), self.rows)

    def test_the_contradicted_rows_still_exist_to_be_doubted(self):
        # contradictions.py raises at build time when one of its keys names no row, so a
        # re-judged cache that dropped one would take the flag down with it.
        for key in (("fluoxetine", "cyp3a4", "inhibitor"),
                    ("armodafinil", "cyp1a2", "inducer"),
                    ("modafinil", "cyp2c9", "inhibitor")):
            self.assertIn(key, self.rows)


class SharedGateTest(unittest.TestCase):
    """The two ``prose_gate`` seams this applier relies on beyond ``on_page``."""

    def test_text_distinguishes_a_missing_page_from_a_present_one(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "7.md").write_text("Metabolized  by CYP2D6.", encoding="utf-8")
            gate = A.PageGate({"stahl": Path(tmp)})
            self.assertEqual(gate.text("stahl", 7), A.normalize_for_match("Metabolized by CYP2D6."))
            self.assertIsNone(gate.text("stahl", 8))
            self.assertIsNone(gate.text("wikipedia_pharm", 7))

    def test_add_source_key_dedups_spellings_of_one_sentence(self):
        bucket = [{"quote": "Inhibits  CYP2D6."}]
        self.assertTrue(A.add_source(list(bucket), {"quote": "Inhibits CYP2D6."}))
        self.assertFalse(A.add_source(bucket, {"quote": "Inhibits CYP2D6."},
                                      key=A.normalize_for_match))
        self.assertEqual(len(bucket), 1)


if __name__ == "__main__":
    unittest.main()


class VocabularyTest(unittest.TestCase):
    """The worklist's isoform vocabulary is ENZYMES itself. Regression: a hand-copied
    mirror in fetch_cyp_wikipedia lagged six isoforms behind (CYP1A1, UGT1A1, UGT1A3,
    UGT1A6, UGT2B4, UGT2B10), so no sentence naming them could ever become a row."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        sys.path.insert(0, str(ROOT / "tools" / "fetch"))

    def test_known_enzymes_is_the_modeled_vocabulary(self):
        from lib.corpora import wikipedia as wikistore
        from data_generators.drugs import ENZYMES
        self.assertEqual(set(wikistore.KNOWN_ENZYMES), set(ENZYMES))

    def test_every_modeled_ugt_isoform_is_read(self):
        import fetch_cyp
        self.assertEqual(fetch_cyp.isoforms("by UGT1A1, UGT1A3 and UGT2B10"),
                         ["ugt1a1", "ugt1a3", "ugt2b10"])
