#!/usr/bin/env python
"""Unit tests for the binding-direction pass: its gates, its idempotency, its aliases.

Stdlib ``unittest`` only (no deps), matching the other tests here. Runnable directly::

    python tools/tests/test_binding_directions.py

pytest-discoverable.

``GateTest`` drives ``apply_binding_directions.apply`` over a hand-built worklist with a
fake page store, so it runs on a clone that lacks the gitignored corpus #9 tree.
``TableGateTest`` drives the other input, ``apply_tables``, the same way: a hand-built
proposals file, a fake page and the fetcher's resolver injected, so the shared gate is
exercised on both its callers without bs4.
``AliasTest`` pins the matcher both halves share: the fetcher offers a sentence because
it names a target, and the applier lets the judge's pick through for the same reason, so
a drift there would let the gate accept what the worklist never showed. ``TableCellTest``
pins the other half of that pairing, the Action cell the table pass reads in its place.

Built with the help of Claude Code.
"""

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib import drugs_io  # noqa: E402
from lib import target_aliases as ta  # noqa: E402
import apply_binding_directions as A  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402
from judged_fixture import fill  # noqa: E402

# The table fetcher imports bs4 at module level, which a plain clone need not have; the
# applier half it feeds is tested regardless, the resolver being injected.
HAS_BS4 = importlib.util.find_spec("bs4") is not None
if HAS_BS4:
    sys.path.insert(0, str(ROOT / "tools" / "fetch"))
    import fetch_binding_direction_tables as T  # noqa: E402

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
    "candidates": [{"line": c} for c in CANDIDATES],
}]


def judge(judged, work=None):
    """``judged`` with each row echoing its candidate's qid, as a judge writes it."""
    by = {r["drug"]: r["candidates"] for r in work or WORKLIST}
    for drug, rows in judged.items():
        fill(rows, by.get(drug, []))
    return judged


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
    return normalize_for_match(PAGE) if slug == "testdrug" else None


def run(judged, data=None):
    """Apply one judged file; returns the mutated drug record and the rejection reasons."""
    data = data if data is not None else drugs()
    stats, rejected = A.apply(WORKLIST, judge(judged), data, read_page)
    return data[0], [line.split("]")[0][1:] for line in rejected], stats


def binding(drug, target):
    return next(b for b in drug["bindings"] if b["target"] == target)


# The table half of the pass. Its quote is one flattened row of the article's Ki table,
# so the stored page holds those rows as `row_text` writes them.
TABLE_PAGE = ("Binding profile\n"
              "Target | Ki (nM) | Action\n"
              "5-HT 2C | 3.0 | Antagonist\n"
              "\u03b1 2A | 12 | Agonist\n"
              "H 1 | 0.5 | Inverse agonist\n")

# The fetcher's own resolver, injected exactly as the script injects it: a name it cannot
# resolve is a name it never offered, so the gate can never accept one.
WIKI_TARGETS = {"5-HT 2C": "5ht2c", "\u03b1 2A": "alpha2a", "H 1": "h1"}


def read_table_page(slug):
    return normalize_for_match(TABLE_PAGE) if slug == "testdrug" else None


def table_row(target, wiki_name, cell, action, quote):
    return {"target": target, "wiki_name": wiki_name, "cell": cell,
            "action": action, "quote": quote}


def run_tables(rows, data=None):
    """Apply one proposals file; returns the mutated drug record and the reasons."""
    data = data if data is not None else drugs()
    stats, rejected = A.apply_tables({"testdrug": {"slug": "testdrug", "rows": rows}},
                                     data, read_table_page, WIKI_TARGETS.get)
    return data[0], [line.split("]")[0][1:] for line in rejected], stats


