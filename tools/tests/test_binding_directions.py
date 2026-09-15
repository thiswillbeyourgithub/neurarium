#!/usr/bin/env python
"""Unit tests for the binding-direction pass: its gates, its idempotency, its aliases.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable directly::

    python tools/tests/test_binding_directions.py

pytest-discoverable.

``GateTest`` drives ``apply_binding_directions.apply`` over a hand-built worklist with a
fake page store, so it runs on a clone that lacks the gitignored corpus #9 tree.
``AliasTest`` pins the matcher both halves share: the fetcher offers a sentence because
it names a target, and the applier lets the judge's pick through for the same reason, so
a drift there would let the gate accept what the worklist never showed.

Built with the help of Claude Code.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import drugs_io  # noqa: E402
import target_aliases as ta  # noqa: E402
import apply_binding_directions as A  # noqa: E402

# The one stored page every fixture quote must be verbatim on. `read_page` returns it
# normalized, exactly as the real `page_text` does.
PAGE = ("Quetiapine is an antagonist of the serotonin 5-HT 2C receptor . "
        "It also acts as an inverse agonist at the histamine H 1 receptor . "
        "Quetiapine has high affinity for the alpha-2A adrenergic receptor .")

CANDIDATES = [
    "Quetiapine is an antagonist of the serotonin 5-HT 2C receptor .",
    "It also acts as an inverse agonist at the histamine H 1 receptor .",
    "Quetiapine has high affinity for the alpha-2A adrenergic receptor .",
]

WORKLIST = [{
    "drug": "testdrug",
    "name": "Testdrug",
    "slug": "testdrug",
    "targets": [{"target": t, "name": t, "aliases": ta.aliases_by_target()[t]}
                for t in ("5ht2c", "h1", "alpha2a")],
    "candidates": CANDIDATES,
}]


def drugs():
    """A one-drug dataset: two affinity-only bindings and one that already has a direction."""
    return [{
        "id": "testdrug", "name": "Testdrug",
        "bindings": [
            {"target": "5ht2c", "affinity_only": True,
             "ki": {"median": 3.0, "source": {"corpus": "pdsp_ki", "ki_id": "1"}}},
            {"target": "alpha2a", "affinity_only": True},
            {"target": "h1", "action": "antagonist",
             "sources": [{"corpus": "stahl", "page": 12, "quote": "blocks H1",
                          "provenance": "verified"}]},
        ],
    }]


def read_page(slug):
    return A.normalize_for_match(PAGE) if slug == "testdrug" else None


def run(judged, data=None):
    """Apply one judged file; returns the mutated drug record and the rejection reasons."""
    data = data if data is not None else drugs()
    stats, rejected = A.apply(WORKLIST, judged, data, read_page)
    return data[0], [line.split("]")[0][1:] for line in rejected], stats


def binding(drug, target):
    return next(b for b in drug["bindings"] if b["target"] == target)


class GateTest(unittest.TestCase):
    """The six gates between a model's answer and ``drugs_data.jsonl``."""

    def test_a_good_row_sets_the_direction_and_cites_it(self):
        drug, why, _ = run({"testdrug": [{"target": "5ht2c", "action": "antagonist",
                                          "index": 0}]})
        b = binding(drug, "5ht2c")
        self.assertEqual(why, [])
        self.assertEqual(b["action"], "antagonist")
        self.assertNotIn("affinity_only", b)
        # The measured affinity is a separate claim and this pass never touches it.
        self.assertEqual(b["ki"]["source"]["corpus"], "pdsp_ki")
        self.assertEqual(b["sources"], [{"corpus": "wikipedia_pharm", "page": "testdrug",
                                         "quote": CANDIDATES[0],
                                         "provenance": "verified"}])

    def test_no_llm_stamp_is_written_here(self):
        """The judge stamp is recheck_quotes.py's to write: a model PICKED this sentence,
        so it is not backed until a second model has agreed it supports the claim."""
        drug, _why, _ = run({"testdrug": [{"target": "5ht2c", "action": "antagonist",
                                           "index": 0}]})
        self.assertNotIn("llm", binding(drug, "5ht2c")["sources"][0])

    def test_a_drug_the_worklist_never_offered_is_rejected(self):
        _drug, why, _ = run({"nosuchdrug": [{"target": "5ht2c", "action": "antagonist",
                                             "index": 0}]})
        self.assertEqual(why, ["drug not in the worklist"])

    def test_an_index_past_the_end_is_rejected_not_silently_dropped(self):
        drug, why, _ = run({"testdrug": [{"target": "5ht2c", "action": "antagonist",
                                          "index": 9}]})
        self.assertEqual(why, ["candidate index out of range"])
        self.assertTrue(binding(drug, "5ht2c")["affinity_only"])

    def test_a_target_the_drug_does_not_bind_is_rejected(self):
        _drug, why, _ = run({"testdrug": [{"target": "d2", "action": "antagonist",
                                           "index": 0}]})
        self.assertEqual(why, ["no binding on that target"])

    def test_a_binding_that_already_states_a_direction_is_untouched(self):
        """Confirm-only: this pass fills a direction in, it never revises one."""
        drug, why, _ = run({"testdrug": [{"target": "h1", "action": "inverse_agonist",
                                          "index": 1}]})
        b = binding(drug, "h1")
        self.assertEqual(why, ["binding already states a direction"])
        self.assertEqual(b["action"], "antagonist")
        self.assertEqual([s["corpus"] for s in b["sources"]], ["stahl"])

    def test_an_action_outside_the_vocabulary_is_rejected(self):
        drug, why, _ = run({"testdrug": [{"target": "5ht2c", "action": "blocks_it",
                                          "index": 0}]})
        self.assertEqual(why, ["unknown action"])
        self.assertTrue(binding(drug, "5ht2c")["affinity_only"])

    def test_a_quote_that_does_not_name_the_target_is_rejected(self):
        """The judge picks a sentence and a target separately, so this is the only check
        that stops the two being paired wrongly: candidate 1 is about H1, not alpha2A."""
        drug, why, _ = run({"testdrug": [{"target": "alpha2a", "action": "antagonist",
                                          "index": 1}]})
        self.assertEqual(why, ["quote does not name the target"])
        self.assertTrue(binding(drug, "alpha2a")["affinity_only"])

    def test_a_quote_that_is_not_on_the_page_fails_the_verbatim_gate(self):
        work = copy.deepcopy(WORKLIST)
        work[0]["candidates"] = ["Quetiapine is a potent agonist of the 5-HT 2C receptor ."]
        data = drugs()
        _stats, rejected = A.apply(work, {"testdrug": [{"target": "5ht2c",
                                                        "action": "agonist",
                                                        "index": 0}]}, data, read_page)
        self.assertEqual([line.split("]")[0][1:] for line in rejected],
                         ["quote not verbatim on the cited page"])
        self.assertTrue(binding(data[0], "5ht2c")["affinity_only"])

    def test_a_missing_stored_page_stops_the_row(self):
        work = copy.deepcopy(WORKLIST)
        work[0]["slug"] = "never_fetched"
        data = drugs()
        _stats, rejected = A.apply(work, {"testdrug": [{"target": "5ht2c",
                                                        "action": "antagonist",
                                                        "index": 0}]}, data, read_page)
        self.assertEqual([line.split("]")[0][1:] for line in rejected],
                         ["no stored page for the citation"])


