"""``data_generators/effect_index.py``: the one effect -> receptors -> drugs join (BETA),
read by llms.txt, the /api/ effect pages and (as ``derived/effects.json``) the viewer.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_effect_index.py``
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data_generators"))

import effect_index  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "public" / "data"

MODES = {"agonism": {"label": "Agonism", "actions": ["agonist", "partial_agonist"]},
         "antagonism": {"label": "Antagonism", "actions": ["antagonist"]}}
META = {"receptor_effect_modes": MODES,
        "receptor_effect_labels": {"sedation": {"en": "Sedation", "fr": "Sédation"},
                                   "hallucinations": "Hallucinations"},
        "drug_targets": {"h1": {"receptor": "h1"},
                         "sert": {"name": "SERT", "effects": []}}}
RECEPTORS = [
    {"id": "h1", "name": "H1", "effects": [{"mode": "antagonism", "effect": "sedation"}]},
    {"id": "5ht2a", "name": "5-HT2A", "effects": [{"mode": "agonism", "effect": "hallucinations"}]},
]


class JoinTest(unittest.TestCase):
    def test_direction_aware_and_affinity_only_ignored(self):
        drugs = [{"id": "quetiapine", "bindings": [{"target": "h1", "action": "antagonist"},
                                                   {"target": "5ht2a", "action": "antagonist"}]},
                 {"id": "kionly", "bindings": [{"target": "h1"}]}]
        idx = {e["id"]: e for e in effect_index.build(RECEPTORS, drugs, [], META)}
        self.assertEqual([d["drug"]["id"] for d in idx["sedation"]["drugs"]], ["quetiapine"])
        self.assertEqual(idx["hallucinations"]["drugs"], [])
        self.assertEqual(idx["sedation"]["label"], "Sedation")
        self.assertEqual(idx["sedation"]["owners"][0]["name"], "H1")

    def test_prodrug_borrows_its_metabolite_bindings(self):
        drugs = [{"id": "pro", "prodrug": True, "bindings": [], "metabolites": [{"id": "m"}]},
                 {"id": "active", "bindings": [{"target": "5ht2a", "action": "agonist"}]}]
        metabolites = [{"id": "m", "name": "Active", "drug_id": "active"}]
        idx = {e["id"]: e for e in effect_index.build(RECEPTORS, drugs, metabolites, META)}
        got = {d["drug"]["id"]: d["via"] for d in idx["hallucinations"]["drugs"]}
        self.assertEqual(set(got), {"pro", "active"})
        self.assertEqual(got["pro"][0][0]["via_metabolite"], "Active")

    def test_any_drug_adds_its_active_metabolites_bindings_labelled(self):
        # Not a prodrug: the parent's own H1 block and its metabolite's (own bindings,
        # not a modeled drug) are two routes to sedation, the metabolite's tagged.
        drugs = [{"id": "parent", "bindings": [{"target": "h1", "action": "antagonist"}],
                  "metabolites": [{"id": "m"}]}]
        metabolites = [{"id": "m", "name": "Normet",
                        "bindings": [{"target": "h1", "action": "antagonist"}]}]
        idx = {e["id"]: e for e in effect_index.build(RECEPTORS, drugs, metabolites, META)}
        via = idx["sedation"]["drugs"][0]["via"]
        self.assertEqual([b.get("via_metabolite") for b, _ in via], [None, "Normet"])

    def test_salt_borrows_its_modeled_constituents_bindings(self):
        drugs = [{"id": "salt", "name": "Salt", "bindings": [],
                  "constituents": ["Diphenhydramine", "8-Chlorotheophylline"]},
                 {"id": "diphenhydramine", "name": "Diphenhydramine",
                  "bindings": [{"target": "h1", "action": "antagonist"}]}]
        idx = {e["id"]: e for e in effect_index.build(RECEPTORS, drugs, [], META)}
        got = {d["drug"]["id"]: d["via"] for d in idx["sedation"]["drugs"]}
        self.assertEqual(set(got), {"salt", "diphenhydramine"})
        self.assertEqual(got["salt"][0][0]["via_metabolite"], "Diphenhydramine")

    def test_summary_line(self):
        drugs = [{"id": "q", "bindings": [{"target": "h1", "action": "antagonist"}]}]
        lines = effect_index.summary_lines(effect_index.build(RECEPTORS, drugs, [], META),
                                           MODES, "https://x")
        self.assertIn("- [Sedation](https://x/api/effect/sedation) `sedation`: "
                      "antagonism of H1; 1 drug could cause it", lines)


class GroupingTest(unittest.TestCase):
    def test_two_receptors_reaching_one_effect_are_grouped_under_it(self):
        receptors = RECEPTORS + [{"id": "alpha1a", "name": "α1A",
                                  "effects": [{"mode": "antagonism", "effect": "sedation"}]}]
        drugs = [{"id": "q", "bindings": [{"target": "h1", "action": "antagonist"},
                                          {"target": "alpha1a", "action": "antagonist"}]}]
        idx = {e["id"]: e for e in effect_index.build(receptors, drugs, [], META)}
        self.assertEqual([b["target"] for b, _ in idx["sedation"]["drugs"][0]["via"]],
                         ["h1", "alpha1a"])
        self.assertEqual([o["id"] for o in idx["sedation"]["owners"]], ["h1", "alpha1a"])

    def test_owners_by_mode_is_mode_ordered_id_sorted_and_english(self):
        effect = {"owners": [{"id": "h1", "node": {"mode": "antagonism"}},
                             {"id": "alpha1a", "node": {"mode": "antagonism"}},
                             {"id": "d2", "node": {"mode": "agonism"}}]}
        modes = {"agonism": {"label": {"en": "Agonism", "fr": "Agonisme"}},
                 "antagonism": {"label": "Antagonism"}, "modulation": {}}
        got = [(label, [o["id"] for o in owners])
               for label, owners in effect_index.owners_by_mode(effect, modes)]
        self.assertEqual(got, [("Agonism", ["d2"]), ("Antagonism", ["alpha1a", "h1"])])


class ToJsonTest(unittest.TestCase):
    """The viewer's file shape, which ``readEffectIndex`` (js/receptor-effects.js)
    reads; ``receptor_effects.test.mjs`` reads back the real file."""

    def test_ids_only_with_via_metabolite_on_borrowed_bindings(self):
        drugs = [{"id": "pro", "prodrug": True, "bindings": [], "metabolites": [{"id": "m"}]},
                 {"id": "active", "bindings": [{"target": "5ht2a", "action": "agonist", "ki": 3}]}]
        metabolites = [{"id": "m", "name": "Active", "drug_id": "active"}]
        out = effect_index.to_json(effect_index.build(RECEPTORS, drugs, metabolites, META))
        self.assertEqual(out["effects"][0], {
            "id": "hallucinations",
            "owners": [{"target": "5ht2a", "mode": "agonism"}],
            "drugs": [{"drug": "pro", "via": [{"target": "5ht2a", "action": "agonist",
                                               "mode": "agonism", "via_metabolite": "Active"}]},
                      {"drug": "active", "via": [{"target": "5ht2a", "action": "agonist",
                                                  "mode": "agonism"}]}]})
        self.assertEqual(out["effects"][1]["id"], "sedation")

    def test_write_effects_from_the_emitted_data(self):
        import tempfile
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import render_api
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "derived" / "effects.json"
            n = render_api.write_effects(DATA, path)
            out = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(n, len(out["effects"]))
        ids = [e["id"] for e in out["effects"]]
        self.assertIn("nausea", ids)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