GOOD_ROW = table_row("5ht2c", "5-HT 2C", "Antagonist", "antagonist",
                     "5-HT 2C | 3.0 | Antagonist")


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

    def test_a_pick_whose_worklist_shifted_is_rejected(self):
        """A rebuilt worklist that moved the judged sentence must not land another one:
        the pick was judged on candidate 0, the rebuild put candidate 1 at index 0."""
        work = copy.deepcopy(WORKLIST)
        judged = judge({"testdrug": [{"target": "5ht2c", "action": "antagonist",
                                      "index": 0}]}, work)
        work[0]["candidates"].reverse()
        data = drugs()
        _stats, rejected = A.apply(work, judged, data, read_page)
        self.assertEqual([line.split("]")[0][1:] for line in rejected],
                         ["qid mismatch: the worklist changed since this pick was judged"])
        self.assertTrue(binding(data[0], "5ht2c")["affinity_only"])

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
        work[0]["candidates"] = [
            {"line": "Quetiapine is a potent agonist of the 5-HT 2C receptor ."}]
        data = drugs()
        _stats, rejected = A.apply(work, judge({"testdrug": [{"target": "5ht2c",
                                                              "action": "agonist",
                                                              "index": 0}]}, work),
                                   data, read_page)
        self.assertEqual([line.split("]")[0][1:] for line in rejected],
                         ["quote not verbatim on the cited page"])
        self.assertTrue(binding(data[0], "5ht2c")["affinity_only"])

    def test_a_missing_stored_page_stops_the_row(self):
        work = copy.deepcopy(WORKLIST)
        work[0]["slug"] = "never_fetched"
        data = drugs()
        _stats, rejected = A.apply(work, judge({"testdrug": [{"target": "5ht2c",
                                                              "action": "antagonist",
                                                              "index": 0}]}, work),
                                   data, read_page)
        self.assertEqual([line.split("]")[0][1:] for line in rejected],
                         ["no stored page for the citation"])


class IdempotencyTest(unittest.TestCase):
    """A second run with the same judged file must be a no-op, not a pile of rejections."""

    JUDGED = judge({"testdrug": [{"target": "5ht2c", "action": "antagonist", "index": 0}]})

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

    def test_gaba_a_rho_is_not_named_by_plain_gaba_a(self):
        # The display name is "GABA-A-ρ": with ρ unfolded its alias reduced to
        # "gaba a" and fired on every GABA-A sentence.
        self.assertNames("gaba_a_rho", "a positive allosteric modulator of GABAA receptors",
                         False)
        self.assertNames("gaba_a_rho", "an antagonist of GABA-A-ρ receptors")
        self.assertNames("gaba_a_rho", "an antagonist of GABA-A-rho receptors")

    def test_alpha4beta2_and_gaba_c_resolve(self):
        al = ta.aliases_by_target()
        self.assertTrue(ta.mentions("an \u03b1 4 \u03b2 2 nicotinic antagonist", al["nachr_a4b2"]))
        self.assertTrue(ta.mentions("an antagonist of GABA C receptors", al["gaba_a_rho"]))
        self.assertFalse(ta.mentions("a GABA A receptor modulator", al["gaba_a_rho"]))

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


