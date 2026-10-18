#!/usr/bin/env python
"""Unit tests for the metabolite-merging half of the pharmacokinetics pass
(``apply_pharmacokinetics.apply``) and the bindings passes' "non-modeled" rule.

Stdlib ``unittest`` over a fake page store in a temp dir, so it runs on a clone lacking
the corpus trees::

    python -m unittest discover -t tools/tests -s tools/tests -p test_pk_metabolites.py

Built with the help of Claude Code.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
import apply_pharmacokinetics as PK  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)

STAHL = "Venlafaxine active metabolite O-desmethylvenlafaxine (ODV)\nElimination half-life 40-50 hours\n"
WIKI = "Elimination half-life | 36-200 hours\n"


class MergeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "stahl").mkdir()
        (root / "wiki").mkdir()
        (root / "stahl" / "1.md").write_text(STAHL, encoding="utf-8")
        (root / "wiki" / "nordazepam.md").write_text(WIKI, encoding="utf-8")
        self.pages = PageGate({"stahl": root / "stahl", "wikipedia_pharm": root / "wiki"})

    def test_link_by_explicit_drug_id_keeps_other_passes_fields(self):
        drugs = [{"id": "venlafaxine", "name": "Venlafaxine", "metabolites": [
                     {"id": "o_desmethylvenlafaxine"}, {"id": "other", "sources": []}]},
                 {"id": "desvenlafaxine", "name": "Desvenlafaxine"}]
        store = [{"id": "o_desmethylvenlafaxine", "name": "O-desmethylvenlafaxine",
                  "bindings": [{"target": "sert"}]},
                 {"id": "other", "name": "Other"}]
        judged = {"venlafaxine": {"metabolites": [{
            "name": "O-desmethylvenlafaxine", "drug_id": "desvenlafaxine", "page": 1,
            "quote": "Venlafaxine active metabolite O-desmethylvenlafaxine (ODV)"}]}}
        _, n_met, warnings = PK.apply(judged, drugs, self.pages, None, store)
        self.assertEqual((n_met, warnings), (1, []))
        refs = drugs[0]["metabolites"]
        self.assertEqual([r["id"] for r in refs], ["o_desmethylvenlafaxine", "other"])
        self.assertEqual(refs[0]["sources"][0]["page"], 1)          # per-parent claim on the ref
        self.assertEqual(store[0]["drug_id"], "desvenlafaxine")    # molecule fact on the record
        self.assertEqual(store[0]["bindings"], [{"target": "sert"}])   # not the PK pass's
        self.assertNotIn("sources", store[0])

    def test_null_half_life_clears_and_metabolite_gets_wikipedia_figure(self):
        drugs = [{"id": "clorazepate", "name": "Clorazepate",
                  "half_life": {"hours": 40.0}, "half_life_sources": [{}],
                  "metabolites": [{"id": "desmethyldiazepam"}]}]
        store = [{"id": "desmethyldiazepam", "name": "Desmethyldiazepam (nordazepam)",
                  "bindings": [{"target": "gaba_a"}]}]
        q = {"corpus": "wikipedia_pharm", "page": "nordazepam",
             "quote": "Elimination half-life | 36-200 hours"}
        judged = {"clorazepate": {"half_life": None, "metabolites": [
            dict(q, name="Nordazepam", half_life=dict(q, hours=36, hours_max=200))]}}
        PK.apply(judged, drugs, self.pages, None, store)
        d = drugs[0]
        self.assertNotIn("half_life", d)
        self.assertNotIn("half_life_sources", d)
        (ref,) = d["metabolites"]
        (m,) = store                                   # matched by synonym, no new record
        self.assertEqual(m["name"], "Desmethyldiazepam (nordazepam)")   # the store owns the name
        self.assertEqual(m["half_life"], {"hours": 36.0, "hours_max": 200.0})
        self.assertEqual(ref["sources"][0]["page"], "nordazepam")
        self.assertEqual(m["bindings"], [{"target": "gaba_a"}])

    def test_two_parents_share_one_record(self):
        """The point of the store: a molecule two drugs make is defined once."""
        drugs = [{"id": "diazepam", "name": "Diazepam"}, {"id": "prazepam", "name": "Prazepam"}]
        store: list = []
        q = {"corpus": "wikipedia_pharm", "page": "nordazepam",
             "quote": "Elimination half-life | 36-200 hours"}
        judged = {"diazepam": {"metabolites": [dict(q, name="Desmethyldiazepam (nordazepam)")]},
                  "prazepam": {"metabolites": [dict(q, name="Nordazepam")]}}
        PK.apply(judged, drugs, self.pages, None, store)
        self.assertEqual([m["id"] for m in store], ["desmethyldiazepam"])
        self.assertEqual([d["metabolites"][0]["id"] for d in drugs],
                         ["desmethyldiazepam", "desmethyldiazepam"])

    def test_quoteless_entry_only_sets_an_existing_metabolites_half_life(self):
        src = [{"corpus": "wikipedia_pharm", "page": "prazepam", "quote": "prodrug"}]
        drugs = [{"id": "prazepam", "name": "Prazepam", "metabolites": [
            {"id": "desmethyldiazepam", "sources": src}]}]
        store = [{"id": "desmethyldiazepam", "name": "Desmethyldiazepam (nordazepam)"}]
        q = {"corpus": "wikipedia_pharm", "page": "nordazepam",
             "quote": "Elimination half-life | 36-200 hours", "hours": 36, "hours_max": 200}
        judged = {"prazepam": {"metabolites": [
            {"name": "Desmethyldiazepam (nordazepam)", "half_life": q},
            {"name": "Unknown", "half_life": q}]}}
        _, _, warnings = PK.apply(judged, drugs, self.pages, None, store)
        (ref,) = drugs[0]["metabolites"]
        self.assertEqual(ref["sources"], src)
        self.assertEqual(store[0]["half_life"], {"hours": 36.0, "hours_max": 200.0})
        self.assertEqual(len(store), 1)
        self.assertIn("no quote", warnings[0])

    def test_off_page_quote_writes_nothing(self):
        drugs = [{"id": "x", "name": "X"}]
        judged = {"x": {"metabolites": [{"name": "Y", "page": 1, "quote": "not there"}]}}
        _, n_met, warnings = PK.apply(judged, drugs, self.pages)
        self.assertEqual(n_met, 0)
        self.assertEqual(len(warnings), 1)
        self.assertNotIn("metabolites", drugs[0])


class NonModeledTest(unittest.TestCase):
    """Which store records a bindings pass sources: the ones not themselves a drug."""

    def test_linked_by_id_or_name_is_skipped_and_parents_are_listed(self):
        from lib import drugs_io
        drugs = [{"id": "venlafaxine", "name": "Venlafaxine",
                  "metabolites": [{"id": "odv"}, {"id": "temazepam"}]},
                 {"id": "desvenlafaxine", "name": "Desvenlafaxine"},
                 {"id": "temazepam", "name": "Temazepam"},
                 {"id": "clozapine", "name": "Clozapine", "metabolites": [{"id": "norclozapine"}]},
                 {"id": "other", "name": "Other", "metabolites": [{"id": "norclozapine"}]}]
        store = [{"id": "odv", "name": "O-desmethylvenlafaxine", "drug_id": "desvenlafaxine"},
                 {"id": "temazepam", "name": "Temazepam"},
                 {"id": "norclozapine", "name": "Norclozapine"},
                 {"id": "unreferenced", "name": "Unreferenced"}]
        out = drugs_io.non_modeled_metabolites(drugs, store)
        self.assertEqual([(m["id"], m["parents"]) for m in out],
                         [("norclozapine", ["clozapine", "other"])])


if __name__ == "__main__":
    unittest.main()