class IdempotencyTest(unittest.TestCase):
    """A second run with the same judged file must be a no-op, not a pile of rejections."""

    JUDGED = {"testdrug": [{"target": "5ht2c", "action": "antagonist", "index": 0}]}

    def test_second_run_changes_nothing_and_reports_no_rejection(self):
        data = drugs()
        A.apply(WORKLIST, self.JUDGED, data, read_page)
        after_first = copy.deepcopy(data)
        stats, rejected = A.apply(WORKLIST, self.JUDGED, data, read_page)
        self.assertEqual(data, after_first)
        self.assertEqual(rejected, [])
        self.assertEqual(stats["skipped: already applied"], 1)

    def test_it_round_trips_through_the_jsonl_store(self):
        """The write path the script actually takes: the same helper every other applier
        uses, so a re-run reads back exactly what was written and still no-ops."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drugs_data.jsonl"
            data = drugs()
            A.apply(WORKLIST, self.JUDGED, data, read_page)
            drugs_io.save_drugs(data, path)
            reloaded = drugs_io.load_drugs(path)
            b = binding(reloaded[0], "5ht2c")
            self.assertEqual(b["action"], "antagonist")
            self.assertEqual(b["sources"][0]["quote"], CANDIDATES[0])
            stats, rejected = A.apply(WORKLIST, self.JUDGED, reloaded, read_page)
            self.assertEqual(rejected, [])
            self.assertEqual(stats["skipped: already applied"], 1)


class AliasTest(unittest.TestCase):
    """The shared "does this sentence name this target" matcher."""

    ALIASES = ta.aliases_by_target()

    def assertNames(self, target, sentence, expected=True):
        self.assertEqual(ta.mentions(sentence, self.ALIASES[target]), expected,
                         f"{target} vs {sentence!r}")

    def test_a_serotonin_receptor_under_its_common_spellings(self):
        for sentence in ("an antagonist of the 5-HT2C receptor",
                         "an antagonist of the 5-HT 2C receptor",
                         "acts at 5HT2C sites",
                         "a serotonin 2C agonist"):
            self.assertNames("5ht2c", sentence)

    def test_a_subtype_is_not_named_by_its_sibling(self):
        self.assertNames("5ht2c", "binds the 5-HT2A receptor", False)

    def test_an_adrenoceptor_whether_written_in_greek_or_spelled_out(self):
        for sentence in ("α2A-adrenergic receptor antagonism",
                         "an alpha-2A adrenergic antagonist",
                         "blockade of alpha 2A receptors"):
            self.assertNames("alpha2a", sentence)

    def test_the_coarse_group_does_not_absorb_its_subtype(self):
        # alpha2 is its own (receptor_group) target, so a sentence about alpha2A must
        # not read as naming it: the two carry different bindings.
        self.assertNames("alpha2", "blocks α2 adrenergic receptors")
        self.assertNames("alpha2", "blocks α2A receptors", False)

    def test_a_transporter_by_abbreviation_process_or_gene(self):
        for sentence in ("inhibits SERT with high potency",
                         "a selective serotonin reuptake inhibitor",
                         "blockade of the serotonin transporter",
                         "5-HTT occupancy was measured"):
            self.assertNames("sert", sentence)

    def test_a_short_id_does_not_fire_inside_a_longer_token(self):
        # The gate would be worthless if "D2" matched CYP2D6 or the word "and 2".
        self.assertNames("d2", "dopamine D 2 receptor antagonist")
        self.assertNames("d2", "metabolized by CYP2D6", False)
        self.assertNames("d2", "quick and 2 others", False)


if __name__ == "__main__":
    unittest.main()