class TableGateTest(unittest.TestCase):
    """The same gates over a copied table cell instead of a chosen sentence."""

    def test_a_good_row_sets_the_direction_and_cites_the_row(self):
        drug, why, _ = run_tables([GOOD_ROW])
        b = binding(drug, "5ht2c")
        self.assertEqual(why, [])
        self.assertEqual(b["action"], "antagonist")
        self.assertNotIn("affinity_only", b)
        self.assertEqual(b["ki"]["source"]["corpus"], "pdsp_ki")
        self.assertEqual(b["sources"], [{"corpus": "wikipedia_pharm", "page": "testdrug",
                                         "quote": "5-HT 2C | 3.0 | Antagonist",
                                         "provenance": "verified",
                                         "extraction": "code"}])

    def test_the_source_is_stamped_code_and_never_judged(self):
        """A copied cell has no wrong-true-sentence failure mode, so `extraction: "code"`
        stands in for the judge stamp the prose path waits on."""
        drug, _why, _ = run_tables([GOOD_ROW])
        self.assertNotIn("llm", binding(drug, "5ht2c")["sources"][0])

    def test_a_quote_that_does_not_open_with_its_target_cell_is_rejected(self):
        """The row text is the target cell first, so a quote starting anywhere else is not
        the row the proposal claims to have read."""
        drug, why, _ = run_tables([table_row("5ht2c", "5-HT 2C", "Antagonist", "antagonist",
                                             "Binding profile 5-HT 2C | 3.0 | Antagonist")])
        self.assertEqual(why, ["quote does not name the target"])
        self.assertTrue(binding(drug, "5ht2c")["affinity_only"])

    def test_a_name_resolving_elsewhere_cannot_be_paired_with_this_target(self):
        """Gate 5 for a row: the cell resolves under the fetcher's resolver, and it must
        resolve to the very target the row claims."""
        drug, why, _ = run_tables([table_row("5ht2c", "\u03b1 2A", "Agonist", "agonist",
                                             "\u03b1 2A | 12 | Agonist")])
        self.assertEqual(why, ["quote does not name the target"])
        self.assertTrue(binding(drug, "5ht2c")["affinity_only"])

    def test_a_binding_that_already_states_a_direction_is_untouched(self):
        drug, why, _ = run_tables([table_row("h1", "H 1", "Inverse agonist",
                                             "inverse_agonist",
                                             "H 1 | 0.5 | Inverse agonist")])
        b = binding(drug, "h1")
        self.assertEqual(why, ["binding already states a direction"])
        self.assertEqual(b["action"], "antagonist")
        self.assertEqual([src["corpus"] for src in b["sources"]], ["stahl"])

    def test_an_action_outside_the_vocabulary_is_rejected(self):
        drug, why, _ = run_tables([table_row("5ht2c", "5-HT 2C", "Blocks it", "blocks_it",
                                             "5-HT 2C | 3.0 | Antagonist")])
        self.assertEqual(why, ["unknown action"])
        self.assertTrue(binding(drug, "5ht2c")["affinity_only"])

    def test_a_row_that_is_not_on_the_page_fails_the_verbatim_gate(self):
        drug, why, _ = run_tables([table_row("5ht2c", "5-HT 2C", "Partial agonist",
                                             "partial_agonist",
                                             "5-HT 2C | 3.0 | Partial agonist")])
        self.assertEqual(why, ["quote not verbatim on the cited page"])
        self.assertTrue(binding(drug, "5ht2c")["affinity_only"])

    def test_second_run_changes_nothing_and_reports_no_rejection(self):
        data = drugs()
        run_tables([GOOD_ROW], data)
        after_first = copy.deepcopy(data)
        _drug, why, stats = run_tables([GOOD_ROW], data)
        self.assertEqual(data, after_first)
        self.assertEqual(why, [])
        self.assertEqual(stats["skipped: already applied"], 1)

    def test_a_drug_the_dataset_does_not_carry_is_rejected(self):
        data = drugs()
        _stats, rejected = A.apply_tables(
            {"nosuchdrug": {"slug": "nosuchdrug", "rows": [GOOD_ROW]}},
            data, read_table_page, WIKI_TARGETS.get)
        self.assertEqual([line.split("]")[0][1:] for line in rejected],
                         ["drug not in the dataset"])
        self.assertTrue(binding(data[0], "5ht2c")["affinity_only"])


@unittest.skipUnless(HAS_BS4, "the table fetcher imports bs4 at module level")
class TableCellTest(unittest.TestCase):
    """The Action cell -> action-key reading, the one judgement the table pass makes."""

    def test_a_cell_in_the_vocabulary_reads_straight_through(self):
        self.assertEqual(T.typed_action("Antagonist", "receptor"), "antagonist")

    def test_a_footnote_does_not_hide_the_cell(self):
        self.assertEqual(T.fold_cell("Inverse agonist [12]"), "inverse agonist")
        self.assertEqual(T.typed_action("Inverse agonist [12]", "receptor"),
                         "inverse_agonist")

    def test_inhibitor_is_read_by_what_the_target_is(self):
        # One word, three different nodes: a transporter is reuptake-inhibited, an enzyme
        # enzyme-inhibited, a channel blocked, and on a receptor it says nothing.
        self.assertEqual(T.typed_action("Inhibitor", "transporter"), "reuptake_inhibitor")
        self.assertEqual(T.typed_action("Inhibitor", "enzyme"), "enzyme_inhibitor")
        self.assertEqual(T.typed_action("Inhibitor", "ion_channel"), "blocker")
        self.assertIsNone(T.typed_action("Inhibitor", "receptor"))

    def test_a_cell_that_states_no_direction_is_left_alone(self):
        self.assertIsNone(T.typed_action("ND", "receptor"))

    def test_two_readings_in_one_cell_are_left_alone(self):
        # The vocabulary holds one action per binding, so a slash reading is not ours to
        # split.
        self.assertIsNone(
            T.typed_action("partial agonist / functional antagonist", "receptor"))


