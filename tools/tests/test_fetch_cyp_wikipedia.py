#!/usr/bin/env python
"""Unit tests for tools/fetch/fetch_cyp_wikipedia.py's claim extraction.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable
directly::

    python tools/tests/test_fetch_cyp_wikipedia.py

pytest-discoverable. ``claims`` is the whole pass: it decides which sentences of a
long Wikipedia article state a role **this drug** plays at an enzyme. Every case
below is a real sentence from a stored article, kept because it sits on one of the
two edges the 2026-07-28 audit found (see docs/SOURCING_GAPS.md): a genuine claim
whose *consequence clause* used to veto it, and a genuine two-role sentence that
used to be dropped whole rather than split.

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fetch"))
import fetch_cyp_wikipedia as W  # noqa: E402


def claims(sentence, drug_id, name=None):
    """The (role, strength, enzymes) rows a one-line article yields for a drug."""
    names = W.subject_names({"id": drug_id, "name": name or drug_id}, drug_id)
    return [(role, strength, enzymes)
            for _quote, role, strength, enzymes in W.claims(sentence, names)]


class VictimFrameTest(unittest.TestCase):
    """The victim veto reads the head, because the tail is the claim's consequence."""

    def test_consequence_clause_does_not_veto_the_claim(self):
        """... but it still BOUNDS it: the isoform named in the consequence ("some
        CYP2D6 substrates") is the victim's, so the claim stops before it."""
        got = claims("Escitalopram weakly inhibits CYP2D6 , and hence may increase "
                     "plasma levels of some CYP2D6 substrates such as aripiprazole , "
                     "risperidone , tramadol , or codeine .", "escitalopram")
        self.assertEqual(got, [("inhibitor", "weak", ["cyp2d6"])])

    def test_another_molecule_as_actor_still_vetoes(self):
        """The frame the veto exists for: the head, not the drug, owns the verb."""
        self.assertEqual(
            claims("Smoking induces CYP1A2 enzyme activity, which accelerates the "
                   "metabolism of clozapine and reduces its plasma concentrations.",
                   "clozapine"), [])

    def test_relative_clause_hands_the_verb_another_subject(self):
        self.assertEqual(
            claims("Fluvoxamine may increase serum concentrations of mirtazapine, "
                   "which is mainly metabolized by CYP1A2 .", "mirtazapine"), [])


class TwoRolesTest(unittest.TestCase):
    """A sentence stating two roles is split by position, not dropped."""

    def test_each_enzyme_goes_to_the_verb_it_follows(self):
        got = claims("Modafinil is a weak to moderate inducer of CYP3A4 and a weak "
                     "inhibitor of CYP2C19 , enzymes of the cytochrome P450 system.",
                     "modafinil")
        # "weak to moderate" states two tiers at once, so the inducer honestly gets
        # none, while the coordinated half keeps its own "weak".
        self.assertEqual(got, [("inducer", None, ["cyp3a4"]),
                               ("inhibitor", "weak", ["cyp2c19"])])

    def test_a_later_verb_must_stay_coordinated_with_the_first(self):
        """Nefazodone's second half is about the drugs it interacts with, and the
        comma + "that" between the two verbs is what says so."""
        got = claims("Nefazodone is a potent inhibitor of CYP3A4 , and may interact "
                     "adversely with many commonly used medications that are "
                     "metabolized by CYP3A4.", "nefazodone")
        self.assertEqual(got, [("inhibitor", "strong", ["cyp3a4"])])


class DrugboxRowTest(unittest.TestCase):
    """The drugbox Metabolism row: a substrate claim by construction."""

    def test_non_cyp_route_is_read_when_the_vocabulary_carries_it(self):
        got = claims("Metabolism | Liver (90%): • Alcohol dehydrogenase "
                     "• MEOS ( CYP2E1 )", "ethanol", "Ethanol")
        self.assertEqual(got, [("substrate", None, ["adh", "cyp2e1"])])

    def test_negation_vetoes_the_row(self):
        """Wikipedia states the absence of a route as often as its presence."""
        self.assertEqual(
            claims("Metabolism | Liver, by hydrolysis without involvement of CYP3A4",
                   "somedrug"), [])


if __name__ == "__main__":
    unittest.main()