class SearchTest(unittest.TestCase):
    """The UNKNOWN search's applier (``apply_search``) and its log (``unknown_log``)."""

    LINE = "Nor-A is a potent antagonist of the histamine H1 receptor ."
    SITE = "metabolite:nor_a/bindings[h1]"

    def drugs(self):
        """Two parents of metabolite ``nor_a``, which is ONE store record (``metabs``)."""
        return [{"id": "a", "bindings": [{"target": "d2", "affinity_only": True}],
                 "metabolites": [{"id": "nor_a"}]},
                {"id": "b", "bindings": [], "metabolites": [{"id": "nor_a"}]}]

    def metabs(self):
        return [{"id": "nor_a", "name": "Nor-A", "bindings": [
            {"target": "h1", "affinity_only": True}]}]

    def worklist(self, corpus="europepmc", page="123"):
        searched = [{"corpus": c, "lookup": "x", "hits": 0}
                    for c in ("pdsp_ki", "gtopdb_ki", "wikipedia_pharm", "wikipedia_fr")]
        searched.append({"corpus": "europepmc", "query": "q", "hits": 1,
                         "searched": "2026-10-01"})
        return [{"site": self.SITE, "drug": "a", "metabolite": "Nor-A", "target": "h1",
                 "elsewhere": [], "searched": searched,
                 "candidates": [{"corpus": corpus, "page": page, "line": self.LINE}]},
                {"site": "drug:a/bindings[d2]", "drug": "a", "metabolite": None,
                 "target": "d2", "elsewhere": [], "searched": searched, "candidates": []}]

    def run_search(self, drugs, corpus="europepmc", page="123", metabs=None):
        seen = []

        def other(c, pg):
            seen.append((c, pg))
            return normalize_for_match(self.LINE) if (c, pg) == (corpus, page) else None
        work = self.worklist(corpus, page)
        stats, _ = A.apply_search(work, {self.SITE: fill({"index": 0, "action": "antagonist"},
                                                         work[0]["candidates"])},
                                  drugs, lambda slug: None, other,
                                  self.metabs() if metabs is None else metabs)
        return stats, seen

    def test_a_metabolite_pick_writes_the_one_record_citing_its_own_corpus(self):
        ms = self.metabs()
        stats, seen = self.run_search(self.drugs(), metabs=ms)
        self.assertEqual(stats["node: antagonist"], 1)    # one molecule, one write
        self.assertEqual(seen, [("europepmc", "123")])
        for b in (ms[0]["bindings"][0],):
            self.assertEqual(b["action"], "antagonist")
            self.assertNotIn("affinity_only", b)
            self.assertEqual(b["sources"][0]["corpus"], "europepmc")
            self.assertEqual(b["sources"][0]["page"], "123")

    def test_a_french_wikipedia_page_is_read_through_its_own_corpus(self):
        stats, seen = self.run_search(self.drugs(), corpus="wikipedia_fr", page="nor-a")
        self.assertEqual(seen, [("wikipedia_fr", "nor-a")])
        self.assertEqual(stats["node: antagonist"], 1)

    def test_an_out_of_range_pick_is_rejected(self):
        stats, _ = A.apply_search(self.worklist(), {self.SITE: {"index": 3, "action": "antagonist"}},
                                  self.drugs(), lambda s: None, lambda c, p: None)
        self.assertEqual(stats["rejected: candidate index out of range"], 1)

    def test_the_log_covers_only_what_the_search_left_directionless(self):
        ds, ms = self.drugs(), self.metabs()
        self.run_search(ds, metabs=ms)
        log = A.unknown_log(self.worklist(), ds, {"harness": "Claude Code", "model": "opus",
                                                  "date": "2026-10-12"},
                            prior={self.SITE: {"stale": True}}, metabolites=ms)
        self.assertEqual(sorted(log), ["drug:a/bindings[d2]"])
        entry = log["drug:a/bindings[d2]"]
        self.assertEqual(entry["searched"], "2026-10-01")  # the oldest leg dates it
        self.assertEqual([s["corpus"] for s in entry["sources"]][-1], "europepmc")
        self.assertNotIn("searched", entry["sources"][-1])

    def test_a_direction_found_elsewhere_keeps_the_binding_out_of_the_log(self):
        wl = self.worklist()
        wl[1]["elsewhere"] = [{"corpus": "gtopdb_ki", "action": "antagonist"}]
        log = A.unknown_log(wl, self.drugs(), {"harness": "h", "model": "m", "date": "d"},
                            metabolites=self.metabs())
        self.assertNotIn("drug:a/bindings[d2]", log)


if __name__ == "__main__":
    unittest.main()
